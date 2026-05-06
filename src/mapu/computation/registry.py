"""Computation evaluator registry for typed evaluators (RatioComparison, ThresholdCheck, etc.)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ComputationEvaluator(Protocol):
    def evaluate(self, definition: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class RatioComparisonResult:
    ratio: float
    met: bool


class RatioComparison:
    """Compare two numeric inputs as a ratio against a threshold."""

    def evaluate(self, definition: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        numerator_key = definition["numerator"]
        denominator_key = definition["denominator"]
        threshold = definition["threshold"]
        operator = definition.get("operator", ">=")

        numerator = float(inputs[numerator_key])
        denominator = float(inputs[denominator_key])

        if denominator == 0:
            return {"ratio": None, "met": False, "error": "division_by_zero"}

        ratio = numerator / denominator
        if operator == ">=":
            met = ratio >= threshold
        elif operator == "<=":
            met = ratio <= threshold
        elif operator == ">":
            met = ratio > threshold
        elif operator == "<":
            met = ratio < threshold
        else:
            met = ratio == threshold

        return {"ratio": ratio, "met": met}


class ThresholdCheck:
    """Check if a value meets a threshold condition."""

    def evaluate(self, definition: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        value_key = definition["value"]
        threshold = definition["threshold"]
        operator = definition.get("operator", ">=")

        value = float(inputs[value_key])

        if operator == ">=":
            met = value >= threshold
        elif operator == "<=":
            met = value <= threshold
        elif operator == ">":
            met = value > threshold
        elif operator == "<":
            met = value < threshold
        else:
            met = value == threshold

        return {"value": value, "threshold": threshold, "met": met}


class DifferenceCheck:
    """Compute the difference between two values and check against a tolerance."""

    def evaluate(self, definition: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
        actual_key = definition["actual"]
        expected_key = definition["expected"]
        tolerance = definition.get("tolerance", 0)

        actual = float(inputs[actual_key])
        expected = float(inputs[expected_key])
        difference = actual - expected

        within_tolerance = abs(difference) <= tolerance

        return {
            "actual": actual,
            "expected": expected,
            "difference": difference,
            "within_tolerance": within_tolerance,
        }


_REGISTRY: dict[str, ComputationEvaluator] = {
    "ratio_comparison": RatioComparison(),
    "threshold_check": ThresholdCheck(),
    "difference_check": DifferenceCheck(),
}


def get_evaluator(evaluator_type: str) -> ComputationEvaluator:
    evaluator = _REGISTRY.get(evaluator_type)
    if evaluator is None:
        raise ValueError(f"Unknown evaluator type: {evaluator_type}")
    return evaluator


def register_evaluator(evaluator_type: str, evaluator: ComputationEvaluator) -> None:
    _REGISTRY[evaluator_type] = evaluator
