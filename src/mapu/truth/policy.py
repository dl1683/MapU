"""TruthPolicyV1.1 — epistemic truth computation engine.

Ordering:
1. Check retraction first.
2. Check non-retraction supersession second.
3. Fetch accepted, non-invalidated evidence.
4. Return unknown if empty.
5. Compute stance groups.
6. Apply authority override.
7. Apply five-dimension dominance.
8. Return accepted/denied/contested/reported/unknown.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from mapu.types import Stance, TruthBasisRole, TruthStatus


@dataclass(frozen=True)
class EvidenceRecord:
    attestation_id: uuid.UUID
    stance: Stance
    extraction_confidence: float
    attestation_strength: str | None
    authority_score: float
    attestation_type: str | None
    document_type: str | None
    publication_context: str | None
    independence_group: str | None


@dataclass(frozen=True)
class TruthBasisRef:
    attestation_id: uuid.UUID
    role: TruthBasisRole


@dataclass(frozen=True)
class TruthResult:
    status: TruthStatus
    basis: tuple[TruthBasisRef, ...]
    basis_hash: str
    reason: str


class TruthEvidenceProvider(Protocol):
    async def accepted_attestations(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID
    ) -> Sequence[EvidenceRecord]: ...

    async def is_retracted(self, proposition_id: uuid.UUID) -> bool: ...

    async def is_superseded(self, proposition_id: uuid.UUID) -> bool: ...


@dataclass(frozen=True)
class EvidenceStrength:
    max_authority: float
    independent_source_count: int
    best_extraction_confidence: float
    has_direct_statement: bool
    has_first_party_non_self_serving: bool

    def dominates(
        self,
        other: EvidenceStrength,
        authority_margin: float,
        confidence_margin: float,
        min_dimensions: int,
    ) -> bool:
        wins = 0
        if self.max_authority > other.max_authority + authority_margin:
            wins += 1
        if self.independent_source_count > other.independent_source_count:
            wins += 1
        if self.best_extraction_confidence > other.best_extraction_confidence + confidence_margin:
            wins += 1
        if self.has_direct_statement and not other.has_direct_statement:
            wins += 1
        if self.has_first_party_non_self_serving and not other.has_first_party_non_self_serving:
            wins += 1
        return wins >= min_dimensions


# Override truth adjudication, not document trustworthiness.
AUTHORITY_OVERRIDE_CLASSES: dict[str, float] = {
    "retraction_notice": 0.97,
    "court_order": 0.95,
    "statutory_text": 0.95,
    "statute": 0.95,
    "regulation": 0.93,
    "regulatory_ruling": 0.93,
}


@dataclass(frozen=True)
class TruthPolicyConfig:
    authority_margin: float = 0.15
    extraction_confidence_margin: float = 0.10
    min_dominance_dimensions: int = 3
    version: str = "v1.1"


class TruthPolicyV1:
    def __init__(self, config: TruthPolicyConfig | None = None) -> None:
        self.config = config or TruthPolicyConfig()

    async def compute(
        self,
        proposition_id: uuid.UUID,
        situation_id: uuid.UUID,
        provider: TruthEvidenceProvider,
    ) -> TruthResult:
        # 1. Check retraction first
        if await provider.is_retracted(proposition_id):
            return TruthResult(TruthStatus.RETRACTED, (), self._hash([]), "retracted")

        # 2. Check supersession
        if await provider.is_superseded(proposition_id):
            return TruthResult(TruthStatus.SUPERSEDED, (), self._hash([]), "superseded")

        # 3. Fetch accepted, non-invalidated evidence
        evidence = await provider.accepted_attestations(proposition_id, situation_id)

        # 4. Empty evidence = unknown
        if not evidence:
            return TruthResult(TruthStatus.UNKNOWN, (), self._hash([]), "no_evidence")

        # 5. Group by stance
        asserting = [e for e in evidence if e.stance == Stance.ASSERTS]
        denying = [e for e in evidence if e.stance == Stance.DENIES]
        reporting = [e for e in evidence if e.stance == Stance.REPORTS]

        # No opposition cases
        if asserting and not denying:
            basis = tuple(
                TruthBasisRef(e.attestation_id, TruthBasisRole.SUPPORTING) for e in asserting
            )
            h = self._hash(evidence)
            return TruthResult(TruthStatus.ACCEPTED, basis, h, "uncontested_assert")

        if denying and not asserting:
            basis = tuple(
                TruthBasisRef(e.attestation_id, TruthBasisRole.SUPPORTING) for e in denying
            )
            return TruthResult(TruthStatus.DENIED, basis, self._hash(evidence), "uncontested_deny")

        # Opposition: apply authority override then dominance
        if asserting and denying:
            return self._resolve_opposition(asserting, denying, evidence)

        # Reports only
        if reporting:
            basis = tuple(
                TruthBasisRef(e.attestation_id, TruthBasisRole.NEUTRAL) for e in reporting
            )
            return TruthResult(TruthStatus.REPORTED, basis, self._hash(evidence), "reports_only")

        return TruthResult(TruthStatus.UNKNOWN, (), self._hash(evidence), "no_decisive_stance")

    def _resolve_opposition(
        self,
        asserting: list[EvidenceRecord],
        denying: list[EvidenceRecord],
        all_evidence: Sequence[EvidenceRecord],
    ) -> TruthResult:
        # 6. Authority override check
        a_class = self._highest_authority_class(asserting)
        d_class = self._highest_authority_class(denying)

        h = self._hash(all_evidence)

        if a_class and (
            not d_class
            or AUTHORITY_OVERRIDE_CLASSES[a_class] > AUTHORITY_OVERRIDE_CLASSES.get(d_class, 0)
        ):
            basis = self._opposition_basis(asserting, denying)
            reason = f"authority_override:{a_class}"
            return TruthResult(TruthStatus.ACCEPTED, basis, h, reason)

        if d_class and (
            not a_class
            or AUTHORITY_OVERRIDE_CLASSES[d_class] > AUTHORITY_OVERRIDE_CLASSES.get(a_class, 0)
        ):
            basis = self._opposition_basis(denying, asserting)
            reason = f"authority_override:{d_class}"
            return TruthResult(TruthStatus.DENIED, basis, h, reason)

        # 7. Five-dimension dominance
        a_strength = self._evidence_strength(asserting)
        d_strength = self._evidence_strength(denying)

        if a_strength.dominates(
            d_strength,
            self.config.authority_margin,
            self.config.extraction_confidence_margin,
            self.config.min_dominance_dimensions,
        ):
            basis = self._opposition_basis(asserting, denying)
            return TruthResult(TruthStatus.ACCEPTED, basis, h, "dominance_assert")

        if d_strength.dominates(
            a_strength,
            self.config.authority_margin,
            self.config.extraction_confidence_margin,
            self.config.min_dominance_dimensions,
        ):
            basis = self._opposition_basis(denying, asserting)
            return TruthResult(TruthStatus.DENIED, basis, h, "dominance_deny")

        # Neither dominates
        basis = self._opposition_basis(asserting, denying)
        return TruthResult(TruthStatus.CONTESTED, basis, h, "no_dominance")

    def _highest_authority_class(self, evidence: list[EvidenceRecord]) -> str | None:
        best_class: str | None = None
        best_score = 0.0
        for e in evidence:
            for field_val in (e.document_type, e.publication_context):
                if field_val and field_val in AUTHORITY_OVERRIDE_CLASSES:
                    score = AUTHORITY_OVERRIDE_CLASSES[field_val]
                    if score > best_score:
                        best_score = score
                        best_class = field_val
        return best_class

    def _evidence_strength(self, evidence: list[EvidenceRecord]) -> EvidenceStrength:
        independent_sources: set[str | uuid.UUID] = set()
        for e in evidence:
            group = e.independence_group if e.independence_group else e.attestation_id
            independent_sources.add(group)

        return EvidenceStrength(
            max_authority=max(e.authority_score for e in evidence),
            independent_source_count=len(independent_sources),
            best_extraction_confidence=max(e.extraction_confidence for e in evidence),
            has_direct_statement=any(
                e.attestation_strength == "direct_statement" for e in evidence
            ),
            has_first_party_non_self_serving=any(
                e.attestation_type == "first_party" and e.attestation_strength != "allegation"
                for e in evidence
            ),
        )

    def _opposition_basis(
        self,
        winning: list[EvidenceRecord],
        losing: list[EvidenceRecord],
    ) -> tuple[TruthBasisRef, ...]:
        return tuple(
            [TruthBasisRef(e.attestation_id, TruthBasisRole.SUPPORTING) for e in winning]
            + [TruthBasisRef(e.attestation_id, TruthBasisRole.CONTRADICTING) for e in losing]
        )

    def _hash(self, evidence: Sequence[EvidenceRecord]) -> str:
        ids = sorted(str(e.attestation_id) for e in evidence)
        return hashlib.sha256("|".join(ids).encode()).hexdigest()[:16]
