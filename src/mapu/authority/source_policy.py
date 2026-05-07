"""Rule-based SourcePolicyEvaluatorV1 — deterministic authority scoring."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.authority import SourcePolicyEval

_DOCUMENT_TYPE_SCORES: dict[str, float] = {
    "court_opinion": 0.95,
    "court_order": 0.95,
    "statute": 0.95,
    "regulation": 0.90,
    "peer_reviewed_article": 0.88,
    "clinical_trial_report": 0.85,
    "government_filing": 0.85,
    "sec_filing": 0.85,
    "public_registry": 0.82,
    "contract": 0.78,
    "amendment": 0.78,
    "retraction_notice": 0.75,
    "cve_record": 0.72,
    "code_file": 0.60,
    "press_release": 0.55,
    "earnings_call_transcript": 0.55,
    "state_media_report": 0.40,
    "internal_document": 0.35,
    "leaked_document": 0.25,
    "other": 0.40,
}

_PUBLICATION_CONTEXT_MODIFIER: dict[str, float] = {
    "official_filing": 0.10,
    "peer_reviewed_journal": 0.10,
    "court_opinion": 0.08,
    "regulatory_bulletin": 0.05,
    "government_registry": 0.05,
    "cve_database": 0.05,
    "code_repository": 0.0,
    "press_release": -0.05,
    "earnings_call": -0.05,
    "internal_document": -0.10,
    "leaked_document": -0.15,
    "social_media": -0.20,
}

_ATTESTATION_TYPE_MODIFIER: dict[str, float] = {
    "first_party": 0.0,
    "government": 0.05,
    "peer_reviewed": 0.08,
    "expert_opinion": 0.03,
    "third_party": -0.05,
    "self_reported": -0.10,
    "hearsay": -0.20,
    "automated": -0.05,
}


@dataclass(frozen=True)
class SourcePolicyInput:
    """Input to the source policy evaluator."""

    document_type: str | None = None
    publication_context: str | None = None
    attestation_type: str | None = None
    independence_group: str | None = None
    source_identity: str | None = None


class SourcePolicyEvaluatorV1:
    """Deterministic, rule-based source authority scorer."""

    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id

    def score(self, inp: SourcePolicyInput) -> float:
        base = _DOCUMENT_TYPE_SCORES.get(inp.document_type or "unknown", 0.40)

        pub_mod = _PUBLICATION_CONTEXT_MODIFIER.get(
            inp.publication_context or "", 0.0
        )
        att_mod = _ATTESTATION_TYPE_MODIFIER.get(
            inp.attestation_type or "first_party", 0.0
        )

        raw = base + pub_mod + att_mod
        return max(0.0, min(1.0, raw))

    async def evaluate_and_persist(
        self,
        document_id: uuid.UUID,
        inp: SourcePolicyInput,
    ) -> SourcePolicyEval:
        authority_score = self.score(inp)

        spe = SourcePolicyEval(
            id=uuid.uuid4(),
            document_id=document_id,
            corpus_id=self._corpus_id,
            authority_score=authority_score,
            document_type=inp.document_type,
            publication_context=inp.publication_context,
            attestation_type=inp.attestation_type,
            independence_group=inp.independence_group,
            source_identity=inp.source_identity,
            evaluated_at=datetime.now(UTC),
        )
        self._session.add(spe)
        await self._session.flush()
        return spe
