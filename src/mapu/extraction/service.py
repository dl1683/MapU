"""Extraction service: orchestrates the full span -> proposition pipeline."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.extraction.abstention import AbstentionGate
from mapu.extraction.grounding import CandidateGrounder, MaterializedExtraction
from mapu.extraction.merge import CandidateMergeEngine
from mapu.extraction.spacy_base import SpacyBaseParser
from mapu.extraction.types import (
    EntityMention,
    ExtractionContext,
    ExtractionPlan,
    ExtractionSignal,
    Extractor,
    ExtractorOutput,
    ExtractorStage,
)
from mapu.models.authority import SourcePolicyEval
from mapu.models.evidence import DocumentExpression, TextSpan


@dataclass
class ExtractionResult:
    """Summary of extraction for an expression."""

    expression_id: uuid.UUID
    spans_processed: int = 0
    candidates_produced: int = 0
    duplicates_removed: int = 0
    accepted: int = 0
    candidate_status: int = 0
    rejected: int = 0
    materialized: list[MaterializedExtraction] = field(default_factory=list)
    signals: list[ExtractionSignal] = field(default_factory=list)


def _make_sequential_plan(extractors: list[Extractor]) -> ExtractionPlan:
    """Wrap a flat extractor list as sequential single-extractor stages."""
    stages = tuple(
        ExtractorStage(name=ext.name, extractors=(ext,), parallel=False)
        for ext in extractors
    )
    return ExtractionPlan(stages=stages)


class ExtractionService:
    """Orchestrates: spans -> base parse -> stages -> merge -> abstention -> ground."""

    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        extractors: list[Extractor],
        merge_engine: CandidateMergeEngine,
        abstention_gate: AbstentionGate,
        grounder: CandidateGrounder,
        spacy_parser: SpacyBaseParser | None = None,
        plan: ExtractionPlan | None = None,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id
        self._merge = merge_engine
        self._abstention = abstention_gate
        self._grounder = grounder
        self._spacy = spacy_parser
        self._plan = plan or _make_sequential_plan(extractors)

    async def extract_expression(
        self,
        expression_id: uuid.UUID,
        source_policy_eval_id: uuid.UUID,
        default_situation_id: uuid.UUID | None = None,
    ) -> ExtractionResult:
        document_id = await self._get_document_id(expression_id)
        await self._validate_source_policy(source_policy_eval_id, document_id)
        spans = await self._load_spans(expression_id)

        result = ExtractionResult(expression_id=expression_id)

        for span in spans:
            base_parse = None
            if self._spacy is not None:
                base_parse = await asyncio.to_thread(
                    self._spacy.parse, span.text
                )

            ctx = ExtractionContext(
                corpus_id=self._corpus_id,
                document_id=document_id,
                expression_id=expression_id,
                span_id=span.id,
                node_id=span.node_id,
                text=span.text,
                start_char=span.start_char,
                end_char=span.end_char,
                base_parse=base_parse,
            )

            outputs = await self._run_stages(ctx)

            merged = self._merge.merge(outputs)
            result.candidates_produced += len(merged.frames)
            result.duplicates_removed += merged.duplicates_removed
            result.signals.extend(merged.signals)

            abstention_results = self._abstention.evaluate(merged.frames)

            for ar in abstention_results:
                if ar.decision.value == "rejected":
                    result.rejected += 1
                    continue

                if ar.decision.value == "accepted":
                    result.accepted += 1
                else:
                    result.candidate_status += 1

                materialized = await self._grounder.materialize(
                    ar,
                    source_policy_eval_id=source_policy_eval_id,
                    default_situation_id=default_situation_id,
                )
                if materialized is not None:
                    result.materialized.append(materialized)

            result.spans_processed += 1

        if result.materialized:
            await self._grounder.flush()

        await self._process_amendment_signals(result, expression_id)

        return result

    async def _run_stages(
        self, base_ctx: ExtractionContext,
    ) -> list[ExtractorOutput]:
        accumulated_signals: list[ExtractionSignal] = []
        accumulated_entities: list[EntityMention] = []
        all_outputs: list[ExtractorOutput] = []

        for stage in self._plan.stages:
            ctx = ExtractionContext(
                corpus_id=base_ctx.corpus_id,
                document_id=base_ctx.document_id,
                expression_id=base_ctx.expression_id,
                span_id=base_ctx.span_id,
                node_id=base_ctx.node_id,
                text=base_ctx.text,
                start_char=base_ctx.start_char,
                end_char=base_ctx.end_char,
                base_parse=base_ctx.base_parse,
                prior_signals=tuple(accumulated_signals),
                prior_entities=tuple(accumulated_entities),
            )

            if stage.parallel and len(stage.extractors) > 1:
                stage_outputs = list(await asyncio.gather(
                    *(ext.extract(ctx) for ext in stage.extractors)
                ))
                for output in stage_outputs:
                    accumulated_signals.extend(output.signals)
                    accumulated_entities.extend(output.entities)
                    all_outputs.append(output)
            else:
                for ext in stage.extractors:
                    ctx = ExtractionContext(
                        corpus_id=base_ctx.corpus_id,
                        document_id=base_ctx.document_id,
                        expression_id=base_ctx.expression_id,
                        span_id=base_ctx.span_id,
                        node_id=base_ctx.node_id,
                        text=base_ctx.text,
                        start_char=base_ctx.start_char,
                        end_char=base_ctx.end_char,
                        base_parse=base_ctx.base_parse,
                        prior_signals=tuple(accumulated_signals),
                        prior_entities=tuple(accumulated_entities),
                    )
                    output = await ext.extract(ctx)
                    accumulated_signals.extend(output.signals)
                    accumulated_entities.extend(output.entities)
                    all_outputs.append(output)

        return all_outputs

    async def _get_document_id(self, expression_id: uuid.UUID) -> uuid.UUID:
        stmt = select(DocumentExpression.document_id).where(
            DocumentExpression.id == expression_id,
            DocumentExpression.corpus_id == self._corpus_id,
        )
        r = await self._session.execute(stmt)
        row = r.scalar_one_or_none()
        if row is None:
            raise ValueError(f"Expression {expression_id} not found")
        return row

    async def _validate_source_policy(
        self, source_policy_eval_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        stmt = select(SourcePolicyEval.document_id).where(
            SourcePolicyEval.id == source_policy_eval_id,
            SourcePolicyEval.corpus_id == self._corpus_id,
        )
        r = await self._session.execute(stmt)
        spe_doc_id = r.scalar_one_or_none()
        if spe_doc_id is None:
            raise ValueError(
                f"SourcePolicyEval {source_policy_eval_id} not found"
            )
        if spe_doc_id != document_id:
            raise ValueError(
                f"SourcePolicyEval document_id {spe_doc_id} does not match "
                f"expression document_id {document_id}"
            )

    async def _process_amendment_signals(
        self,
        result: ExtractionResult,
        expression_id: uuid.UUID,
    ) -> None:
        from datetime import UTC, datetime

        from mapu.models.entity import Handle
        from mapu.models.lineage import SupersessionEdge
        from mapu.models.proposition import Proposition

        amendment_signals = [
            s for s in result.signals if s.signal_type == "amendment"
        ]
        if not amendment_signals:
            return

        amendment_props = [
            m for m in result.materialized
            if m.proposition.predicate == "amended"
        ]
        if not amendment_props:
            return

        for mat in amendment_props:
            target_ref = mat.proposition.normalized_text
            if not target_ref:
                continue

            subject_handle = mat.proposition.subject_handle_id
            stmt = (
                select(Proposition)
                .join(Handle, Proposition.subject_handle_id == Handle.id)
                .where(
                    Proposition.corpus_id == self._corpus_id,
                    Handle.id == subject_handle,
                    Proposition.id != mat.proposition.id,
                )
                .order_by(Proposition.system_created.desc())
                .limit(1)
            )
            r = await self._session.execute(stmt)
            old_prop = r.scalar_one_or_none()
            if old_prop is None:
                continue

            existing = await self._session.execute(
                select(SupersessionEdge.id).where(
                    SupersessionEdge.old_proposition_id == old_prop.id,
                    SupersessionEdge.new_proposition_id == mat.proposition.id,
                    SupersessionEdge.corpus_id == self._corpus_id,
                ),
            )
            if existing.scalar_one_or_none() is not None:
                continue

            now = datetime.now(UTC)
            self._session.add(SupersessionEdge(
                corpus_id=self._corpus_id,
                old_proposition_id=old_prop.id,
                new_proposition_id=mat.proposition.id,
                supersession_type="supersession",
                effective_at=now,
            ))
            if old_prop.valid_range is not None and old_prop.valid_range.upper is None:
                from sqlalchemy.dialects.postgresql import Range
                old_prop.valid_range = Range(
                    old_prop.valid_range.lower, now, bounds="[)",
                )
        await self._session.flush()

    async def _load_spans(self, expression_id: uuid.UUID) -> list[TextSpan]:
        stmt = (
            select(TextSpan)
            .where(
                TextSpan.expression_id == expression_id,
                TextSpan.corpus_id == self._corpus_id,
            )
            .order_by(TextSpan.start_char, TextSpan.id)
        )
        r = await self._session.execute(stmt)
        return list(r.scalars().all())
