"""Unit tests for TruthPolicyV1.1."""

from __future__ import annotations

import uuid

import pytest

from mapu.truth.policy import EvidenceStrength, TruthPolicyConfig, TruthPolicyV1
from mapu.types import Stance, TruthStatus
from tests.conftest import InMemoryTruthEvidenceProvider, make_evidence

PROP = uuid.uuid4()
SIT = uuid.uuid4()


@pytest.fixture
def policy() -> TruthPolicyV1:
    return TruthPolicyV1(TruthPolicyConfig())


@pytest.fixture
def provider() -> InMemoryTruthEvidenceProvider:
    return InMemoryTruthEvidenceProvider()


class TestRetractedFirst:
    async def test_retracted_before_evidence(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [make_evidence()])
        provider.mark_retracted(PROP)
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.RETRACTED

    async def test_retracted_before_superseded(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.mark_retracted(PROP)
        provider.mark_superseded(PROP)
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.RETRACTED

    async def test_superseded_before_evidence(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [make_evidence()])
        provider.mark_superseded(PROP)
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.SUPERSEDED


class TestNoEvidence:
    async def test_no_evidence_returns_unknown(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.UNKNOWN
        assert result.reason == "no_evidence"


class TestUncontested:
    async def test_single_assert_accepted(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [make_evidence(Stance.ASSERTS)])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.ACCEPTED
        assert len(result.basis) == 1

    async def test_multiple_asserts_accepted(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.ASSERTS, authority_score=0.8),
            make_evidence(Stance.ASSERTS, authority_score=0.6),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.ACCEPTED

    async def test_single_deny_denied(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [make_evidence(Stance.DENIES)])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.DENIED

    async def test_reports_only_reported(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.REPORTS, authority_score=0.25),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.REPORTED


class TestOpposition:
    async def test_equal_strength_contested(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """Two roughly equal sources, one asserting one denying -> contested."""
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.ASSERTS, authority_score=0.65, independence_group="a"),
            make_evidence(Stance.DENIES, authority_score=0.70, independence_group="b"),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.CONTESTED

    async def test_dominant_assert_accepted(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """Strong asserting evidence dominates weak denial."""
        provider.add_evidence(PROP, SIT, [
            make_evidence(
                Stance.ASSERTS, authority_score=0.90,
                extraction_confidence=0.95,
                attestation_strength="direct_statement",
                attestation_type="first_party",
                independence_group="a",
            ),
            make_evidence(
                Stance.ASSERTS, authority_score=0.85,
                independence_group="b",
            ),
            make_evidence(
                Stance.ASSERTS, authority_score=0.80,
                independence_group="c",
            ),
            make_evidence(
                Stance.DENIES, authority_score=0.40,
                extraction_confidence=0.6,
                attestation_strength="allegation",
                attestation_type="self_reported",
                independence_group="d",
            ),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.ACCEPTED


class TestAuthorityOverride:
    async def test_court_order_overrides(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """A court_order denial overrides multiple weak assertions."""
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.ASSERTS, authority_score=0.5, independence_group="a"),
            make_evidence(Stance.ASSERTS, authority_score=0.5, independence_group="b"),
            make_evidence(Stance.ASSERTS, authority_score=0.5, independence_group="c"),
            make_evidence(
                Stance.DENIES, authority_score=0.85,
                document_type="court_order",
                independence_group="court",
            ),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.DENIED
        assert "authority_override" in result.reason

    async def test_retraction_notice_overrides(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.ASSERTS, authority_score=0.80, independence_group="study"),
            make_evidence(
                Stance.DENIES, authority_score=0.70,
                document_type="retraction_notice",
                independence_group="journal",
            ),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.DENIED

    async def test_equal_override_classes_fall_through(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """When both sides have same-tier override classes, fall through to dominance."""
        provider.add_evidence(PROP, SIT, [
            make_evidence(
                Stance.ASSERTS, authority_score=0.85,
                document_type="court_order", independence_group="court_a",
            ),
            make_evidence(
                Stance.DENIES, authority_score=0.85,
                document_type="court_order", independence_group="court_b",
            ),
        ])
        result = await policy.compute(PROP, SIT, provider)
        # Equal override classes -> falls to dominance -> contested (tied)
        assert result.status == TruthStatus.CONTESTED


class TestEvidenceStrengthDominance:
    def test_dominates_3_of_5(self) -> None:
        strong = EvidenceStrength(
            max_authority=0.9,
            independent_source_count=3,
            best_extraction_confidence=0.95,
            has_direct_statement=True,
            has_first_party_non_self_serving=True,
        )
        weak = EvidenceStrength(
            max_authority=0.5,
            independent_source_count=1,
            best_extraction_confidence=0.6,
            has_direct_statement=False,
            has_first_party_non_self_serving=False,
        )
        assert strong.dominates(weak, 0.15, 0.10, 3)
        assert not weak.dominates(strong, 0.15, 0.10, 3)

    def test_authority_within_margin_no_win(self) -> None:
        a = EvidenceStrength(0.80, 1, 0.9, True, True)
        b = EvidenceStrength(0.70, 1, 0.9, True, True)
        # Difference is 0.10 < margin 0.15, so authority is not a win
        assert not a.dominates(b, 0.15, 0.10, 3)


class TestHardExamples:
    """Validate truth policy against key hard examples from the design."""

    async def test_l1_conditional_obligation_accepted(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """L1: Single contract clause, asserts stance -> accepted."""
        prop = uuid.uuid4()
        sit = uuid.uuid4()
        provider.add_evidence(prop, sit, [
            make_evidence(Stance.ASSERTS, authority_score=0.88),
        ])
        result = await policy.compute(prop, sit, provider)
        assert result.status == TruthStatus.ACCEPTED

    async def test_b2_conflicting_studies_contested(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """B2: Two conflicting RCTs with similar authority -> contested."""
        prop = uuid.uuid4()
        sit = uuid.uuid4()
        provider.add_evidence(prop, sit, [
            make_evidence(
                Stance.ASSERTS, authority_score=0.65,
                extraction_confidence=0.85,
                attestation_strength="direct_statement",
                attestation_type="peer_reviewed",
                independence_group="study_a",
            ),
            make_evidence(
                Stance.DENIES, authority_score=0.78,
                extraction_confidence=0.85,
                attestation_strength="direct_statement",
                attestation_type="peer_reviewed",
                independence_group="study_b",
            ),
        ])
        result = await policy.compute(prop, sit, provider)
        assert result.status == TruthStatus.CONTESTED

    async def test_i3_adversarial_disinformation_reported(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """I3: State media with reports stance -> reported."""
        prop = uuid.uuid4()
        sit = uuid.uuid4()
        provider.add_evidence(prop, sit, [
            make_evidence(Stance.REPORTS, authority_score=0.25),
        ])
        result = await policy.compute(prop, sit, provider)
        assert result.status == TruthStatus.REPORTED

    async def test_b5_retraction_retracted(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """B5: Retracted study -> retracted status."""
        prop = uuid.uuid4()
        sit = uuid.uuid4()
        provider.add_evidence(prop, sit, [make_evidence(Stance.ASSERTS, authority_score=0.80)])
        provider.mark_retracted(prop)
        result = await policy.compute(prop, sit, provider)
        assert result.status == TruthStatus.RETRACTED

    async def test_f2_guidance_vs_actual_separate_situations(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """F2: Guidance and actual are in different situations, no conflict."""
        prop_guidance = uuid.uuid4()
        prop_actual = uuid.uuid4()
        sit_guidance = uuid.uuid4()
        sit_actual = uuid.uuid4()

        provider.add_evidence(prop_guidance, sit_guidance, [
            make_evidence(Stance.REPORTS, authority_score=0.60),
        ])
        provider.add_evidence(prop_actual, sit_actual, [
            make_evidence(Stance.ASSERTS, authority_score=0.85),
        ])

        result_guidance = await policy.compute(prop_guidance, sit_guidance, provider)
        result_actual = await policy.compute(prop_actual, sit_actual, provider)

        assert result_guidance.status == TruthStatus.REPORTED
        assert result_actual.status == TruthStatus.ACCEPTED


class TestNeutralStances:
    """Questions and conditions stances should not create truth on their own."""

    async def test_questions_only_unknown(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.QUESTIONS, authority_score=0.70),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.UNKNOWN

    async def test_conditions_only_unknown(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.CONDITIONS, authority_score=0.80),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.UNKNOWN

    async def test_assert_plus_questions_accepted(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """Questions should not oppose assertions."""
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.ASSERTS, authority_score=0.80),
            make_evidence(Stance.QUESTIONS, authority_score=0.70),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.ACCEPTED

    async def test_assert_plus_conditions_accepted(
        self, policy: TruthPolicyV1, provider: InMemoryTruthEvidenceProvider
    ) -> None:
        """Conditions should not oppose assertions."""
        provider.add_evidence(PROP, SIT, [
            make_evidence(Stance.ASSERTS, authority_score=0.80),
            make_evidence(Stance.CONDITIONS, authority_score=0.80),
        ])
        result = await policy.compute(PROP, SIT, provider)
        assert result.status == TruthStatus.ACCEPTED
