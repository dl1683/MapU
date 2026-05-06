"""Abstention gate: decides which candidates to materialize based on confidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mapu.extraction.types import PropositionFrameCandidate


class AbstentionDecision(StrEnum):
    ACCEPTED = "accepted"
    CANDIDATE = "candidate"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AbstentionResult:
    """A candidate with its abstention decision."""

    frame: PropositionFrameCandidate
    decision: AbstentionDecision


class AbstentionGate:
    """Filters extraction candidates by confidence thresholds."""

    def __init__(
        self,
        auto_accept_min: float = 0.85,
        candidate_min: float = 0.3,
    ) -> None:
        if not 0.0 <= candidate_min <= auto_accept_min <= 1.0:
            raise ValueError(
                f"Invalid thresholds: candidate_min={candidate_min}, "
                f"auto_accept_min={auto_accept_min}"
            )
        self._auto_accept_min = auto_accept_min
        self._candidate_min = candidate_min

    def evaluate(
        self, frames: tuple[PropositionFrameCandidate, ...]
    ) -> list[AbstentionResult]:
        results: list[AbstentionResult] = []
        for frame in frames:
            conf = frame.extraction_confidence
            if not 0.0 <= conf <= 1.0:
                raise ValueError(
                    f"extraction_confidence must be in [0.0, 1.0], got {conf}"
                )
            if conf >= self._auto_accept_min:
                decision = AbstentionDecision.ACCEPTED
            elif conf >= self._candidate_min:
                decision = AbstentionDecision.CANDIDATE
            else:
                decision = AbstentionDecision.REJECTED
            results.append(AbstentionResult(frame=frame, decision=decision))
        return results
