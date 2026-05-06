"""Attestation repository with truth-computation query support."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from mapu.models.attestation import Attestation, AttestationSituation
from mapu.repos.base import CorpusScopedRepo


class AttestationRepo(CorpusScopedRepo[Attestation]):
    model = Attestation

    async def accepted_for_truth(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID
    ) -> list[Attestation]:
        """Get accepted, non-invalidated attestations assigned to a situation."""
        stmt = (
            select(Attestation)
            .join(
                AttestationSituation,
                (AttestationSituation.attestation_id == Attestation.id)
                & (AttestationSituation.corpus_id == Attestation.corpus_id),
            )
            .where(
                Attestation.proposition_id == proposition_id,
                Attestation.corpus_id == self.corpus_id,
                Attestation.status == "accepted",
                Attestation.system_invalidated.is_(None),
                AttestationSituation.situation_id == situation_id,
                AttestationSituation.invalidated_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def accept(self, attestation_id: uuid.UUID) -> None:
        stmt = (
            update(Attestation)
            .where(Attestation.id == attestation_id, Attestation.corpus_id == self.corpus_id)
            .values(status="accepted")
        )
        await self.session.execute(stmt)

    async def reject(self, attestation_id: uuid.UUID) -> None:
        stmt = (
            update(Attestation)
            .where(Attestation.id == attestation_id, Attestation.corpus_id == self.corpus_id)
            .values(status="rejected")
        )
        await self.session.execute(stmt)

    async def quarantine(self, attestation_id: uuid.UUID) -> None:
        stmt = (
            update(Attestation)
            .where(Attestation.id == attestation_id, Attestation.corpus_id == self.corpus_id)
            .values(status="quarantined")
        )
        await self.session.execute(stmt)

    async def invalidate(self, attestation_id: uuid.UUID) -> None:
        stmt = (
            update(Attestation)
            .where(Attestation.id == attestation_id, Attestation.corpus_id == self.corpus_id)
            .values(system_invalidated=datetime.now(UTC))
        )
        await self.session.execute(stmt)

    async def assign_situation(
        self,
        attestation_id: uuid.UUID,
        situation_id: uuid.UUID,
        confidence: float,
        basis: str,
    ) -> AttestationSituation:
        assn = AttestationSituation(
            attestation_id=attestation_id,
            situation_id=situation_id,
            corpus_id=self.corpus_id,
            assignment_confidence=confidence,
            assignment_basis=basis,
        )
        self.session.add(assn)
        await self.session.flush()
        return assn
