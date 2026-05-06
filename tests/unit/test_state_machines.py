"""Unit tests for proposition and changeset state machines."""

from __future__ import annotations

import pytest

from mapu.truth.state_machine import (
    InvalidTransitionError,
    validate_changeset_transition,
    validate_proposition_transition,
)
from mapu.types import ChangesetStatus, TruthStatus


class TestPropositionTransitions:
    @pytest.mark.parametrize(
        "current,target",
        [
            (TruthStatus.UNKNOWN, TruthStatus.ACCEPTED),
            (TruthStatus.UNKNOWN, TruthStatus.DENIED),
            (TruthStatus.UNKNOWN, TruthStatus.REPORTED),
            (TruthStatus.UNKNOWN, TruthStatus.CONTESTED),
            (TruthStatus.UNKNOWN, TruthStatus.RETRACTED),
            (TruthStatus.UNKNOWN, TruthStatus.SUPERSEDED),
            (TruthStatus.ACCEPTED, TruthStatus.CONTESTED),
            (TruthStatus.ACCEPTED, TruthStatus.UNKNOWN),
            (TruthStatus.ACCEPTED, TruthStatus.RETRACTED),
            (TruthStatus.ACCEPTED, TruthStatus.SUPERSEDED),
            (TruthStatus.DENIED, TruthStatus.CONTESTED),
            (TruthStatus.DENIED, TruthStatus.UNKNOWN),
            (TruthStatus.DENIED, TruthStatus.RETRACTED),
            (TruthStatus.DENIED, TruthStatus.SUPERSEDED),
            (TruthStatus.REPORTED, TruthStatus.ACCEPTED),
            (TruthStatus.REPORTED, TruthStatus.DENIED),
            (TruthStatus.REPORTED, TruthStatus.CONTESTED),
            (TruthStatus.REPORTED, TruthStatus.UNKNOWN),
            (TruthStatus.REPORTED, TruthStatus.RETRACTED),
            (TruthStatus.REPORTED, TruthStatus.SUPERSEDED),
            (TruthStatus.CONTESTED, TruthStatus.ACCEPTED),
            (TruthStatus.CONTESTED, TruthStatus.DENIED),
            (TruthStatus.CONTESTED, TruthStatus.UNKNOWN),
            (TruthStatus.CONTESTED, TruthStatus.RETRACTED),
            (TruthStatus.CONTESTED, TruthStatus.SUPERSEDED),
            (TruthStatus.RETRACTED, TruthStatus.UNKNOWN),
            (TruthStatus.SUPERSEDED, TruthStatus.UNKNOWN),
        ],
    )
    def test_valid_transitions(self, current: TruthStatus, target: TruthStatus) -> None:
        validate_proposition_transition(current, target)

    @pytest.mark.parametrize(
        "current,target",
        [
            (TruthStatus.ACCEPTED, TruthStatus.ACCEPTED),
            (TruthStatus.ACCEPTED, TruthStatus.DENIED),
            (TruthStatus.ACCEPTED, TruthStatus.REPORTED),
            (TruthStatus.RETRACTED, TruthStatus.ACCEPTED),
            (TruthStatus.RETRACTED, TruthStatus.RETRACTED),
            (TruthStatus.SUPERSEDED, TruthStatus.ACCEPTED),
            (TruthStatus.SUPERSEDED, TruthStatus.SUPERSEDED),
        ],
    )
    def test_invalid_transitions(self, current: TruthStatus, target: TruthStatus) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_proposition_transition(current, target)


class TestChangesetTransitions:
    @pytest.mark.parametrize(
        "current,target",
        [
            (ChangesetStatus.PROPOSED, ChangesetStatus.AUTO_APPLIED),
            (ChangesetStatus.PROPOSED, ChangesetStatus.APPROVED),
            (ChangesetStatus.PROPOSED, ChangesetStatus.REJECTED),
            (ChangesetStatus.AUTO_APPLIED, ChangesetStatus.APPLIED),
            (ChangesetStatus.AUTO_APPLIED, ChangesetStatus.FAILED),
            (ChangesetStatus.APPROVED, ChangesetStatus.APPLIED),
            (ChangesetStatus.APPROVED, ChangesetStatus.FAILED),
            (ChangesetStatus.APPLIED, ChangesetStatus.ROLLED_BACK),
            (ChangesetStatus.APPLIED, ChangesetStatus.ROLLBACK_FAILED),
        ],
    )
    def test_valid_transitions(self, current: ChangesetStatus, target: ChangesetStatus) -> None:
        validate_changeset_transition(current, target)

    @pytest.mark.parametrize(
        "current,target",
        [
            (ChangesetStatus.REJECTED, ChangesetStatus.PROPOSED),
            (ChangesetStatus.REJECTED, ChangesetStatus.APPROVED),
            (ChangesetStatus.ROLLED_BACK, ChangesetStatus.APPLIED),
            (ChangesetStatus.FAILED, ChangesetStatus.APPLIED),
            (ChangesetStatus.ROLLBACK_FAILED, ChangesetStatus.ROLLED_BACK),
            (ChangesetStatus.PROPOSED, ChangesetStatus.APPLIED),
        ],
    )
    def test_invalid_transitions(
        self, current: ChangesetStatus, target: ChangesetStatus
    ) -> None:
        with pytest.raises(InvalidTransitionError):
            validate_changeset_transition(current, target)

    def test_terminal_states_have_no_transitions(self) -> None:
        terminals = [
            ChangesetStatus.REJECTED,
            ChangesetStatus.ROLLED_BACK,
            ChangesetStatus.FAILED,
            ChangesetStatus.ROLLBACK_FAILED,
        ]
        for terminal in terminals:
            for target in ChangesetStatus:
                if target != terminal:
                    with pytest.raises(InvalidTransitionError):
                        validate_changeset_transition(terminal, target)
