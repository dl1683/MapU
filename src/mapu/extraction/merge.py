"""Merge engine: deduplicates extraction outputs from multiple extractors."""

from __future__ import annotations

import json
from dataclasses import dataclass

from mapu.extraction.types import (
    ExtractionSignal,
    ExtractorOutput,
    PropositionFrameCandidate,
)


@dataclass(frozen=True)
class MergeResult:
    """Result of merging multiple extractor outputs."""

    frames: tuple[PropositionFrameCandidate, ...]
    signals: tuple[ExtractionSignal, ...]
    duplicates_removed: int


class CandidateMergeEngine:
    """Conservative merge: dedup exact-match candidates, combine signals."""

    def merge(self, outputs: list[ExtractorOutput]) -> MergeResult:
        all_signals: list[ExtractionSignal] = []
        best_by_key: dict[str, PropositionFrameCandidate] = {}
        duplicates = 0

        for output in outputs:
            all_signals.extend(output.signals)
            for frame in output.frames:
                key = _frame_dedup_key(frame)
                existing = best_by_key.get(key)
                if existing is not None:
                    duplicates += 1
                    if frame.extraction_confidence > existing.extraction_confidence:
                        best_by_key[key] = frame
                    continue
                best_by_key[key] = frame

        return MergeResult(
            frames=tuple(best_by_key.values()),
            signals=tuple(all_signals),
            duplicates_removed=duplicates,
        )


def _frame_dedup_key(frame: PropositionFrameCandidate) -> str:
    """Deterministic key for deduplication based on semantic content only."""
    parts = [
        frame.frame_type.value,
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
    ]
    return "|".join(parts)
