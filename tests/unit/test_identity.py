"""Unit tests for identity decision pair canonicalization and validation."""

from __future__ import annotations

import uuid

from mapu.entity.identity import _VALID_DECISIONS, canonicalize_pair


class TestCanonicalizePair:
    def test_same_order_preserved(self) -> None:
        a = uuid.UUID("00000000-0000-0000-0000-000000000001")
        b = uuid.UUID("00000000-0000-0000-0000-000000000002")
        result = canonicalize_pair(a, b)
        assert result == (a, b)

    def test_reversed_order_swapped(self) -> None:
        a = uuid.UUID("00000000-0000-0000-0000-000000000001")
        b = uuid.UUID("00000000-0000-0000-0000-000000000002")
        result = canonicalize_pair(b, a)
        assert result == (a, b)

    def test_idempotent(self) -> None:
        a = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        b = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        r1 = canonicalize_pair(a, b)
        r2 = canonicalize_pair(b, a)
        assert r1 == r2

    def test_same_id(self) -> None:
        a = uuid.UUID("00000000-0000-0000-0000-000000000001")
        result = canonicalize_pair(a, a)
        assert result == (a, a)


class TestValidDecisions:
    def test_expected_decisions_present(self) -> None:
        assert {"same_entity", "different_entity", "uncertain"} == _VALID_DECISIONS

    def test_matches_db_check_constraint(self) -> None:
        db_values = {"same_entity", "different_entity", "uncertain"}
        assert db_values == _VALID_DECISIONS
