"""Merge engine: deduplicates extraction outputs from multiple extractors."""

from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher

from mapu.extraction.types import (
    ExtractionSignal,
    ExtractorOutput,
    PropositionFrameCandidate,
)

_DEFAULT_METHOD_WEIGHTS: dict[str, float] = {
    "gliner": 1.0,
    "rebel": 0.8,
    "setfit": 1.2,
    "spacy": 0.9,
    "rule_defined_term": 1.5,
    "rule_amendment": 1.5,
    "rule_date": 1.0,
    "rule_cross_reference": 1.0,
    "srl": 0.7,
    "llm": 1.3,
}

_AGREEMENT_BONUS_PER_METHOD = 0.04
_MAX_AGREEMENT_BONUS = 0.12


@dataclass(frozen=True)
class MergeResult:
    """Result of merging multiple extractor outputs."""

    frames: tuple[PropositionFrameCandidate, ...]
    signals: tuple[ExtractionSignal, ...]
    duplicates_removed: int


@dataclass
class _CandidateAccumulator:
    best: PropositionFrameCandidate
    supports: list[tuple[str, float]]


class CandidateMergeEngine:
    """Merges extraction outputs: dedup, weighted confidence, agreement bonus."""

    def __init__(
        self,
        method_weights: dict[str, float] | None = None,
        fuzzy_threshold: float = 0.75,
    ) -> None:
        self._weights = method_weights or _DEFAULT_METHOD_WEIGHTS
        self._fuzzy_threshold = fuzzy_threshold

    def merge(self, outputs: list[ExtractorOutput]) -> MergeResult:
        all_signals: list[ExtractionSignal] = []
        accumulators: dict[str, _CandidateAccumulator] = {}
        duplicates = 0

        for output in outputs:
            all_signals.extend(output.signals)
            for frame in output.frames:
                key = _frame_dedup_key(frame)
                existing = accumulators.get(key)
                if existing is not None:
                    duplicates += 1
                    existing.supports.append(
                        (frame.extraction_method, frame.extraction_confidence)
                    )
                    if frame.extraction_confidence > existing.best.extraction_confidence:
                        existing.best = frame
                    continue
                accumulators[key] = _CandidateAccumulator(
                    best=frame,
                    supports=[(frame.extraction_method, frame.extraction_confidence)],
                )

        resolved: list[PropositionFrameCandidate] = []
        for acc in accumulators.values():
            if len(acc.supports) > 1:
                resolved.append(self._apply_agreement(acc))
            else:
                resolved.append(acc.best)

        final_frames, fuzzy_dupes = _fuzzy_dedup(resolved, self._fuzzy_threshold)
        duplicates += fuzzy_dupes

        return MergeResult(
            frames=tuple(final_frames),
            signals=tuple(all_signals),
            duplicates_removed=duplicates,
        )

    def _apply_agreement(
        self, acc: _CandidateAccumulator,
    ) -> PropositionFrameCandidate:
        unique_methods = {m for m, _ in acc.supports}
        num_unique = len(unique_methods)

        total_weight = sum(
            self._weights.get(m, 1.0) for m, _ in acc.supports
        )
        weighted_conf = sum(
            self._weights.get(m, 1.0) * c for m, c in acc.supports
        ) / total_weight if total_weight > 0 else acc.best.extraction_confidence

        base = max(acc.best.extraction_confidence, weighted_conf)
        bonus = min(_MAX_AGREEMENT_BONUS, _AGREEMENT_BONUS_PER_METHOD * (num_unique - 1))
        final = min(0.99, base + bonus)

        frame = acc.best
        return PropositionFrameCandidate(
            span_id=frame.span_id,
            frame_type=frame.frame_type,
            subject=frame.subject,
            predicate=frame.predicate,
            object=frame.object,
            value=frame.value,
            polarity=frame.polarity,
            modality=frame.modality,
            valid_range=frame.valid_range,
            normalized_text=frame.normalized_text,
            qualifiers=frame.qualifiers,
            stance=frame.stance,
            attestation_strength=frame.attestation_strength,
            extraction_method=frame.extraction_method,
            extraction_confidence=final,
            corroborating_methods=tuple(acc.supports),
        )


def _fuzzy_dedup(
    frames: list[PropositionFrameCandidate],
    threshold: float,
) -> tuple[list[PropositionFrameCandidate], int]:
    """Remove near-duplicate frames based on normalized_text similarity.

    Only compares frames that share the same subject kind, predicate, and stance.
    """
    if threshold <= 0 or len(frames) <= 1:
        return frames, 0

    kept: list[PropositionFrameCandidate] = []
    removed = 0
    for frame in frames:
        fn = frame.normalized_text.lower()
        fqual = tuple(sorted(frame.qualifiers.items())) if frame.qualifiers else ()
        fkey = (frame.subject.kind, frame.predicate.lower(), frame.stance, fqual)
        is_dup = False
        for existing in kept:
            equal = tuple(sorted(existing.qualifiers.items())) if existing.qualifiers else ()
            ekey = (existing.subject.kind, existing.predicate.lower(), existing.stance, equal)
            if fkey != ekey:
                continue
            en = existing.normalized_text.lower()
            if abs(len(fn) - len(en)) > max(len(fn), len(en)) * 0.5:
                continue
            if SequenceMatcher(None, fn, en).ratio() >= threshold:
                is_dup = True
                if frame.extraction_confidence > existing.extraction_confidence:
                    kept[kept.index(existing)] = frame
                break
        if is_dup:
            removed += 1
        else:
            kept.append(frame)
    return kept, removed


def _frame_dedup_key(frame: PropositionFrameCandidate) -> str:
    """Deterministic key for deduplication based on semantic content only."""
    parts = [
        frame.frame_type,
        frame.subject.text.lower().strip(),
        frame.subject.kind,
        frame.predicate.lower().strip(),
        frame.object.text.lower().strip() if frame.object else "",
        frame.object.kind if frame.object else "",
        json.dumps(frame.value, sort_keys=True) if frame.value else "",
        str(frame.polarity),
        frame.modality or "",
        str(frame.valid_range) if frame.valid_range else "",
        json.dumps(frame.qualifiers, sort_keys=True) if frame.qualifiers else "",
        frame.stance.value,
        frame.attestation_strength.value if frame.attestation_strength else "",
    ]
    return "|".join(parts)
