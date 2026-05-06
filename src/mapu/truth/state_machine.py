"""State machines for proposition truth status and changeset status."""

from __future__ import annotations

from mapu.types import ChangesetStatus, TruthStatus

PROPOSITION_TRANSITIONS: dict[TruthStatus, frozenset[TruthStatus]] = {
    TruthStatus.UNKNOWN: frozenset({
        TruthStatus.ACCEPTED, TruthStatus.DENIED, TruthStatus.REPORTED,
        TruthStatus.CONTESTED, TruthStatus.RETRACTED, TruthStatus.SUPERSEDED,
    }),
    TruthStatus.ACCEPTED: frozenset({
        TruthStatus.CONTESTED, TruthStatus.UNKNOWN,
        TruthStatus.RETRACTED, TruthStatus.SUPERSEDED,
    }),
    TruthStatus.DENIED: frozenset({
        TruthStatus.CONTESTED, TruthStatus.UNKNOWN,
        TruthStatus.RETRACTED, TruthStatus.SUPERSEDED,
    }),
    TruthStatus.REPORTED: frozenset({
        TruthStatus.ACCEPTED, TruthStatus.DENIED, TruthStatus.CONTESTED,
        TruthStatus.UNKNOWN, TruthStatus.RETRACTED, TruthStatus.SUPERSEDED,
    }),
    TruthStatus.CONTESTED: frozenset({
        TruthStatus.ACCEPTED, TruthStatus.DENIED, TruthStatus.UNKNOWN,
        TruthStatus.RETRACTED, TruthStatus.SUPERSEDED,
    }),
    TruthStatus.RETRACTED: frozenset({TruthStatus.UNKNOWN}),
    TruthStatus.SUPERSEDED: frozenset({TruthStatus.UNKNOWN}),
}

CHANGESET_TRANSITIONS: dict[ChangesetStatus, frozenset[ChangesetStatus]] = {
    ChangesetStatus.PROPOSED: frozenset({
        ChangesetStatus.AUTO_APPLIED, ChangesetStatus.APPROVED, ChangesetStatus.REJECTED,
    }),
    ChangesetStatus.AUTO_APPLIED: frozenset({
        ChangesetStatus.APPLIED, ChangesetStatus.FAILED,
    }),
    ChangesetStatus.APPROVED: frozenset({
        ChangesetStatus.APPLIED, ChangesetStatus.FAILED,
    }),
    ChangesetStatus.APPLIED: frozenset({
        ChangesetStatus.ROLLED_BACK, ChangesetStatus.ROLLBACK_FAILED,
    }),
    ChangesetStatus.REJECTED: frozenset(),
    ChangesetStatus.ROLLED_BACK: frozenset(),
    ChangesetStatus.FAILED: frozenset(),
    ChangesetStatus.ROLLBACK_FAILED: frozenset(),
}


class InvalidTransitionError(Exception):
    def __init__(self, current: str, target: str, entity: str = "entity") -> None:
        super().__init__(f"Invalid {entity} transition: {current} -> {target}")
        self.current = current
        self.target = target


def validate_proposition_transition(current: TruthStatus, target: TruthStatus) -> None:
    allowed = PROPOSITION_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(current, target, "proposition truth status")


def validate_changeset_transition(current: ChangesetStatus, target: ChangesetStatus) -> None:
    allowed = CHANGESET_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(current, target, "changeset status")
