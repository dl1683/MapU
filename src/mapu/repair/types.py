"""Repair engine types: blast radius reports, operation payloads, risk levels."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from mapu.types import RiskLevel as RiskLevel


class RepairOperationType(StrEnum):
    RETRACT = "retract_proposition"
    SUPERSEDE = "supersede_proposition"
    REJECT_ATTESTATION = "reject_attestation"
    SPLIT_HANDLE = "split_handle"
    MERGE_HANDLES = "merge_handles"


@dataclass(frozen=True)
class BlastRadiusReport:
    root_proposition_id: uuid.UUID
    affected_proposition_ids: tuple[uuid.UUID, ...]
    recompute_only_proposition_ids: tuple[uuid.UUID, ...]
    affected_handle_ids: tuple[uuid.UUID, ...]
    affected_gap_ids: tuple[uuid.UUID, ...]
    max_depth_seen: int
    depth_limited: bool
    risk_level: RiskLevel

    @property
    def total_affected(self) -> int:
        return len(self.affected_proposition_ids) + len(self.recompute_only_proposition_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_proposition_id": str(self.root_proposition_id),
            "affected_proposition_ids": [str(x) for x in self.affected_proposition_ids],
            "recompute_only_proposition_ids": [str(x) for x in self.recompute_only_proposition_ids],
            "affected_handle_ids": [str(x) for x in self.affected_handle_ids],
            "affected_gap_ids": [str(x) for x in self.affected_gap_ids],
            "max_depth_seen": self.max_depth_seen,
            "depth_limited": self.depth_limited,
            "risk_level": self.risk_level.value,
            "total_affected": self.total_affected,
        }


@dataclass(frozen=True)
class RepairRequest:
    operation_type: RepairOperationType
    payload: dict[str, Any]
    actor: str
    actor_type: str = "system"
    reason: str = ""


@dataclass(frozen=True)
class RepairPreview:
    request: RepairRequest
    blast_radius: BlastRadiusReport
    operations: tuple[OperationPayload, ...]
    risk_level: RiskLevel


@dataclass(frozen=True)
class OperationPayload:
    operation_type: str
    ordinal: int
    payload: dict[str, Any]


@dataclass
class RepairResult:
    changeset_id: uuid.UUID
    success: bool
    operations_executed: int
    recomputed_propositions: int
    gaps_created: int
    errors: list[str] = field(default_factory=list)
