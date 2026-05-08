"""Evaluation metrics: precision, recall, F1, and domain-specific quality scores."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class PrecisionRecallF1:
    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int


def precision_recall_f1(
    predicted: set[str],
    expected: set[str],
) -> PrecisionRecallF1:
    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return PrecisionRecallF1(
        precision=precision, recall=recall, f1=f1,
        true_positives=tp, false_positives=fp, false_negatives=fn,
    )


def fuzzy_match_score(predicted: str, expected: str) -> float:
    p, e = predicted.lower(), expected.lower()
    if p == e:
        return 1.0
    lp, le = len(p), len(e)
    if lp == 0 or le == 0:
        return 0.0
    if max(lp, le) > 3 * min(lp, le):
        return 0.0
    return SequenceMatcher(None, p, e).ratio()


def fuzzy_precision_recall_f1(
    predicted: list[str],
    expected: list[str],
    threshold: float = 0.7,
) -> PrecisionRecallF1:
    matched_expected: set[int] = set()
    tp = 0
    for pred in predicted:
        best_score = 0.0
        best_idx = -1
        for i, exp in enumerate(expected):
            if i in matched_expected:
                continue
            score = fuzzy_match_score(pred, exp)
            if score > best_score:
                best_score = score
                best_idx = i
        if best_score >= threshold and best_idx >= 0:
            tp += 1
            matched_expected.add(best_idx)

    fp = len(predicted) - tp
    fn = len(expected) - len(matched_expected)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return PrecisionRecallF1(
        precision=precision, recall=recall, f1=f1,
        true_positives=tp, false_positives=fp, false_negatives=fn,
    )


def truth_accuracy(
    predicted_statuses: list[str],
    expected_statuses: list[str],
) -> float:
    if not expected_statuses:
        return 1.0
    correct = sum(
        1 for p, e in zip(predicted_statuses, expected_statuses, strict=True) if p == e
    )
    return correct / len(expected_statuses)


def authority_calibration_error(
    predicted_scores: list[float],
    ground_truth_correct: list[bool],
    n_bins: int = 10,
) -> float:
    if not predicted_scores:
        return 0.0
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for score, correct in zip(predicted_scores, ground_truth_correct, strict=True):
        bin_idx = min(int(score * n_bins), n_bins - 1)
        bins[bin_idx].append((score, correct))

    total_error = 0.0
    total_count = 0
    for b in bins:
        if not b:
            continue
        avg_confidence = sum(s for s, _ in b) / len(b)
        actual_accuracy = sum(1 for _, c in b if c) / len(b)
        total_error += abs(avg_confidence - actual_accuracy) * len(b)
        total_count += len(b)

    return total_error / total_count if total_count > 0 else 0.0


def provenance_hit_rate(
    proposition_ids_with_provenance: int,
    total_propositions: int,
) -> float:
    if total_propositions == 0:
        return 1.0
    return proposition_ids_with_provenance / total_propositions


def gap_detection_score(
    detected_gaps: int,
    expected_gaps: int,
) -> float:
    if expected_gaps == 0:
        return 1.0 if detected_gaps == 0 else 0.0
    return min(detected_gaps / expected_gaps, 1.0)


def abstention_quality(
    abstained_count: int,
    should_have_abstained: int,
    should_not_have_abstained: int,
) -> float:
    if should_have_abstained + should_not_have_abstained == 0:
        return 1.0
    correct_abstentions = abstained_count - should_not_have_abstained
    total = should_have_abstained + should_not_have_abstained
    return max(0.0, correct_abstentions / total) if total > 0 else 1.0
