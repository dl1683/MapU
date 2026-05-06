"""Unit tests for computation evaluator registry."""

from __future__ import annotations

import pytest

from mapu.computation.registry import (
    DifferenceCheck,
    RatioComparison,
    ThresholdCheck,
    get_evaluator,
)


class TestRatioComparison:
    def test_basic_ratio(self) -> None:
        evaluator = RatioComparison()
        result = evaluator.evaluate(
            {"numerator": "revenue", "denominator": "debt", "threshold": 2.0},
            {"revenue": 100, "debt": 40},
        )
        assert result["ratio"] == pytest.approx(2.5)
        assert result["met"] is True

    def test_ratio_below_threshold(self) -> None:
        evaluator = RatioComparison()
        result = evaluator.evaluate(
            {"numerator": "revenue", "denominator": "debt", "threshold": 3.0},
            {"revenue": 100, "debt": 40},
        )
        assert result["met"] is False

    def test_division_by_zero(self) -> None:
        evaluator = RatioComparison()
        result = evaluator.evaluate(
            {"numerator": "a", "denominator": "b", "threshold": 1.0},
            {"a": 10, "b": 0},
        )
        assert result["met"] is False
        assert result["error"] == "division_by_zero"

    def test_less_than_operator(self) -> None:
        evaluator = RatioComparison()
        result = evaluator.evaluate(
            {"numerator": "a", "denominator": "b", "threshold": 3.0, "operator": "<"},
            {"a": 4, "b": 2},
        )
        assert result["ratio"] == pytest.approx(2.0)
        assert result["met"] is True

    def test_comparison_word_form_lte(self) -> None:
        evaluator = RatioComparison()
        result = evaluator.evaluate(
            {"numerator": "a", "denominator": "b", "threshold": 3.5, "comparison": "lte"},
            {"a": 7, "b": 2},
        )
        assert result["ratio"] == pytest.approx(3.5)
        assert result["met"] is True

    def test_comparison_word_form_gte(self) -> None:
        evaluator = RatioComparison()
        result = evaluator.evaluate(
            {"numerator": "a", "denominator": "b", "threshold": 3.0, "comparison": "gte"},
            {"a": 7, "b": 2},
        )
        assert result["met"] is True

    def test_operator_takes_precedence_over_comparison(self) -> None:
        evaluator = RatioComparison()
        result = evaluator.evaluate(
            {"numerator": "a", "denominator": "b", "threshold": 3.0,
             "operator": "<=", "comparison": "gte"},
            {"a": 4, "b": 2},
        )
        assert result["met"] is True  # 2.0 <= 3.0, operator wins


class TestThresholdCheck:
    def test_above_threshold(self) -> None:
        evaluator = ThresholdCheck()
        result = evaluator.evaluate(
            {"value": "score", "threshold": 0.5},
            {"score": 0.8},
        )
        assert result["met"] is True

    def test_below_threshold(self) -> None:
        evaluator = ThresholdCheck()
        result = evaluator.evaluate(
            {"value": "score", "threshold": 0.9},
            {"score": 0.8},
        )
        assert result["met"] is False

    def test_comparison_word_form_lt(self) -> None:
        evaluator = ThresholdCheck()
        result = evaluator.evaluate(
            {"value": "score", "threshold": 0.9, "comparison": "lt"},
            {"score": 0.8},
        )
        assert result["met"] is True


class TestDifferenceCheck:
    def test_within_tolerance(self) -> None:
        evaluator = DifferenceCheck()
        result = evaluator.evaluate(
            {"actual": "a", "expected": "b", "tolerance": 5.0},
            {"a": 102, "b": 100},
        )
        assert result["within_tolerance"] is True
        assert result["difference"] == pytest.approx(2.0)

    def test_outside_tolerance(self) -> None:
        evaluator = DifferenceCheck()
        result = evaluator.evaluate(
            {"actual": "a", "expected": "b", "tolerance": 1.0},
            {"a": 105, "b": 100},
        )
        assert result["within_tolerance"] is False


class TestRegistry:
    def test_get_known_evaluator(self) -> None:
        assert get_evaluator("ratio_comparison") is not None
        assert get_evaluator("threshold_check") is not None
        assert get_evaluator("difference_check") is not None

    def test_get_unknown_evaluator_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown evaluator"):
            get_evaluator("nonexistent")
