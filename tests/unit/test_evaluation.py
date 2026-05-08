"""Unit tests for the evaluation framework."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mapu.evaluation.cases import (
    ALL_BENCHMARK_CASES,
    get_cases_by_domain,
    get_cases_by_tag,
)
from mapu.evaluation.metrics import (
    abstention_quality,
    authority_calibration_error,
    fuzzy_match_score,
    fuzzy_precision_recall_f1,
    gap_detection_score,
    precision_recall_f1,
    provenance_hit_rate,
    truth_accuracy,
)
from mapu.evaluation.reporting import (
    format_summary,
    suite_to_dict,
    write_json_scorecard,
)
from mapu.evaluation.types import (
    BenchmarkDomain,
    CaseResult,
    EvalPhase,
    PhaseResult,
    SuiteResult,
)


class TestPrecisionRecallF1:
    def test_perfect_match(self) -> None:
        result = precision_recall_f1({"a", "b", "c"}, {"a", "b", "c"})
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0

    def test_no_match(self) -> None:
        result = precision_recall_f1({"x", "y"}, {"a", "b"})
        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.f1 == 0.0

    def test_partial_match(self) -> None:
        result = precision_recall_f1({"a", "b", "x"}, {"a", "b", "c"})
        assert result.true_positives == 2
        assert result.false_positives == 1
        assert result.false_negatives == 1
        assert result.precision == pytest.approx(2 / 3)
        assert result.recall == pytest.approx(2 / 3)

    def test_empty_sets(self) -> None:
        result = precision_recall_f1(set(), set())
        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.f1 == 0.0


class TestFuzzyMatch:
    def test_exact_match(self) -> None:
        assert fuzzy_match_score("hello world", "hello world") == 1.0

    def test_case_insensitive(self) -> None:
        assert fuzzy_match_score("Hello World", "hello world") == 1.0

    def test_partial_match(self) -> None:
        score = fuzzy_match_score("hello world", "hello earth")
        assert 0.3 < score < 0.9

    def test_no_match(self) -> None:
        score = fuzzy_match_score("abc", "xyz")
        assert score < 0.5


class TestFuzzyPrecisionRecallF1:
    def test_exact_matches(self) -> None:
        result = fuzzy_precision_recall_f1(
            ["foo bar", "baz qux"],
            ["foo bar", "baz qux"],
        )
        assert result.precision == 1.0
        assert result.recall == 1.0

    def test_close_matches(self) -> None:
        result = fuzzy_precision_recall_f1(
            ["the seller shall deliver financial statements"],
            ["Seller shall deliver financial statements"],
            threshold=0.7,
        )
        assert result.true_positives == 1

    def test_no_match_below_threshold(self) -> None:
        result = fuzzy_precision_recall_f1(
            ["completely different text"],
            ["Seller shall deliver"],
            threshold=0.7,
        )
        assert result.true_positives == 0


class TestTruthAccuracy:
    def test_perfect(self) -> None:
        assert truth_accuracy(["accepted", "denied"], ["accepted", "denied"]) == 1.0

    def test_half(self) -> None:
        assert truth_accuracy(["accepted", "denied"], ["accepted", "accepted"]) == 0.5

    def test_empty(self) -> None:
        assert truth_accuracy([], []) == 1.0


class TestAuthorityCalibrationError:
    def test_perfectly_calibrated(self) -> None:
        error = authority_calibration_error(
            [0.9, 0.9, 0.1, 0.1],
            [True, True, False, False],
        )
        assert error < 0.15

    def test_empty(self) -> None:
        assert authority_calibration_error([], []) == 0.0


class TestProvenanceHitRate:
    def test_full(self) -> None:
        assert provenance_hit_rate(10, 10) == 1.0

    def test_partial(self) -> None:
        assert provenance_hit_rate(5, 10) == 0.5

    def test_empty(self) -> None:
        assert provenance_hit_rate(0, 0) == 1.0


class TestGapDetection:
    def test_all_detected(self) -> None:
        assert gap_detection_score(3, 3) == 1.0

    def test_partial(self) -> None:
        assert gap_detection_score(1, 2) == 0.5

    def test_over_detection_capped(self) -> None:
        assert gap_detection_score(5, 3) == 1.0

    def test_no_expected(self) -> None:
        assert gap_detection_score(0, 0) == 1.0


class TestAbstentionQuality:
    def test_perfect(self) -> None:
        assert abstention_quality(3, 3, 0) == 1.0

    def test_no_cases(self) -> None:
        assert abstention_quality(0, 0, 0) == 1.0


class TestFindFuzzyRank:
    def test_exact_match_first(self) -> None:
        from mapu.evaluation.runner import _find_fuzzy_rank
        result = _find_fuzzy_rank(["hello world", "foo bar"], "hello world", 0.7)
        assert result == 0

    def test_exact_match_second(self) -> None:
        from mapu.evaluation.runner import _find_fuzzy_rank
        result = _find_fuzzy_rank(["foo bar", "hello world"], "hello world", 0.7)
        assert result == 1

    def test_no_match(self) -> None:
        from mapu.evaluation.runner import _find_fuzzy_rank
        result = _find_fuzzy_rank(["completely different"], "hello world", 0.7)
        assert result is None

    def test_fuzzy_match(self) -> None:
        from mapu.evaluation.runner import _find_fuzzy_rank
        result = _find_fuzzy_rank(
            ["the seller shall deliver financial statements"],
            "Seller shall deliver financial statements",
            0.7,
        )
        assert result == 0


class TestBenchmarkCases:
    def test_all_cases_exist(self) -> None:
        assert len(ALL_BENCHMARK_CASES) >= 8

    def test_all_have_ids(self) -> None:
        ids = [c.id for c in ALL_BENCHMARK_CASES]
        assert len(set(ids)) == len(ids)

    def test_domain_filter(self) -> None:
        legal = get_cases_by_domain(BenchmarkDomain.LEGAL)
        assert all(c.domain == BenchmarkDomain.LEGAL for c in legal)
        assert len(legal) >= 2

    def test_tag_filter(self) -> None:
        contract_cases = get_cases_by_tag("contract")
        assert len(contract_cases) >= 1

    def test_all_domains_represented(self) -> None:
        domains = {c.domain for c in ALL_BENCHMARK_CASES}
        assert BenchmarkDomain.CODE in domains
        assert BenchmarkDomain.LEGAL in domains
        assert BenchmarkDomain.FINANCE in domains
        assert BenchmarkDomain.BIOMEDICAL in domains

    def test_cases_have_source_text(self) -> None:
        for case in ALL_BENCHMARK_CASES:
            assert len(case.source_text) > 50, f"Case {case.id} has insufficient source text"


class TestSuiteResult:
    def _make_suite(self) -> SuiteResult:
        return SuiteResult(
            suite_name="test",
            git_commit="abc1234",
            duration_ms=1000.0,
            case_results=[
                CaseResult(
                    case_id="legal_001",
                    domain="legal",
                    metrics={"extraction.proposition_f1": 0.85},
                    phases=[
                        PhaseResult(
                            phase=EvalPhase.EXTRACTION,
                            success=True,
                            duration_ms=100.0,
                            details={"proposition_f1": 0.85},
                        ),
                    ],
                ),
                CaseResult(
                    case_id="code_001",
                    domain="code",
                    metrics={"extraction.proposition_f1": 0.70},
                    phases=[
                        PhaseResult(
                            phase=EvalPhase.EXTRACTION,
                            success=True,
                            duration_ms=80.0,
                            details={"proposition_f1": 0.70},
                        ),
                    ],
                ),
            ],
            aggregate_metrics={
                "mean_extraction.proposition_f1": 0.775,
                "total_cases": 2.0,
            },
        )

    def test_suite_to_dict(self) -> None:
        suite = self._make_suite()
        d = suite_to_dict(suite)
        assert d["suite_name"] == "test"
        assert d["git_commit"] == "abc1234"
        assert len(d["cases"]) == 2  # type: ignore[arg-type]

    def test_format_summary(self) -> None:
        suite = self._make_suite()
        summary = format_summary(suite)
        assert "test" in summary
        assert "legal" in summary
        assert "code" in summary

    def test_write_json_scorecard(self, tmp_path: Path) -> None:
        suite = self._make_suite()
        path = write_json_scorecard(suite, tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["suite_name"] == "test"
        assert len(data["cases"]) == 2
