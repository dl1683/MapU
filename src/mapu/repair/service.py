"""Repair service: public facade for preview/propose/apply repair operations."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.repair.blast_radius import compute_blast_radius
from mapu.repair.changesets import ChangesetBuilder, execute_changeset
from mapu.repair.types import (
    OperationPayload,
    RepairOperationType,
    RepairPreview,
    RepairRequest,
    RepairResult,
)
from mapu.repos.review import ChangesetRepo
from mapu.types import ChangesetStatus


class RepairService:
    def __init__(self, session: AsyncSession, corpus_id: uuid.UUID) -> None:
        self._session = session
        self._corpus_id = corpus_id

    async def preview_retraction(
        self,
        proposition_id: uuid.UUID,
        retraction_proposition_id: uuid.UUID,
        reason: str = "",
        actor: str = "system",
    ) -> RepairPreview:
        blast = await compute_blast_radius(
            self._session, self._corpus_id, proposition_id,
        )
        ops = (
            OperationPayload(
                operation_type=RepairOperationType.RETRACT.value,
                ordinal=0,
                payload={
                    "proposition_id": str(proposition_id),
                    "retraction_proposition_id": str(retraction_proposition_id),
                    "affected_ids": [str(x) for x in blast.affected_proposition_ids],
                    "reason": reason,
                    "actor": actor,
                },
            ),
        )
        return RepairPreview(
            request=RepairRequest(
                operation_type=RepairOperationType.RETRACT,
                payload={"proposition_id": str(proposition_id)},
                actor=actor,
                reason=reason,
            ),
            blast_radius=blast,
            operations=ops,
            risk_level=blast.risk_level,
        )

    async def preview_supersession(
        self,
        old_proposition_id: uuid.UUID,
        new_proposition_id: uuid.UUID,
        actor: str = "system",
    ) -> RepairPreview:
        blast = await compute_blast_radius(
            self._session, self._corpus_id, old_proposition_id,
        )
        ops = (
            OperationPayload(
                operation_type=RepairOperationType.SUPERSEDE.value,
                ordinal=0,
                payload={
                    "old_proposition_id": str(old_proposition_id),
                    "new_proposition_id": str(new_proposition_id),
                    "affected_ids": [str(x) for x in blast.affected_proposition_ids],
                    "actor": actor,
                },
            ),
        )
        return RepairPreview(
            request=RepairRequest(
                operation_type=RepairOperationType.SUPERSEDE,
                payload={
                    "old_proposition_id": str(old_proposition_id),
                    "new_proposition_id": str(new_proposition_id),
                },
                actor=actor,
            ),
            blast_radius=blast,
            operations=ops,
            risk_level=blast.risk_level,
        )

    async def propose(
        self,
        preview: RepairPreview,
        description: str | None = None,
    ) -> uuid.UUID:
        builder = ChangesetBuilder(
            session=self._session,
            corpus_id=self._corpus_id,
            actor=preview.request.actor,
            actor_type=preview.request.actor_type,
            description=description or preview.request.reason,
            blast_radius=preview.blast_radius,
        )
        for op in preview.operations:
            builder.add_operation(op.operation_type, op.payload)
        return await builder.build()

    async def apply(self, changeset_id: uuid.UUID) -> RepairResult:
        return await execute_changeset(
            self._session, self._corpus_id, changeset_id,
        )

    async def approve_and_apply(self, changeset_id: uuid.UUID) -> RepairResult:
        repo = ChangesetRepo(self._session, self._corpus_id)
        await repo.transition(changeset_id, ChangesetStatus.APPROVED.value)
        return await self.apply(changeset_id)

    async def auto_apply(self, changeset_id: uuid.UUID) -> RepairResult:
        repo = ChangesetRepo(self._session, self._corpus_id)
        await repo.transition(changeset_id, ChangesetStatus.AUTO_APPLIED.value)
        return await self.apply(changeset_id)
