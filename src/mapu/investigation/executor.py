"""Non-LLM investigation action executor."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.investigation.types import (
    ActionKind,
    InvestigationAction,
    InvestigationState,
    Observation,
)
from mapu.query.structured import StructuredQueryExecutor
from mapu.query.types import (
    PropositionHit,
    QueryIntent,
    QueryPlan,
    QueryRequest,
    Tier,
)

_ACTION_TO_INTENT: dict[ActionKind, QueryIntent] = {
    ActionKind.STRUCTURED_QUERY: QueryIntent.LIST,
    ActionKind.ENTITY_LOOKUP: QueryIntent.IDENTITY,
    ActionKind.TEMPORAL_DIFF: QueryIntent.TEMPORAL_DIFF,
    ActionKind.GAP_CHECK: QueryIntent.GAP,
}


class InvestigationExecutor:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._structured = StructuredQueryExecutor(session)

    async def execute_action(
        self,
        action: InvestigationAction,
        corpus_id: uuid.UUID,
        state: InvestigationState,
    ) -> Observation:
        if action.kind in (
            ActionKind.STRUCTURED_QUERY,
            ActionKind.ENTITY_LOOKUP,
            ActionKind.TEMPORAL_DIFF,
            ActionKind.GAP_CHECK,
        ):
            return await self._execute_structured(action, corpus_id, state)

        if action.kind == ActionKind.EMBEDDING_SEARCH:
            return await self._execute_embedding(action, corpus_id, state)

        if action.kind == ActionKind.CHUNK_RETRIEVAL:
            return await self._execute_chunk(action, corpus_id, state)

        return Observation(action=action)

    async def _execute_structured(
        self,
        action: InvestigationAction,
        corpus_id: uuid.UUID,
        state: InvestigationState,
    ) -> Observation:
        intent = _ACTION_TO_INTENT.get(action.kind, QueryIntent.LIST)
        plan = QueryPlan(
            intent=intent,
            selected_tier=Tier.STRUCTURED,
            entities_extracted=action.entities,
            predicates_extracted=action.predicates,
        )
        request = QueryRequest(corpus_id=corpus_id, question=action.query)
        hits = await self._structured.execute(plan, request)

        state.actions_executed += 1
        new_ids = tuple(
            h.proposition_id for h in hits
            if h.proposition_id not in state.seen_proposition_ids
        )
        state.seen_proposition_ids.update(new_ids)

        return Observation(
            action=action,
            proposition_ids_found=new_ids,
            new_entities_discovered=_extract_new_entities(hits, action.entities),
            span_texts=tuple(
                h.source_span_text for h in hits if h.source_span_text
            ),
        )

    async def _execute_embedding(
        self,
        action: InvestigationAction,
        corpus_id: uuid.UUID,
        state: InvestigationState,
    ) -> Observation:
        state.actions_executed += 1
        return Observation(action=action)

    async def _execute_chunk(
        self,
        action: InvestigationAction,
        corpus_id: uuid.UUID,
        state: InvestigationState,
    ) -> Observation:
        state.actions_executed += 1
        return Observation(action=action)


def _extract_new_entities(
    hits: Sequence[PropositionHit], known: tuple[str, ...],
) -> tuple[str, ...]:
    known_lower = {e.lower() for e in known}
    new: list[str] = []
    seen: set[str] = set()
    for h in hits:
        for name in (h.subject_name, h.object_name):
            if name and name.lower() not in known_lower and name not in seen:
                seen.add(name)
                new.append(name)
    return tuple(new)
