"""Review repository for changesets."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from mapu.models.review import Changeset, ChangesetOperation
from mapu.repos.base import CorpusScopedRepo
from mapu.truth.state_machine import validate_changeset_transition
from mapu.types import ChangesetStatus


class ChangesetRepo(CorpusScopedRepo[Changeset]):
    model = Changeset

    async def transition(self, changeset_id: uuid.UUID, new_status: str) -> None:
        current = await self.get(changeset_id)
        if current is None:
            raise ValueError(f"Changeset {changeset_id} not found in corpus {self.corpus_id}")
        validate_changeset_transition(
            ChangesetStatus(current.status), ChangesetStatus(new_status),
        )
        current.status = new_status
        await self.session.flush()

    async def mark_applied(self, changeset_id: uuid.UUID) -> None:
        await self.transition(changeset_id, ChangesetStatus.APPLIED.value)
        current = await self.get(changeset_id)
        if current is not None:
            current.applied_at = datetime.now(UTC)
            await self.session.flush()

    async def append_operation(
        self,
        changeset_id: uuid.UUID,
        ordinal: int,
        operation_type: str,
        payload: dict[str, Any],
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
