"""Gap repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from mapu.models.gap import Gap, GapTarget
from mapu.repos.base import CorpusScopedRepo


class GapRepo(CorpusScopedRepo[Gap]):
    model = Gap

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

    async def open_gaps(self, *, limit: int = 100) -> list[Gap]:
        stmt = (
            select(Gap)
            .where(
                Gap.corpus_id == self.corpus_id,
                Gap.status == "open",
            )
            .order_by(Gap.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
