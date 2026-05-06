"""Entity repository for handles and identity decisions."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from mapu.models.entity import Handle, IdentityDecisionModel
from mapu.repos.base import CorpusScopedRepo


class HandleRepo(CorpusScopedRepo[Handle]):
    model = Handle

    async def get_by_name_kind(self, canonical_name: str, kind: str) -> Handle | None:
        stmt = select(Handle).where(
            Handle.corpus_id == self.corpus_id,
            Handle.canonical_name == canonical_name,
            Handle.kind == kind,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def active_handles(
        self, *, limit: int = 100, offset: int = 0
    ) -> list[Handle]:
        stmt = (
            select(Handle)
            .where(Handle.corpus_id == self.corpus_id, Handle.status == "active")
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_by_name(
        self, query: str, *, limit: int = 20
    ) -> list[Handle]:
        stmt = (
            select(Handle)
            .where(
                Handle.corpus_id == self.corpus_id,
                Handle.status == "active",
                Handle.canonical_name.ilike(f"%{query}%"),
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class IdentityDecisionRepo(CorpusScopedRepo[IdentityDecisionModel]):
    model = IdentityDecisionModel

    async def active_for_handle(self, handle_id: uuid.UUID) -> list[IdentityDecisionModel]:
        stmt = select(IdentityDecisionModel).where(
            IdentityDecisionModel.corpus_id == self.corpus_id,
            IdentityDecisionModel.invalidated_at.is_(None),
            (IdentityDecisionModel.handle_a_id == handle_id)
            | (IdentityDecisionModel.handle_b_id == handle_id),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
