"""Merge engine: deduplicates extraction outputs from multiple extractors."""

from __future__ import annotations

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
        seen_frame_keys: set[str] = set()
        unique_frames: list[PropositionFrameCandidate] = []
        duplicates = 0

        for output in outputs:
            all_signals.extend(output.signals)
            for frame in output.frames:
                key = _frame_dedup_key(frame)
                if key in seen_frame_keys:
                    duplicates += 1
                    continue
                seen_frame_keys.add(key)
                unique_frames.append(frame)

        return MergeResult(
            frames=tuple(unique_frames),
            signals=tuple(all_signals),
            duplicates_removed=duplicates,
        )


def _frame_dedup_key(frame: PropositionFrameCandidate) -> str:
    """Deterministic key for deduplication based on semantic content only."""
    parts = [
        frame.frame_type.value,
        frame.subject.text.lower().strip(),
        frame.predicate.lower().strip(),
        frame.object.text.lower().strip() if frame.object else "",
        str(frame.value) if frame.value else "",
        str(frame.polarity),
        frame.modality or "",
        str(frame.valid_range) if frame.valid_range else "",
    ]
    return "|".join(parts)
