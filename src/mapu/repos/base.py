"""Base repository with corpus isolation enforcement."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.db.base import Base

T = TypeVar("T", bound=Base)


class BaseRepo(Generic[T]):
    """Generic repository for tables without corpus scoping."""

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> T | None:
        return await self.session.get(self.model, id)

    async def add(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[T]:
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()


class CorpusScopedRepo(Generic[T]):
    """Repository scoped to a single corpus. Every query filters by corpus_id."""

    model: type[T]

    def __init__(self, session: AsyncSession, corpus_id: uuid.UUID) -> None:
        self.session = session
        self.corpus_id = corpus_id

    async def get(self, id: uuid.UUID) -> T | None:
        stmt = select(self.model).where(
            self.model.id == id,  # type: ignore[attr-defined]
            self.model.corpus_id == self.corpus_id,  # type: ignore[attr-defined]
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, entity: T) -> T:
        entity_corpus = getattr(entity, "corpus_id", None)
        if entity_corpus is None:
            object.__setattr__(entity, "corpus_id", self.corpus_id)
        elif entity_corpus != self.corpus_id:
            raise ValueError(
                f"Entity corpus_id {entity_corpus} does not match repo scope {self.corpus_id}"
            )
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[T]:
        stmt = (
            select(self.model)
            .where(self.model.corpus_id == self.corpus_id)  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete(self, entity: T) -> None:
        if getattr(entity, "corpus_id", None) != self.corpus_id:
            raise ValueError("Cannot delete entity from different corpus")
        await self.session.delete(entity)
        await self.session.flush()
