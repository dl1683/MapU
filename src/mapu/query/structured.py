"""Tier 1: Structured query execution — parameterized SQL, no LLM."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.attestation import Attestation
from mapu.models.entity import Handle
from mapu.models.proposition import Proposition
from mapu.query.direct import _escape_like
from mapu.query.types import PropositionHit, QueryIntent, QueryPlan, QueryRequest, Tier


class StructuredQueryExecutor:
    """Executes Tier 1 queries: list, temporal, temporal_diff, measurement."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def tier(self) -> Tier:
        return Tier.STRUCTURED

    async def execute(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> Sequence[PropositionHit]:
        if plan.intent == QueryIntent.LIST:
            return await self._execute_list(plan, request)
        if plan.intent == QueryIntent.TEMPORAL:
            return await self._execute_temporal(plan, request)
        if plan.intent == QueryIntent.TEMPORAL_DIFF:
            return await self._execute_temporal_diff(plan, request)
        if plan.intent == QueryIntent.MEASUREMENT:
            return await self._execute_measurement(plan, request)
        return await self._execute_generic(plan, request)

    async def _execute_list(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> list[PropositionHit]:
        stmt = self._base_query(request.corpus_id)
        if plan.predicates_extracted:
            predicates = plan.predicates_extracted
            stmt = stmt.where(
                Proposition.predicate.ilike(f"%{_escape_like(predicates[0])}%")
            )
        if plan.entities_extracted:
            stmt = stmt.where(
                Handle.canonical_name.ilike(f"%{_escape_like(plan.entities_extracted[0])}%")
            )
        stmt = stmt.order_by(Proposition.system_created.desc()).limit(request.max_results)
        return await self._fetch(stmt)

    async def _execute_temporal(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> list[PropositionHit]:
        stmt = self._base_query(request.corpus_id)
        if plan.entities_extracted:
            stmt = stmt.where(
                Handle.canonical_name.ilike(f"%{_escape_like(plan.entities_extracted[0])}%")
            )
        stmt = stmt.where(Proposition.valid_range.isnot(None))
        stmt = stmt.order_by(Proposition.system_created.desc()).limit(request.max_results)
        return await self._fetch(stmt)

    async def _execute_temporal_diff(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> list[PropositionHit]:
        from mapu.models.lineage import SupersessionEdge

        stmt = (
            select(Proposition, Handle, Attestation)
            .join(Handle, Proposition.subject_handle_id == Handle.id)
            .join(
                Attestation,
                (Attestation.proposition_id == Proposition.id)
                & (Attestation.corpus_id == Proposition.corpus_id),
            )
            .join(
                SupersessionEdge,
                (
                    (SupersessionEdge.old_proposition_id == Proposition.id)
                    | (SupersessionEdge.new_proposition_id == Proposition.id)
                )
                & (SupersessionEdge.corpus_id == Proposition.corpus_id),
            )
            .where(
                Proposition.corpus_id == request.corpus_id,
                Attestation.status == "accepted",
                Attestation.system_invalidated.is_(None),
            )
        )
        if plan.entities_extracted:
            stmt = stmt.where(
                Handle.canonical_name.ilike(f"%{_escape_like(plan.entities_extracted[0])}%")
            )
        if plan.predicates_extracted:
            stmt = stmt.where(
                Proposition.predicate.ilike(f"%{_escape_like(plan.predicates_extracted[0])}%")
            )
        stmt = stmt.limit(request.max_results)
        return await self._fetch(stmt)

    async def _execute_measurement(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> list[PropositionHit]:
        from mapu.types import FrameType

        stmt = self._base_query(request.corpus_id).where(
            Proposition.frame_type.in_([
                FrameType.MEASUREMENT.value,
                FrameType.THRESHOLD.value,
            ])
        )
        if plan.entities_extracted:
            stmt = stmt.where(
                Handle.canonical_name.ilike(f"%{_escape_like(plan.entities_extracted[0])}%")
            )
        stmt = stmt.limit(request.max_results)
        return await self._fetch(stmt)

    async def _execute_generic(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> list[PropositionHit]:
        stmt = self._base_query(request.corpus_id)
        if plan.entities_extracted:
            stmt = stmt.where(
                Handle.canonical_name.ilike(f"%{_escape_like(plan.entities_extracted[0])}%")
            )
        if plan.predicates_extracted:
            stmt = stmt.where(
                Proposition.predicate.ilike(f"%{_escape_like(plan.predicates_extracted[0])}%")
            )
        stmt = stmt.order_by(Attestation.extraction_confidence.desc()).limit(request.max_results)
        return await self._fetch(stmt)

    def _base_query(self, corpus_id: uuid.UUID) -> Any:
        return (
            select(Proposition, Handle, Attestation)
            .join(Handle, Proposition.subject_handle_id == Handle.id)
            .join(
                Attestation,
                (Attestation.proposition_id == Proposition.id)
                & (Attestation.corpus_id == Proposition.corpus_id),
            )
            .where(
                Proposition.corpus_id == corpus_id,
                Attestation.status == "accepted",
                Attestation.system_invalidated.is_(None),
            )
        )

    async def _fetch(self, stmt: Any) -> list[PropositionHit]:
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            PropositionHit(
                proposition_id=prop.id,
                normalized_text=prop.normalized_text,
                frame_type=prop.frame_type,
                predicate=prop.predicate,
                subject_name=handle.canonical_name,
                subject_kind=handle.kind,
                object_name=None,
                object_kind=None,
                truth_status=None,
                extraction_confidence=att.extraction_confidence,
                authority_score=None,
                source_span_text=None,
                relevance_score=0.85,
            )
            for prop, handle, att in rows
        ]
