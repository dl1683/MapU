"""Shared test fixtures."""

from __future__ import annotations

import uuid

import pytest

from mapu.truth.policy import EvidenceRecord, TruthEvidenceProvider, TruthPolicyConfig, TruthPolicyV1
from mapu.types import Stance


class InMemoryTruthEvidenceProvider:
    """In-memory evidence provider for unit testing truth policy without DB."""

    def __init__(self) -> None:
        self._evidence: dict[tuple[uuid.UUID, uuid.UUID], list[EvidenceRecord]] = {}
        self._retracted: set[uuid.UUID] = set()
        self._superseded: set[uuid.UUID] = set()

    def add_evidence(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID, records: list[EvidenceRecord]
    ) -> None:
        self._evidence[(proposition_id, situation_id)] = records

    def mark_retracted(self, proposition_id: uuid.UUID) -> None:
        self._retracted.add(proposition_id)

    def mark_superseded(self, proposition_id: uuid.UUID) -> None:
        self._superseded.add(proposition_id)

    async def accepted_attestations(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID
    ) -> list[EvidenceRecord]:
        return self._evidence.get((proposition_id, situation_id), [])

    async def is_retracted(self, proposition_id: uuid.UUID) -> bool:
        return proposition_id in self._retracted

    async def is_superseded(self, proposition_id: uuid.UUID) -> bool:
        return proposition_id in self._superseded


@pytest.fixture
def evidence_provider() -> InMemoryTruthEvidenceProvider:
    return InMemoryTruthEvidenceProvider()


@pytest.fixture
def truth_policy() -> TruthPolicyV1:
    return TruthPolicyV1(TruthPolicyConfig())


def make_evidence(
    stance: Stance = Stance.ASSERTS,
    authority_score: float = 0.7,
    extraction_confidence: float = 0.85,
    attestation_strength: str | None = "direct_statement",
    attestation_type: str | None = "first_party",
    document_type: str | None = None,
    publication_context: str | None = None,
    independence_group: str | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        attestation_id=uuid.uuid4(),
        stance=stance,
        extraction_confidence=extraction_confidence,
        attestation_strength=attestation_strength,
        authority_score=authority_score,
        attestation_type=attestation_type,
        document_type=document_type,
        publication_context=publication_context,
        independence_group=independence_group,
    )
