"""Tier 0: Direct state lookup — pure SQL, no LLM, no embeddings."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, load_only

from mapu.models.attestation import Attestation
from mapu.models.authority import SourcePolicyEval
from mapu.models.entity import Handle
from mapu.models.evidence import TextSpan
from mapu.models.proposition import Proposition
from mapu.models.truth import PropositionState
from mapu.query.types import PropositionHit, QueryPlan, QueryRequest, Tier


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input matches literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class DirectLookupExecutor:
    """Executes Tier 0 queries: entity identity, single-fact lookup."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def tier(self) -> Tier:
        return Tier.DIRECT

    async def execute(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> Sequence[PropositionHit]:
        if plan.entities_extracted:
            hits = await self._lookup(
                corpus_id=request.corpus_id,
                entity_texts=plan.entities_extracted,
                predicate_texts=(),
                limit=request.max_results,
                relevance=1.0,
                situation_id=request.situation_id,
            )
            if hits:
                return hits

        if plan.predicates_extracted:
            return await self._lookup(
                corpus_id=request.corpus_id,
                entity_texts=(),
                predicate_texts=plan.predicates_extracted,
                limit=request.max_results,
                relevance=0.9,
                situation_id=request.situation_id,
            )

        return ()

    async def _lookup(
        self,
        corpus_id: uuid.UUID,
        entity_texts: tuple[str, ...],
        predicate_texts: tuple[str, ...],
        limit: int,
        relevance: float,
        situation_id: uuid.UUID | None = None,
    ) -> list[PropositionHit]:
        obj_handle = aliased(Handle, name="object_handle")
        truth_col = (
            PropositionState.truth_status
            if situation_id is not None
            else null().label("truth_status")
        )
        stmt = (
            select(
                Proposition, Handle, Attestation,
                SourcePolicyEval, TextSpan, obj_handle,
                truth_col,
            )
            .options(
                load_only(
                    Proposition.id, Proposition.normalized_text,
                    Proposition.frame_type, Proposition.predicate,
                    Proposition.corpus_id, Proposition.subject_handle_id,
                ),
                load_only(Handle.id, Handle.canonical_name, Handle.kind),
                load_only(
                    Attestation.proposition_id, Attestation.corpus_id,
                    Attestation.extraction_confidence, Attestation.status,
                    Attestation.system_invalidated,
                ),
                load_only(SourcePolicyEval.authority_score),
                load_only(TextSpan.text),
                load_only(obj_handle.canonical_name, obj_handle.kind),
            )
            .join(Handle, Proposition.subject_handle_id == Handle.id)
            .join(
                Attestation,
                (Attestation.proposition_id == Proposition.id)
                & (Attestation.corpus_id == Proposition.corpus_id),
            )
            .outerjoin(
                SourcePolicyEval,
                Attestation.source_policy_eval_id == SourcePolicyEval.id,
            )
            .outerjoin(TextSpan, Attestation.span_id == TextSpan.id)
            .outerjoin(
                obj_handle,
                Proposition.object_handle_id == obj_handle.id,
            )
        )

        if situation_id is not None:
            stmt = stmt.outerjoin(
                PropositionState,
                (PropositionState.proposition_id == Proposition.id)
                & (PropositionState.corpus_id == Proposition.corpus_id)
                & (PropositionState.situation_id == situation_id)
                & (func.upper(PropositionState.effective_range).is_(None)),
            )

        stmt = stmt.where(
            Proposition.corpus_id == corpus_id,
            Attestation.status == "accepted",
            Attestation.system_invalidated.is_(None),
        )

        filters = []
        for entity in entity_texts:
            filters.append(
                Handle.canonical_name.ilike(f"%{_escape_like(entity)}%")
            )
        for pred in predicate_texts:
            filters.append(
                Proposition.predicate.ilike(f"%{_escape_like(pred)}%")
            )
        if filters:
            stmt = stmt.where(or_(*filters))

        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        rows = result.all()

        seen: set[uuid.UUID] = set()
        hits: list[PropositionHit] = []
        for prop, handle, att, spe, span, obj_h, truth_status in rows:
            if prop.id in seen:
                continue
            seen.add(prop.id)
            hits.append(PropositionHit(
                proposition_id=prop.id,
                normalized_text=prop.normalized_text,
                frame_type=prop.frame_type,
                predicate=prop.predicate,
                subject_name=handle.canonical_name,
                subject_kind=handle.kind,
                object_name=obj_h.canonical_name if obj_h else None,
                object_kind=obj_h.kind if obj_h else None,
                truth_status=truth_status,
                extraction_confidence=att.extraction_confidence,
                authority_score=spe.authority_score if spe else None,
                source_span_text=span.text if span else None,
                relevance_score=relevance,
            ))
        return hits
