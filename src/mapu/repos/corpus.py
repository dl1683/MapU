"""Corpus repository."""

from __future__ import annotations

from sqlalchemy import select

from mapu.models.corpus import Corpus
from mapu.repos.base import BaseRepo


class CorpusRepo(BaseRepo[Corpus]):
    model = Corpus

    async def get_by_name(self, name: str) -> Corpus | None:
        stmt = select(Corpus).where(Corpus.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
