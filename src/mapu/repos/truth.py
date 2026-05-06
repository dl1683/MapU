"""Truth state repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text, update

from mapu.models.truth import PropositionState, PropositionStateBasis
from mapu.repos.base import CorpusScopedRepo


class TruthStateRepo(CorpusScopedRepo[PropositionState]):
    model = PropositionState

    async def current(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID
    ) -> PropositionState | None:
        stmt = select(PropositionState).where(
            PropositionState.proposition_id == proposition_id,
            PropositionState.situation_id == situation_id,
            PropositionState.corpus_id == self.corpus_id,
            func.upper(PropositionState.effective_range).is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def close_current(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID
    ) -> None:
        """Close the current open state by setting upper bound of effective_range."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(PropositionState)
            .where(
                PropositionState.proposition_id == proposition_id,
                PropositionState.situation_id == situation_id,
                PropositionState.corpus_id == self.corpus_id,
                func.upper(PropositionState.effective_range).is_(None),
            )
            .values(effective_range=text(f"tstzrange(lower(effective_range), '{now.isoformat()}'::timestamptz, '[)')"))
        )
        await self.session.execute(stmt)

    async def insert_current(self, state: PropositionState) -> PropositionState:
        return await self.add(state)

    async def write_basis(
        self,
        state_id: uuid.UUID,
        basis: list[tuple[uuid.UUID, str]],
    ) -> None:
        for attestation_id, role in basis:
            row = PropositionStateBasis(
                state_id=state_id,
                attestation_id=attestation_id,
                corpus_id=self.corpus_id,
                role=role,
            )
            self.session.add(row)
        await self.session.flush()
