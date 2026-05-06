"""Context repository for situations and query views."""

from __future__ import annotations

from sqlalchemy import select

from mapu.models.context import QueryView, Situation
from mapu.repos.base import CorpusScopedRepo


class SituationRepo(CorpusScopedRepo[Situation]):
    model = Situation


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
