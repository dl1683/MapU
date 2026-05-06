"""Activity (audit) repository — append-only."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from mapu.models.audit import Activity
from mapu.repos.base import CorpusScopedRepo


class ActivityRepo(CorpusScopedRepo[Activity]):
    model = Activity

    async def log(
        self,
        event_type: str,
        actor: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> Activity:
        entry = Activity(
            corpus_id=self.corpus_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
            actor=actor,
        )
        return await self.add(entry)

    async def for_entity(
        self, entity_type: str, entity_id: uuid.UUID, *, limit: int = 50
    ) -> list[Activity]:
        stmt = (
            select(Activity)
            .where(
                Activity.corpus_id == self.corpus_id,
                Activity.entity_type == entity_type,
                Activity.entity_id == entity_id,
            )
            .order_by(Activity.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
