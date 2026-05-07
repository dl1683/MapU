"""Tier 1: Structured query execution — parameterized SQL, no LLM."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, null, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, load_only

from mapu.models.attestation import Attestation
from mapu.models.authority import SourcePolicyEval
from mapu.models.entity import Handle
from mapu.models.evidence import TextSpan
from mapu.models.proposition import Proposition
from mapu.models.truth import PropositionState
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
        stmt = self._base_query(request.corpus_id, request.situation_id)
        has_filter = False
        if plan.predicates_extracted:
            predicates = plan.predicates_extracted
            stmt = stmt.where(
                Proposition.predicate.ilike(f"%{_escape_like(predicates[0])}%")
            )
            has_filter = True
        if plan.entities_extracted:
            stmt = stmt.where(
                Handle.canonical_name.ilike(f"%{_escape_like(plan.entities_extracted[0])}%")
            )
            has_filter = True
        if has_filter:
            stmt = stmt.order_by(
                SourcePolicyEval.authority_score.desc().nulls_last(),
                Proposition.system_created.desc(),
            )
        else:
            stmt = stmt.order_by(Proposition.system_created.desc())
        stmt = stmt.limit(request.max_results)
        return await self._fetch(stmt)

    async def _execute_temporal(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> list[PropositionHit]:
        stmt = self._base_query(request.corpus_id, request.situation_id)
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

        stmt = self._base_query(request.corpus_id, request.situation_id)
        stmt = stmt.join(
            SupersessionEdge,
            (
                (SupersessionEdge.old_proposition_id == Proposition.id)
                | (SupersessionEdge.new_proposition_id == Proposition.id)
            )
            & (SupersessionEdge.corpus_id == Proposition.corpus_id),
        )
        if plan.entities_extracted:
            stmt = stmt.where(
                Handle.canonical_name.ilike(f"%{_escape_like(plan.entities_extracted[0])}%")
            )
        if plan.predicates_extracted:
            stmt = stmt.where(
                Proposition.predicate.ilike(f"%{_escape_like(plan.predicates_extracted[0])}%")
            )
        stmt = stmt.order_by(
            SourcePolicyEval.authority_score.desc().nulls_last(),
        ).limit(request.max_results)
        return await self._fetch(stmt)

    async def _execute_measurement(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> list[PropositionHit]:
        from mapu.types import FrameType

        stmt = self._base_query(request.corpus_id, request.situation_id).where(
            Proposition.frame_type.in_([
                FrameType.MEASUREMENT.value,
                FrameType.THRESHOLD.value,
            ])
        )
        if plan.entities_extracted:
            entity = plan.entities_extracted[0]
            if entity[0].isupper():
                stmt = stmt.where(
                    Handle.canonical_name.ilike(f"%{_escape_like(entity)}%")
                )
            else:
                stmt = stmt.where(
                    Proposition.normalized_text.ilike(f"%{_escape_like(entity)}%")
                )
        if plan.predicates_extracted:
            stmt = stmt.where(
                Proposition.predicate.ilike(f"%{_escape_like(plan.predicates_extracted[0])}%")
            )
        stmt = stmt.order_by(
            SourcePolicyEval.authority_score.desc().nulls_last(),
        ).limit(request.max_results)
        return await self._fetch(stmt)

    async def _execute_generic(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> list[PropositionHit]:
        if not plan.entities_extracted and not plan.predicates_extracted:
            return []
        stmt = self._base_query(request.corpus_id, request.situation_id)
        if plan.entities_extracted:
            stmt = stmt.where(
                Handle.canonical_name.ilike(f"%{_escape_like(plan.entities_extracted[0])}%")
            )
        if plan.predicates_extracted:
            stmt = stmt.where(
                Proposition.predicate.ilike(f"%{_escape_like(plan.predicates_extracted[0])}%")
            )
        stmt = stmt.order_by(
            SourcePolicyEval.authority_score.desc().nulls_last(),
            Attestation.extraction_confidence.desc(),
        ).limit(request.max_results)
        return await self._fetch(stmt)

    def _base_query(
        self, corpus_id: uuid.UUID, situation_id: uuid.UUID | None = None,
    ) -> Any:
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
                    Proposition.system_created, Proposition.valid_range,
                ),
                load_only(
                    Handle.id, Handle.canonical_name, Handle.kind,
                ),
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

        return stmt.where(
            Proposition.corpus_id == corpus_id,
            Attestation.status == "accepted",
            Attestation.system_invalidated.is_(None),
        )

    async def _fetch(self, stmt: Any) -> list[PropositionHit]:
        result = await self._session.execute(stmt)
        rows = result.all()
        seen: set[uuid.UUID] = set()
        hits: list[PropositionHit] = []
        for prop, handle, att, spe, span, obj_handle, truth_status in rows:
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
                object_name=obj_handle.canonical_name if obj_handle else None,
                object_kind=obj_handle.kind if obj_handle else None,
                truth_status=truth_status,
                extraction_confidence=att.extraction_confidence,
                authority_score=spe.authority_score if spe else None,
                source_span_text=span.text if span else None,
                relevance_score=0.85,
            ))
        return hits
