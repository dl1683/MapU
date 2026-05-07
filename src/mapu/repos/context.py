"""Context repository for situations and query views."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from mapu.models.context import QueryView, Situation
from mapu.repos.base import CorpusScopedRepo


class SituationRepo(CorpusScopedRepo[Situation]):
    model = Situation

    async def get_or_create_default(self) -> Situation:
        stmt = select(Situation).where(
            Situation.corpus_id == self.corpus_id,
            Situation.kind == "default",
        ).limit(1)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        situation = Situation(
            id=uuid.uuid4(),
            corpus_id=self.corpus_id,
            kind="default",
            name="default",
        )
        try:
            async with self.session.begin_nested():
                self.session.add(situation)
                await self.session.flush()
        except Exception:
            result = await self.session.execute(stmt)
            return result.scalar_one()
        return situation


class QueryViewRepo(CorpusScopedRepo[QueryView]):
    model = QueryView

    async def get_default(self) -> QueryView | None:
        stmt = select(QueryView).where(
            QueryView.corpus_id == self.corpus_id,
            QueryView.is_default.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_default(self, view: QueryView) -> None:
        current = await self.get_default()
        if current and current.id != view.id:
            current.is_default = False
        view.is_default = True
        await self.session.flush()
