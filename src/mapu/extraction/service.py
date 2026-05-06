"""Extraction service: orchestrates the full span -> proposition pipeline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.extraction.abstention import AbstentionGate
from mapu.extraction.grounding import CandidateGrounder, MaterializedExtraction
from mapu.extraction.merge import CandidateMergeEngine
from mapu.extraction.spacy_base import SpacyBaseParser
from mapu.extraction.types import (
    ExtractionContext,
    Extractor,
    ExtractorOutput,
)
from mapu.models.evidence import TextSpan


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


class ExtractionService:
    """Orchestrates: spans -> base parse -> extractors -> merge -> abstention -> ground."""

    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        extractors: list[Extractor],
        merge_engine: CandidateMergeEngine,
        abstention_gate: AbstentionGate,
        grounder: CandidateGrounder,
        spacy_parser: SpacyBaseParser | None = None,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id
        self._extractors = extractors
        self._merge = merge_engine
        self._abstention = abstention_gate
        self._grounder = grounder
        self._spacy = spacy_parser

    async def extract_expression(
        self,
        expression_id: uuid.UUID,
        source_policy_eval_id: uuid.UUID,
        default_situation_id: uuid.UUID | None = None,
    ) -> ExtractionResult:
        spans = await self._load_spans(expression_id)

        result = ExtractionResult(expression_id=expression_id)

        for span in spans:
            base_parse = None
            if self._spacy is not None:
                base_parse = self._spacy.parse(span.text)

            ctx = ExtractionContext(
                corpus_id=self._corpus_id,
                document_id=uuid.UUID(int=0),
                expression_id=expression_id,
                span_id=span.id,
                node_id=span.node_id,
                text=span.text,
                start_char=span.start_char,
                end_char=span.end_char,
                base_parse=base_parse,
            )

            outputs: list[ExtractorOutput] = []
            for extractor in self._extractors:
                output = await extractor.extract(ctx)
                outputs.append(output)

            merged = self._merge.merge(outputs)
            result.candidates_produced += len(merged.frames)
            result.duplicates_removed += merged.duplicates_removed

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

        return result

    async def _load_spans(self, expression_id: uuid.UUID) -> list[TextSpan]:
        stmt = select(TextSpan).where(
            TextSpan.expression_id == expression_id,
            TextSpan.corpus_id == self._corpus_id,
        )
        r = await self._session.execute(stmt)
        return list(r.scalars().all())
