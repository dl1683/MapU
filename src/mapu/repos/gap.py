"""Gap repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from mapu.models.gap import Gap, GapTarget
from mapu.repos.base import CorpusScopedRepo


class GapRepo(CorpusScopedRepo[Gap]):
    model = Gap

    async def create_gap(
        self,
        *,
        kind: str,
        description: str,
        detected_by: str,
        severity: str = "moderate",
        uncertainty_reason: str = "missing_evidence",
        evidence_hypothesis: dict[str, Any] | None = None,
        next_action: dict[str, Any] | None = None,
        expected_resolution: str | None = None,
        governance_tier: str = "provisional",
        priority_score: float | None = None,
    ) -> Gap:
        gap = Gap(
            corpus_id=self.corpus_id,
            kind=kind,
            description=description,
            severity=severity,
            detected_by=detected_by,
            uncertainty_reason=uncertainty_reason,
            evidence_hypothesis=evidence_hypothesis or {},
            next_action=next_action or {},
            expected_resolution=expected_resolution,
            governance_tier=governance_tier,
            priority_score=priority_score,
            last_evaluated_at=datetime.now(UTC),
        )
        return await self.add(gap)

    async def find_open_by_description(
        self,
        *,
        kind: str,
        description: str,
    ) -> Gap | None:
        stmt = (
            select(Gap)
            .where(
                Gap.corpus_id == self.corpus_id,
                Gap.status == "open",
                Gap.kind == kind,
                Gap.description == description,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_open_gap(
        self,
        *,
        kind: str,
        description: str,
        detected_by: str,
        severity: str = "moderate",
        uncertainty_reason: str = "missing_evidence",
        evidence_hypothesis: dict[str, Any] | None = None,
        next_action: dict[str, Any] | None = None,
        expected_resolution: str | None = None,
        governance_tier: str = "provisional",
        priority_score: float | None = None,
    ) -> Gap:
        existing = await self.find_open_by_description(
            kind=kind,
            description=description,
        )
        if existing is None:
            return await self.create_gap(
                kind=kind,
                description=description,
                detected_by=detected_by,
                severity=severity,
                uncertainty_reason=uncertainty_reason,
                evidence_hypothesis=evidence_hypothesis,
                next_action=next_action,
                expected_resolution=expected_resolution,
                governance_tier=governance_tier,
                priority_score=priority_score,
            )

        existing.detected_by = detected_by
        existing.severity = severity
        existing.uncertainty_reason = uncertainty_reason
        existing.evidence_hypothesis = evidence_hypothesis or {}
        existing.next_action = next_action or {}
        existing.expected_resolution = expected_resolution
        existing.governance_tier = governance_tier
        if priority_score is not None:
            existing.priority_score = max(float(existing.priority_score or 0.0), priority_score)
        existing.last_evaluated_at = datetime.now(UTC)
        await self.session.flush()
        return existing

    async def resolve(
        self,
        gap_id: uuid.UUID,
        *,
        summary: str = "",
        status: str = "resolved",
    ) -> Gap | None:
        gap = await self.get(gap_id)
        if gap is None:
            return None
        now = datetime.now(UTC)
        gap.status = status
        gap.resolved_at = now
        gap.resolution_summary = summary or None
        gap.last_evaluated_at = now
        await self.session.flush()
        return gap

    async def add_target(
        self, gap_id: uuid.UUID, target_type: str, target_id: uuid.UUID
    ) -> GapTarget:
        gt = GapTarget(
            gap_id=gap_id,
            corpus_id=self.corpus_id,
            target_type=target_type,
            target_id=target_id,
        )
        self.session.add(gt)
        await self.session.flush()
        return gt

    async def gaps_for_target(
        self, target_type: str, target_id: uuid.UUID,
    ) -> Sequence[uuid.UUID]:
        stmt = select(GapTarget.gap_id).where(
            GapTarget.corpus_id == self.corpus_id,
            GapTarget.target_type == target_type,
            GapTarget.target_id == target_id,
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def gaps_for_targets_batch(
        self, target_type: str, target_ids: set[uuid.UUID],
    ) -> set[uuid.UUID]:
        if not target_ids:
            return set()
        stmt = select(GapTarget.gap_id).where(
            GapTarget.corpus_id == self.corpus_id,
            GapTarget.target_type == target_type,
            GapTarget.target_id.in_(target_ids),
        )
        result = await self.session.execute(stmt)
        return {row[0] for row in result.all()}

    async def open_gaps(self, *, limit: int = 100) -> list[Gap]:
        stmt = (
            select(Gap)
            .where(
                Gap.corpus_id == self.corpus_id,
                Gap.status == "open",
            )
            .order_by(Gap.priority_score.desc().nulls_last(), Gap.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list(
        self,
        *,
        status: str | None = "open",
        kind: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[Gap]:
        stmt = select(Gap).where(Gap.corpus_id == self.corpus_id)
        if status is not None:
            stmt = stmt.where(Gap.status == status)
        if kind is not None:
            stmt = stmt.where(Gap.kind == kind)
        if severity is not None:
            stmt = stmt.where(Gap.severity == severity)
        stmt = stmt.order_by(
            Gap.priority_score.desc().nulls_last(),
            Gap.created_at.desc(),
        ).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
