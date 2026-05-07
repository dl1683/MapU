"""Unit tests for source policy scoring (pure logic, no DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from mapu.authority.source_policy import SourcePolicyEvaluatorV1, SourcePolicyInput


class TestSourcePolicyScoring:
    @pytest.fixture
    def evaluator(self) -> SourcePolicyEvaluatorV1:
        return SourcePolicyEvaluatorV1.__new__(SourcePolicyEvaluatorV1)

    def test_court_opinion_high(self, evaluator: SourcePolicyEvaluatorV1) -> None:
        score = evaluator.score(SourcePolicyInput(document_type="court_opinion"))
        assert score >= 0.90

    def test_leaked_document_low(self, evaluator: SourcePolicyEvaluatorV1) -> None:
        score = evaluator.score(SourcePolicyInput(document_type="leaked_document"))
        assert score <= 0.30

    def test_unknown_document_type(self, evaluator: SourcePolicyEvaluatorV1) -> None:
        score = evaluator.score(SourcePolicyInput(document_type=None))
        assert 0.30 <= score <= 0.50

    def test_publication_context_boost(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        base = evaluator.score(SourcePolicyInput(document_type="peer_reviewed_article"))
        boosted = evaluator.score(SourcePolicyInput(
            document_type="peer_reviewed_article",
            publication_context="peer_reviewed_journal",
        ))
        assert boosted > base

    def test_hearsay_penalty(self, evaluator: SourcePolicyEvaluatorV1) -> None:
        base = evaluator.score(SourcePolicyInput(document_type="press_release"))
        penalized = evaluator.score(SourcePolicyInput(
            document_type="press_release",
            attestation_type="hearsay",
        ))
        assert penalized < base

    def test_score_clamped_to_zero_one(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        score = evaluator.score(SourcePolicyInput(
            document_type="leaked_document",
            publication_context="leaked_document",
            attestation_type="hearsay",
        ))
        assert 0.0 <= score <= 1.0

    def test_government_attestation_boost(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        base = evaluator.score(SourcePolicyInput(
            document_type="government_filing",
        ))
        gov = evaluator.score(SourcePolicyInput(
            document_type="government_filing",
            attestation_type="government",
        ))
        assert gov > base

    def test_all_document_types_return_scores(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        types = [
            "court_opinion", "court_order", "statute", "regulation",
            "peer_reviewed_article", "clinical_trial_report",
            "government_filing", "sec_filing", "public_registry",
            "contract", "amendment", "retraction_notice",
            "cve_record", "code_file", "press_release",
            "earnings_call_transcript", "state_media_report",
            "internal_document", "leaked_document", "other",
        ]
        for doc_type in types:
            score = evaluator.score(SourcePolicyInput(document_type=doc_type))
            assert 0.0 <= score <= 1.0, f"Bad score for {doc_type}: {score}"


class TestSourcePolicyPersistValidation:
    @pytest.fixture
    def evaluator(self) -> SourcePolicyEvaluatorV1:
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return SourcePolicyEvaluatorV1(session, uuid.uuid4())

    async def test_unknown_document_type_uses_default_score(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        spe = await evaluator.evaluate_and_persist(
            uuid.uuid4(),
            SourcePolicyInput(document_type="invented_type"),
        )
        assert spe.authority_score == pytest.approx(0.40)

    async def test_unknown_publication_context_uses_zero_modifier(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        spe = await evaluator.evaluate_and_persist(
            uuid.uuid4(),
            SourcePolicyInput(
                document_type="contract",
                publication_context="invented_context",
            ),
        )
        assert spe.authority_score == pytest.approx(0.78)

    async def test_unknown_attestation_type_uses_zero_modifier(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        spe = await evaluator.evaluate_and_persist(
            uuid.uuid4(),
            SourcePolicyInput(
                document_type="contract",
                attestation_type="invented_type",
            ),
        )
        assert spe.authority_score == pytest.approx(0.78)
