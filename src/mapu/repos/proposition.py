"""Proposition repository with semantic key dedup and state management."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from mapu.models.proposition import Proposition, PropositionParticipant
from mapu.models.truth import PropositionState
from mapu.repos.base import CorpusScopedRepo


class PropositionRepo(CorpusScopedRepo[Proposition]):
    model = Proposition

    async def get_by_semantic_key(self, semantic_key: str) -> Proposition | None:
        stmt = select(Proposition).where(
            Proposition.corpus_id == self.corpus_id,
            Proposition.semantic_key == semantic_key,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_participant(
        self,
        proposition_id: uuid.UUID,
        handle_id: uuid.UUID,
        role: str,
        ordinal: int = 0,
    ) -> PropositionParticipant:
        pp = PropositionParticipant(
            proposition_id=proposition_id,
            handle_id=handle_id,
            corpus_id=self.corpus_id,
            role=role,
            ordinal=ordinal,
        )
        self.session.add(pp)
        await self.session.flush()
        return pp

    async def current_state(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID
    ) -> PropositionState | None:
        from sqlalchemy import func

        stmt = select(PropositionState).where(
            PropositionState.proposition_id == proposition_id,
            PropositionState.situation_id == situation_id,
            PropositionState.corpus_id == self.corpus_id,
            func.upper(PropositionState.effective_range).is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
