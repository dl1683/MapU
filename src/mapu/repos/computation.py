"""Computation repository."""

from __future__ import annotations

from sqlalchemy import select

from mapu.models.computation import ComputationRun, ComputationSpec
from mapu.repos.base import CorpusScopedRepo


class ComputationSpecRepo(CorpusScopedRepo[ComputationSpec]):
    model = ComputationSpec

    async def get_by_name_version(self, name: str, version: int) -> ComputationSpec | None:
        stmt = select(ComputationSpec).where(
            ComputationSpec.corpus_id == self.corpus_id,
            ComputationSpec.name == name,
            ComputationSpec.version == version,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ComputationRunRepo(CorpusScopedRepo[ComputationRun]):
    model = ComputationRun
