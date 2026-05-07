"""Truth computation service: computes and persists PropositionState."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.attestation import Attestation, AttestationSituation
from mapu.models.truth import PropositionState, PropositionStateBasis
from mapu.truth.policy import TruthPolicyV1, TruthResult
from mapu.truth.provider import DbTruthEvidenceProvider


@dataclass
class TruthComputeResult:
    proposition_id: uuid.UUID
    situation_id: uuid.UUID
    truth_result: TruthResult
    state_id: uuid.UUID
    changed: bool


class TruthComputeService:
    """Computes truth status for propositions and persists the result."""

    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        policy: TruthPolicyV1 | None = None,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id
        self._policy = policy or TruthPolicyV1()
        self._provider = DbTruthEvidenceProvider(session, corpus_id)

    async def compute_and_persist(
        self,
        proposition_id: uuid.UUID,
        situation_id: uuid.UUID,
    ) -> TruthComputeResult:
        truth = await self._policy.compute(
            proposition_id, situation_id, self._provider,
        )

        existing = await self._current_state(proposition_id, situation_id)

        if existing and existing.basis_hash == truth.basis_hash:
            return TruthComputeResult(
                proposition_id=proposition_id,
                situation_id=situation_id,
                truth_result=truth,
                state_id=existing.id,
                changed=False,
            )

        state = PropositionState(
            proposition_id=proposition_id,
            situation_id=situation_id,
            corpus_id=self._corpus_id,
            truth_status=truth.status.value,
            truth_policy_version=self._policy.config.version,
            effective_range=text("tstzrange(now(), NULL)"),
            basis_hash=truth.basis_hash,
        )
        self._session.add(state)
        await self._session.flush()

        for ref in truth.basis:
            basis = PropositionStateBasis(
                state_id=state.id,
                attestation_id=ref.attestation_id,
                corpus_id=self._corpus_id,
                role=ref.role.value,
            )
            self._session.add(basis)
        await self._session.flush()

        return TruthComputeResult(
            proposition_id=proposition_id,
            situation_id=situation_id,
            truth_result=truth,
            state_id=state.id,
            changed=True,
        )

    async def recompute_for_proposition(
        self,
        proposition_id: uuid.UUID,
        situation_ids: list[uuid.UUID] | None = None,
    ) -> list[TruthComputeResult]:
        if situation_ids is None:
            situation_ids = await self._situations_for_proposition(proposition_id)

        results = []
        for sid in situation_ids:
            r = await self.compute_and_persist(proposition_id, sid)
            results.append(r)
        return results

    async def _current_state(
        self,
        proposition_id: uuid.UUID,
        situation_id: uuid.UUID,
    ) -> PropositionState | None:
        stmt = (
            select(PropositionState)
            .where(
                PropositionState.proposition_id == proposition_id,
                PropositionState.situation_id == situation_id,
                PropositionState.corpus_id == self._corpus_id,
            )
            .order_by(PropositionState.computed_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _situations_for_proposition(
        self, proposition_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        stmt = (
            select(AttestationSituation.situation_id)
            .join(
                Attestation,
                (AttestationSituation.attestation_id == Attestation.id)
                & (AttestationSituation.corpus_id == Attestation.corpus_id),
            )
            .where(
                Attestation.proposition_id == proposition_id,
                Attestation.corpus_id == self._corpus_id,
            )
            .distinct()
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]
