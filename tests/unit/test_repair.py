"""Unit tests for the repair engine: types, blast radius, changesets, service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mapu.repair.blast_radius import _classify_risk, compute_blast_radius
from mapu.repair.types import (
    BlastRadiusReport,
    OperationPayload,
    RepairOperationType,
    RepairPreview,
    RepairRequest,
    RepairResult,
    RiskLevel,
)


class TestRiskClassification:
    def test_low_risk(self) -> None:
        assert _classify_risk(5, 2, False) == RiskLevel.LOW

    def test_moderate_risk_by_count(self) -> None:
        assert _classify_risk(15, 3, False) == RiskLevel.MODERATE

    def test_moderate_risk_by_depth(self) -> None:
        assert _classify_risk(5, 7, False) == RiskLevel.MODERATE

    def test_high_risk_by_count(self) -> None:
        assert _classify_risk(150, 3, False) == RiskLevel.HIGH

    def test_high_risk_by_depth(self) -> None:
        assert _classify_risk(5, 12, False) == RiskLevel.HIGH

    def test_critical_risk_depth_limited(self) -> None:
        assert _classify_risk(0, 0, True) == RiskLevel.CRITICAL


class TestBlastRadiusReport:
    def test_total_affected(self) -> None:
        report = BlastRadiusReport(
            root_proposition_id=uuid.uuid4(),
            affected_proposition_ids=(uuid.uuid4(), uuid.uuid4()),
            recompute_only_proposition_ids=(uuid.uuid4(),),
            affected_handle_ids=(),
            affected_gap_ids=(),
            max_depth_seen=2,
            depth_limited=False,
            risk_level=RiskLevel.LOW,
        )
        assert report.total_affected == 3

    def test_to_dict_contains_keys(self) -> None:
        report = BlastRadiusReport(
            root_proposition_id=uuid.uuid4(),
            affected_proposition_ids=(),
            recompute_only_proposition_ids=(),
            affected_handle_ids=(),
            affected_gap_ids=(),
            max_depth_seen=0,
            depth_limited=False,
            risk_level=RiskLevel.LOW,
        )
        d = report.to_dict()
        assert "root_proposition_id" in d
        assert "risk_level" in d
        assert d["risk_level"] == "low"
        assert d["total_affected"] == 0


class TestRepairTypes:
    def test_operation_payload_fields(self) -> None:
        op = OperationPayload(
            operation_type="retract_proposition",
            ordinal=0,
            payload={"key": "value"},
        )
        assert op.ordinal == 0
        assert op.operation_type == "retract_proposition"

    def test_repair_request_defaults(self) -> None:
        req = RepairRequest(
            operation_type=RepairOperationType.RETRACT,
            payload={},
            actor="test",
        )
        assert req.actor_type == "system"
        assert req.reason == ""

    def test_repair_result_defaults(self) -> None:
        r = RepairResult(
            changeset_id=uuid.uuid4(),
            success=True,
            operations_executed=1,
            recomputed_propositions=2,
            gaps_created=0,
        )
        assert r.errors == []


class TestBlastRadiusComputation:
    @pytest.mark.asyncio
    async def test_empty_descendants(self) -> None:
        session = AsyncMock()

        with patch(
            "mapu.repair.blast_radius.DerivationEdgeRepo"
        ) as MockDerivRepo, patch(
            "mapu.repair.blast_radius.GapRepo"
        ) as MockGapRepo:
            deriv_instance = MagicMock()
            deriv_instance.descendants_with_depth = AsyncMock(return_value=[])
            MockDerivRepo.return_value = deriv_instance

            gap_instance = MagicMock()
            gap_instance.gaps_for_target = AsyncMock(return_value=[])
            MockGapRepo.return_value = gap_instance

            prop_id = uuid.uuid4()
            handle_id = uuid.uuid4()

            result_mock = MagicMock()
            result_mock.one_or_none.return_value = (handle_id, None)
            session.execute = AsyncMock(return_value=result_mock)

            report = await compute_blast_radius(
                session, uuid.uuid4(), prop_id,
            )

            assert report.root_proposition_id == prop_id
            assert len(report.affected_proposition_ids) == 0
            assert report.risk_level == RiskLevel.LOW
            assert report.depth_limited is False

    @pytest.mark.asyncio
    async def test_with_survivable_child(self) -> None:
        session = AsyncMock()
        from mapu.repos.lineage import DescendantInfo

        child_id = uuid.uuid4()
        prop_id = uuid.uuid4()
        other_parent = uuid.uuid4()

        with patch(
            "mapu.repair.blast_radius.DerivationEdgeRepo"
        ) as MockDerivRepo, patch(
            "mapu.repair.blast_radius.GapRepo"
        ) as MockGapRepo:
            deriv_instance = MagicMock()
            deriv_instance.descendants_with_depth = AsyncMock(
                return_value=[DescendantInfo(id=child_id, depth=1)]
            )
            deriv_instance.parents = AsyncMock(
                return_value=[prop_id, other_parent]
            )
            MockDerivRepo.return_value = deriv_instance

            gap_instance = MagicMock()
            gap_instance.gaps_for_target = AsyncMock(return_value=[])
            MockGapRepo.return_value = gap_instance

            handle_id = uuid.uuid4()
            result_mock = MagicMock()
            result_mock.one_or_none.return_value = (handle_id, None)
            session.execute = AsyncMock(return_value=result_mock)

            report = await compute_blast_radius(
                session, uuid.uuid4(), prop_id,
            )

            assert child_id in report.recompute_only_proposition_ids
            assert child_id not in report.affected_proposition_ids

    @pytest.mark.asyncio
    async def test_with_non_survivable_child(self) -> None:
        session = AsyncMock()
        from mapu.repos.lineage import DescendantInfo

        child_id = uuid.uuid4()
        prop_id = uuid.uuid4()

        with patch(
            "mapu.repair.blast_radius.DerivationEdgeRepo"
        ) as MockDerivRepo, patch(
            "mapu.repair.blast_radius.GapRepo"
        ) as MockGapRepo:
            deriv_instance = MagicMock()
            deriv_instance.descendants_with_depth = AsyncMock(
                return_value=[DescendantInfo(id=child_id, depth=1)]
            )
            deriv_instance.parents = AsyncMock(return_value=[prop_id])
            MockDerivRepo.return_value = deriv_instance

            gap_instance = MagicMock()
            gap_instance.gaps_for_target = AsyncMock(return_value=[])
            MockGapRepo.return_value = gap_instance

            handle_id = uuid.uuid4()
            result_mock = MagicMock()
            result_mock.one_or_none.return_value = (handle_id, None)
            session.execute = AsyncMock(return_value=result_mock)

            report = await compute_blast_radius(
                session, uuid.uuid4(), prop_id,
            )

            assert child_id in report.affected_proposition_ids
            assert child_id not in report.recompute_only_proposition_ids


class TestRepairPreview:
    def test_preview_structure(self) -> None:
        blast = BlastRadiusReport(
            root_proposition_id=uuid.uuid4(),
            affected_proposition_ids=(),
            recompute_only_proposition_ids=(),
            affected_handle_ids=(),
            affected_gap_ids=(),
            max_depth_seen=0,
            depth_limited=False,
            risk_level=RiskLevel.LOW,
        )
        preview = RepairPreview(
            request=RepairRequest(
                operation_type=RepairOperationType.RETRACT,
                payload={},
                actor="test",
            ),
            blast_radius=blast,
            operations=(
                OperationPayload("retract_proposition", 0, {}),
            ),
            risk_level=RiskLevel.LOW,
        )
        assert preview.risk_level == RiskLevel.LOW
        assert len(preview.operations) == 1
