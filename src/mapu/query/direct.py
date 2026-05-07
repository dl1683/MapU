"""Tier 0: Direct state lookup — pure SQL, no LLM, no embeddings."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from mapu.models.attestation import Attestation
from mapu.models.entity import Handle
from mapu.models.proposition import Proposition
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
        hits: list[PropositionHit] = []

        for entity_text in plan.entities_extracted:
            results = await self._lookup_by_entity(
                entity_text, request.corpus_id, request.max_results,
            )
            hits.extend(results)

        if not hits and plan.predicates_extracted:
            for predicate in plan.predicates_extracted:
                results = await self._lookup_by_predicate(
                    predicate, request.corpus_id, request.max_results,
                )
                hits.extend(results)

        seen: set[uuid.UUID] = set()
        deduped: list[PropositionHit] = []
        for hit in hits:
            if hit.proposition_id not in seen:
                seen.add(hit.proposition_id)
                deduped.append(hit)

        return deduped[: request.max_results]

    async def _lookup_by_entity(
        self, entity_text: str, corpus_id: uuid.UUID, limit: int,
    ) -> list[PropositionHit]:
        stmt = (
            select(Proposition, Handle, Attestation)
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
            )
            .join(Handle, Proposition.subject_handle_id == Handle.id)
            .join(
                Attestation,
                (Attestation.proposition_id == Proposition.id)
                & (Attestation.corpus_id == Proposition.corpus_id),
            )
            .where(
                Proposition.corpus_id == corpus_id,
                Handle.canonical_name.ilike(f"%{_escape_like(entity_text)}%"),
                Attestation.status == "accepted",
                Attestation.system_invalidated.is_(None),
            )
            .limit(limit)
        )
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
                relevance_score=1.0,
            )
            for prop, handle, att in rows
        ]

    async def _lookup_by_predicate(
        self, predicate: str, corpus_id: uuid.UUID, limit: int,
    ) -> list[PropositionHit]:
        stmt = (
            select(Proposition, Handle, Attestation)
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
            )
            .join(Handle, Proposition.subject_handle_id == Handle.id)
            .join(
                Attestation,
                (Attestation.proposition_id == Proposition.id)
                & (Attestation.corpus_id == Proposition.corpus_id),
            )
            .where(
                Proposition.corpus_id == corpus_id,
                Proposition.predicate.ilike(f"%{_escape_like(predicate)}%"),
                Attestation.status == "accepted",
                Attestation.system_invalidated.is_(None),
            )
            .limit(limit)
        )
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
                relevance_score=0.9,
            )
            for prop, handle, att in rows
        ]
