"""Review repository for changesets."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from mapu.models.review import Changeset, ChangesetOperation
from mapu.repos.base import CorpusScopedRepo


class ChangesetRepo(CorpusScopedRepo[Changeset]):
    model = Changeset

    async def transition(self, changeset_id: uuid.UUID, new_status: str) -> None:
        stmt = (
            update(Changeset)
            .where(Changeset.id == changeset_id, Changeset.corpus_id == self.corpus_id)
            .values(status=new_status)
        )
        await self.session.execute(stmt)

    async def mark_applied(self, changeset_id: uuid.UUID) -> None:
        stmt = (
            update(Changeset)
            .where(Changeset.id == changeset_id, Changeset.corpus_id == self.corpus_id)
            .values(status="applied", applied_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def append_operation(
        self,
        changeset_id: uuid.UUID,
        ordinal: int,
        operation_type: str,
        payload: dict,
    ) -> ChangesetOperation:
        op = ChangesetOperation(
            changeset_id=changeset_id,
            corpus_id=self.corpus_id,
            ordinal=ordinal,
            operation_type=operation_type,
            payload=payload,
        )
        self.session.add(op)
        await self.session.flush()
        return op

    async def pending_for_review(self) -> list[Changeset]:
        stmt = select(Changeset).where(
            Changeset.corpus_id == self.corpus_id,
            Changeset.status.in_(["proposed"]),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
