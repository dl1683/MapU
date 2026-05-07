"""Unit tests for TruthComputeService and DbTruthEvidenceProvider."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from mapu.truth.policy import EvidenceRecord, TruthPolicyV1
from mapu.truth.provider import DbTruthEvidenceProvider
from mapu.truth.service import TruthComputeService
from mapu.types import Stance, TruthStatus


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestDbTruthEvidenceProvider:
    @pytest.mark.asyncio
    async def test_is_retracted_returns_false_when_no_edge(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        provider = DbTruthEvidenceProvider(session, uuid.uuid4())
        assert await provider.is_retracted(uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_is_retracted_returns_true_when_edge_exists(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = uuid.uuid4()
        session.execute = AsyncMock(return_value=result_mock)

        provider = DbTruthEvidenceProvider(session, uuid.uuid4())
        assert await provider.is_retracted(uuid.uuid4()) is True

    @pytest.mark.asyncio
    async def test_is_superseded_returns_false_when_no_edge(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        provider = DbTruthEvidenceProvider(session, uuid.uuid4())
        assert await provider.is_superseded(uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_accepted_attestations_returns_empty_on_no_results(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        provider = DbTruthEvidenceProvider(session, uuid.uuid4())
        records = await provider.accepted_attestations(uuid.uuid4(), uuid.uuid4())
        assert len(records) == 0


class TestTruthComputeService:
    @pytest.mark.asyncio
    async def test_compute_returns_unchanged_on_same_basis_hash(self) -> None:
        session = _make_session()
        corpus_id = uuid.uuid4()
        prop_id = uuid.uuid4()
        sit_id = uuid.uuid4()

        svc = TruthComputeService(session, corpus_id)
        svc._provider = MagicMock()
        svc._provider.is_retracted = AsyncMock(return_value=False)
        svc._provider.is_superseded = AsyncMock(return_value=False)
        svc._provider.accepted_attestations = AsyncMock(return_value=[])

        existing_state = MagicMock()
        existing_state.id = uuid.uuid4()
        existing_state.basis_hash = TruthPolicyV1()._hash([])

        current_mock = MagicMock()
        current_mock.scalar_one_or_none.return_value = existing_state
        session.execute = AsyncMock(return_value=current_mock)

        result = await svc.compute_and_persist(prop_id, sit_id)
        assert result.changed is False
        assert result.truth_result.status == TruthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_compute_creates_state_on_new_proposition(self) -> None:
        session = _make_session()
        corpus_id = uuid.uuid4()
        prop_id = uuid.uuid4()
        sit_id = uuid.uuid4()

        svc = TruthComputeService(session, corpus_id)
        svc._provider = MagicMock()
        svc._provider.is_retracted = AsyncMock(return_value=False)
        svc._provider.is_superseded = AsyncMock(return_value=False)
        svc._provider.accepted_attestations = AsyncMock(return_value=[
            EvidenceRecord(
                attestation_id=uuid.uuid4(),
                stance=Stance.ASSERTS,
                extraction_confidence=0.9,
                attestation_strength="direct_statement",
                authority_score=0.8,
                attestation_type="first_party",
                document_type=None,
                publication_context=None,
                independence_group=None,
            ),
        ])

        current_mock = MagicMock()
        current_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=current_mock)

        result = await svc.compute_and_persist(prop_id, sit_id)
        assert result.changed is True
        assert result.truth_result.status == TruthStatus.ACCEPTED
        session.add.assert_called()

    @pytest.mark.asyncio
    async def test_compute_retracted_proposition(self) -> None:
        session = _make_session()
        corpus_id = uuid.uuid4()

        svc = TruthComputeService(session, corpus_id)
        svc._provider = MagicMock()
        svc._provider.is_retracted = AsyncMock(return_value=True)

        current_mock = MagicMock()
        current_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=current_mock)

        result = await svc.compute_and_persist(uuid.uuid4(), uuid.uuid4())
        assert result.changed is True
        assert result.truth_result.status == TruthStatus.RETRACTED

    @pytest.mark.asyncio
    async def test_recompute_delegates_to_compute_and_persist(self) -> None:
        session = _make_session()
        corpus_id = uuid.uuid4()
        prop_id = uuid.uuid4()
        sit_ids = [uuid.uuid4(), uuid.uuid4()]

        svc = TruthComputeService(session, corpus_id)
        svc._provider = MagicMock()
        svc._provider.is_retracted = AsyncMock(return_value=False)
        svc._provider.is_superseded = AsyncMock(return_value=False)
        svc._provider.accepted_attestations = AsyncMock(return_value=[])

        current_mock = MagicMock()
        current_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=current_mock)

        results = await svc.recompute_for_proposition(prop_id, sit_ids)
        assert len(results) == 2
        assert all(r.truth_result.status == TruthStatus.UNKNOWN for r in results)
