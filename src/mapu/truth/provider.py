"""Production TruthEvidenceProvider backed by the database."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.attestation import Attestation, AttestationSituation
from mapu.models.authority import SourcePolicyEval
from mapu.truth.policy import EvidenceRecord


class DbTruthEvidenceProvider:
    """Implements TruthEvidenceProvider against the real database.

    Fetches accepted, non-invalidated attestations for a given proposition
    scoped to a situation, joining SourcePolicyEval for authority metadata.
    """

    def __init__(self, session: AsyncSession, corpus_id: uuid.UUID) -> None:
        self._session = session
        self._corpus_id = corpus_id

    async def accepted_attestations(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID,
    ) -> Sequence[EvidenceRecord]:
        stmt = (
            select(Attestation, SourcePolicyEval)
            .join(
                AttestationSituation,
                (AttestationSituation.attestation_id == Attestation.id)
                & (AttestationSituation.corpus_id == Attestation.corpus_id),
            )
            .outerjoin(
                SourcePolicyEval,
                Attestation.source_policy_eval_id == SourcePolicyEval.id,
            )
            .where(
                Attestation.proposition_id == proposition_id,
                Attestation.corpus_id == self._corpus_id,
                Attestation.status == "accepted",
                Attestation.system_invalidated.is_(None),
                AttestationSituation.situation_id == situation_id,
                AttestationSituation.invalidated_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            EvidenceRecord(
                attestation_id=att.id,
                stance=att.stance,
                extraction_confidence=att.extraction_confidence,
                attestation_strength=att.attestation_strength,
                authority_score=spe.authority_score if spe else 0.5,
                attestation_type=spe.attestation_type if spe else None,
                document_type=spe.document_type if spe else None,
                publication_context=spe.publication_context if spe else None,
                independence_group=spe.independence_group if spe else None,
            )
            for att, spe in rows
        ]

    async def is_retracted(self, proposition_id: uuid.UUID) -> bool:
        from mapu.models.lineage import SupersessionEdge

        stmt = select(SupersessionEdge.id).where(
            SupersessionEdge.old_proposition_id == proposition_id,
            SupersessionEdge.corpus_id == self._corpus_id,
            SupersessionEdge.supersession_type == "retraction",
        ).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def is_superseded(self, proposition_id: uuid.UUID) -> bool:
        from mapu.models.lineage import SupersessionEdge

        stmt = select(SupersessionEdge.id).where(
            SupersessionEdge.old_proposition_id == proposition_id,
            SupersessionEdge.corpus_id == self._corpus_id,
        ).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
