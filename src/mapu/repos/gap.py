"""Gap repository."""

from __future__ import annotations

import uuid

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
