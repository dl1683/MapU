"""Unit tests for identity decision pair canonicalization and validation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from mapu.entity.identity import (
    _VALID_DECISIONS,
    IdentityDecisionService,
    canonicalize_pair,
)


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


class TestIdentityDecisionValidation:
    @pytest.fixture
    def service(self) -> IdentityDecisionService:
        session = AsyncMock()
        corpus_id = uuid.uuid4()
        return IdentityDecisionService(session, corpus_id)

    async def test_same_handle_rejected(self, service: IdentityDecisionService) -> None:
        handle_id = uuid.uuid4()
        with pytest.raises(ValueError, match="itself"):
            await service.decide(handle_id, handle_id, "same_entity", 0.9, "test")

    async def test_invalid_decision_rejected(self, service: IdentityDecisionService) -> None:
        with pytest.raises(ValueError, match="Invalid decision"):
            await service.decide(uuid.uuid4(), uuid.uuid4(), "maybe", 0.5, "test")

    async def test_confidence_below_zero_rejected(self, service: IdentityDecisionService) -> None:
        with pytest.raises(ValueError, match="Confidence"):
            await service.decide(uuid.uuid4(), uuid.uuid4(), "same_entity", -0.1, "test")

    async def test_confidence_above_one_rejected(self, service: IdentityDecisionService) -> None:
        with pytest.raises(ValueError, match="Confidence"):
            await service.decide(uuid.uuid4(), uuid.uuid4(), "same_entity", 1.5, "test")
