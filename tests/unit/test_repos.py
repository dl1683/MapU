"""Unit tests for extended lineage, review, and gap repositories."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from mapu.repos.gap import GapRepo
from mapu.repos.lineage import (
    DerivationEdgeRepo,
    DescendantInfo,
    RepairCascadeDepthExceeded,
    SupersessionEdgeRepo,
)
from mapu.repos.review import ChangesetRepo


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestDerivationEdgeRepo:
    @pytest.mark.asyncio
    async def test_children_returns_child_ids(self) -> None:
        session = _make_session()
        child_1, child_2 = uuid.uuid4(), uuid.uuid4()
        result_mock = MagicMock()
        result_mock.all.return_value = [(child_1,), (child_2,)]
        session.execute = AsyncMock(return_value=result_mock)

        repo = DerivationEdgeRepo(session, uuid.uuid4())
        children = await repo.children(uuid.uuid4())
        assert children == [child_1, child_2]

    @pytest.mark.asyncio
    async def test_children_returns_empty_when_none(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = DerivationEdgeRepo(session, uuid.uuid4())
        assert await repo.children(uuid.uuid4()) == []

    @pytest.mark.asyncio
    async def test_parents_returns_parent_ids(self) -> None:
        session = _make_session()
        parent_1 = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.all.return_value = [(parent_1,)]
        session.execute = AsyncMock(return_value=result_mock)

        repo = DerivationEdgeRepo(session, uuid.uuid4())
        parents = await repo.parents(uuid.uuid4())
        assert parents == [parent_1]

    @pytest.mark.asyncio
    async def test_descendants_with_depth_returns_info(self) -> None:
        session = _make_session()
        d1, d2 = uuid.uuid4(), uuid.uuid4()
        result_mock = MagicMock()
        result_mock.__iter__ = MagicMock(return_value=iter([(d1, 1), (d2, 2)]))
        session.execute = AsyncMock(return_value=result_mock)

        repo = DerivationEdgeRepo(session, uuid.uuid4())
        infos = await repo.descendants_with_depth(uuid.uuid4())
        assert len(infos) == 2
        assert infos[0] == DescendantInfo(id=d1, depth=1)
        assert infos[1] == DescendantInfo(id=d2, depth=2)

    @pytest.mark.asyncio
    async def test_descendants_with_depth_raises_on_limit(self) -> None:
        session = _make_session()
        d1 = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.__iter__ = MagicMock(return_value=iter([(d1, 5)]))
        session.execute = AsyncMock(return_value=result_mock)

        repo = DerivationEdgeRepo(session, uuid.uuid4())
        prop_id = uuid.uuid4()
        with pytest.raises(RepairCascadeDepthExceeded):
            await repo.descendants_with_depth(prop_id, max_depth=5)

    @pytest.mark.asyncio
    async def test_descendants_bounded_returns_id_set(self) -> None:
        session = _make_session()
        d1, d2 = uuid.uuid4(), uuid.uuid4()
        result_mock = MagicMock()
        result_mock.__iter__ = MagicMock(return_value=iter([(d1, 1), (d2, 2)]))
        session.execute = AsyncMock(return_value=result_mock)

        repo = DerivationEdgeRepo(session, uuid.uuid4())
        ids = await repo.descendants_bounded(uuid.uuid4())
        assert ids == {d1, d2}

    @pytest.mark.asyncio
    async def test_ancestors_bounded_returns_info(self) -> None:
        session = _make_session()
        a1 = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.__iter__ = MagicMock(return_value=iter([(a1, 1)]))
        session.execute = AsyncMock(return_value=result_mock)

        repo = DerivationEdgeRepo(session, uuid.uuid4())
        ancestors = await repo.ancestors_bounded(uuid.uuid4())
        assert len(ancestors) == 1
        assert ancestors[0].id == a1
        assert ancestors[0].depth == 1


class TestSUpersessionEdgeRepo:
    @pytest.mark.asyncio
    async def test_is_superseded_true(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar.return_value = True
        session.execute = AsyncMock(return_value=result_mock)

        repo = SupersessionEdgeRepo(session, uuid.uuid4())
        assert await repo.is_superseded(uuid.uuid4()) is True

    @pytest.mark.asyncio
    async def test_is_retracted_false(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar.return_value = False
        session.execute = AsyncMock(return_value=result_mock)

        repo = SupersessionEdgeRepo(session, uuid.uuid4())
        assert await repo.is_retracted(uuid.uuid4()) is False


class TestChangesetRepo:
    @pytest.mark.asyncio
    async def test_operations_for_changeset_returns_ordered(self) -> None:
        session = _make_session()
        op1, op2 = MagicMock(), MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [op1, op2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        repo = ChangesetRepo(session, uuid.uuid4())
        ops = await repo.operations_for_changeset(uuid.uuid4())
        assert ops == [op1, op2]

    @pytest.mark.asyncio
    async def test_record_operation_result_sets_fields(self) -> None:
        session = _make_session()
        op = MagicMock()
        op.result = None
        op.executed_at = None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = op
        session.execute = AsyncMock(return_value=result_mock)

        repo = ChangesetRepo(session, uuid.uuid4())
        await repo.record_operation_result(uuid.uuid4(), {"status": "ok"})
        assert op.result == {"status": "ok"}
        assert op.executed_at is not None

    @pytest.mark.asyncio
    async def test_record_operation_result_raises_on_missing(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        repo = ChangesetRepo(session, uuid.uuid4())
        with pytest.raises(ValueError, match="not found"):
            await repo.record_operation_result(uuid.uuid4(), {})


class TestGapRepo:
    @pytest.mark.asyncio
    async def test_gaps_for_target_returns_ids(self) -> None:
        session = _make_session()
        g1, g2 = uuid.uuid4(), uuid.uuid4()
        result_mock = MagicMock()
        result_mock.all.return_value = [(g1,), (g2,)]
        session.execute = AsyncMock(return_value=result_mock)

        repo = GapRepo(session, uuid.uuid4())
        gap_ids = await repo.gaps_for_target("proposition", uuid.uuid4())
        assert gap_ids == [g1, g2]

    @pytest.mark.asyncio
    async def test_gaps_for_target_returns_empty(self) -> None:
        session = _make_session()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        repo = GapRepo(session, uuid.uuid4())
        assert await repo.gaps_for_target("proposition", uuid.uuid4()) == []

    @pytest.mark.asyncio
    async def test_open_gaps_returns_list(self) -> None:
        session = _make_session()
        gap = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [gap]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        repo = GapRepo(session, uuid.uuid4())
        gaps = await repo.open_gaps()
        assert gaps == [gap]
