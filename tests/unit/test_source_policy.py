"""Unit tests for source policy scoring (pure logic, no DB)."""

from __future__ import annotations

import pytest

from mapu.authority.source_policy import SourcePolicyEvaluatorV1, SourcePolicyInput


class TestSourcePolicyScoring:
    @pytest.fixture
    def evaluator(self) -> SourcePolicyEvaluatorV1:
        return SourcePolicyEvaluatorV1.__new__(SourcePolicyEvaluatorV1)

    def test_court_opinion_high(self, evaluator: SourcePolicyEvaluatorV1) -> None:
        score = evaluator.score(SourcePolicyInput(document_type="court_opinion"))
        assert score >= 0.90

    def test_social_media_low(self, evaluator: SourcePolicyEvaluatorV1) -> None:
        score = evaluator.score(SourcePolicyInput(document_type="social_media"))
        assert score <= 0.30

    def test_unknown_document_type(self, evaluator: SourcePolicyEvaluatorV1) -> None:
        score = evaluator.score(SourcePolicyInput(document_type=None))
        assert 0.30 <= score <= 0.50

    def test_publication_context_boost(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        base = evaluator.score(SourcePolicyInput(document_type="peer_reviewed_paper"))
        boosted = evaluator.score(SourcePolicyInput(
            document_type="peer_reviewed_paper",
            publication_context="peer_reviewed_journal",
        ))
        assert boosted > base

    def test_hearsay_penalty(self, evaluator: SourcePolicyEvaluatorV1) -> None:
        base = evaluator.score(SourcePolicyInput(document_type="news_article"))
        penalized = evaluator.score(SourcePolicyInput(
            document_type="news_article",
            attestation_type="hearsay",
        ))
        assert penalized < base

    def test_score_clamped_to_zero_one(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        score = evaluator.score(SourcePolicyInput(
            document_type="social_media",
            publication_context="social_media",
            attestation_type="hearsay",
        ))
        assert 0.0 <= score <= 1.0

    def test_government_attestation_boost(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        base = evaluator.score(SourcePolicyInput(
            document_type="official_report",
        ))
        gov = evaluator.score(SourcePolicyInput(
            document_type="official_report",
            attestation_type="government",
        ))
        assert gov > base

    def test_all_document_types_return_scores(
        self, evaluator: SourcePolicyEvaluatorV1
    ) -> None:
        types = [
            "court_opinion", "statute", "regulation", "peer_reviewed_paper",
            "government_filing", "sec_filing", "official_report", "contract",
            "technical_standard", "audit_report", "news_article", "blog_post",
            "social_media", "unknown",
        ]
        for doc_type in types:
            score = evaluator.score(SourcePolicyInput(document_type=doc_type))
            assert 0.0 <= score <= 1.0, f"Bad score for {doc_type}: {score}"
