"""Unit tests for identity decision pair canonicalization."""

from __future__ import annotations

import uuid

from mapu.entity.identity import canonicalize_pair


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
