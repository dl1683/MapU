"""Changeset builder and executor for repair operations."""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.repair.operations import (
    merge_handles,
    reject_attestation,
    retract_proposition,
    split_handle,
    supersede_proposition,
)
from mapu.repair.types import (
    BlastRadiusReport,
    OperationPayload,
    RepairResult,
)
from mapu.repos.review import ChangesetRepo
from mapu.types import ChangesetStatus


class ChangesetBuilder:
    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        actor: str,
        actor_type: str = "system",
        description: str | None = None,
        blast_radius: BlastRadiusReport | None = None,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id
        self._actor = actor
        self._actor_type = actor_type
        self._description = description
        self._blast_radius = blast_radius
        self._operations: list[OperationPayload] = []

    def add_operation(
        self, operation_type: str, payload: dict[str, Any],
    ) -> ChangesetBuilder:
        ordinal = len(self._operations)
        self._operations.append(
            OperationPayload(
                operation_type=operation_type,
                ordinal=ordinal,
                payload=payload,
            )
        )
        return self

    async def build(self) -> uuid.UUID:
        repo = ChangesetRepo(self._session, self._corpus_id)
        risk = self._blast_radius.risk_level.value if self._blast_radius else "low"
        br_dict = self._blast_radius.to_dict() if self._blast_radius else None

        cs = await repo.create_changeset(
            actor=self._actor,
            actor_type=self._actor_type,
            description=self._description,
            risk_level=risk,
            blast_radius=br_dict,
        )

        for op in self._operations:
            await repo.append_operation(
                changeset_id=cs.id,
                ordinal=op.ordinal,
                operation_type=op.operation_type,
                payload=op.payload,
            )

        return cs.id


_KNOWN_OPERATIONS = {
    "retract_proposition",
    "supersede_proposition",
    "reject_attestation",
    "merge_handles",
    "split_handle",
}


async def execute_changeset(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    changeset_id: uuid.UUID,
) -> RepairResult:
    repo = ChangesetRepo(session, corpus_id)
    cs = await repo.get(changeset_id)
    if cs is None:
        raise ValueError(f"Changeset {changeset_id} not found")

    if cs.status not in (
        ChangesetStatus.APPROVED.value,
        ChangesetStatus.AUTO_APPLIED.value,
    ):
        raise ValueError(
            f"Changeset {changeset_id} has status '{cs.status}', "
            "must be 'approved' or 'auto_applied' to execute"
        )

    operations = await repo.operations_for_changeset(changeset_id)

    result = RepairResult(
        changeset_id=changeset_id,
        success=False,
        operations_executed=0,
        recomputed_propositions=0,
        gaps_created=0,
    )

    savepoint = await session.begin_nested()
    try:
        for op in operations:
            if op.operation_type not in _KNOWN_OPERATIONS:
                raise ValueError(f"Unknown operation type: {op.operation_type}")

            op_result = await _dispatch_operation(
                session, corpus_id, op.operation_type, op.payload,
            )
            await repo.record_operation_result(op.id, op_result)
            result.operations_executed += 1
            result.recomputed_propositions += op_result.get("recomputed_states", 0)
            if "gap_id" in op_result:
                result.gaps_created += 1

        await savepoint.commit()
        await repo.mark_applied(changeset_id)
        result.success = True

    except Exception as exc:
        await savepoint.rollback()
        result.errors.append(str(exc))
        await repo.mark_failed(changeset_id)

    return result


async def _dispatch_operation(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    operation_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if operation_type == "retract_proposition":
        raw_retraction_id = payload.get("retraction_proposition_id")
        retraction_id = (
            uuid.UUID(raw_retraction_id)
            if raw_retraction_id is not None and raw_retraction_id != "None"
            else None
        )
        return await retract_proposition(
            session=session,
            corpus_id=corpus_id,
            proposition_id=uuid.UUID(payload["proposition_id"]),
            retraction_proposition_id=retraction_id,
            affected_ids=tuple(uuid.UUID(x) for x in payload.get("affected_ids", [])),
            reason=payload.get("reason", ""),
            actor=payload.get("actor", "system"),
            recompute_only_ids=tuple(
                uuid.UUID(x) for x in payload.get("recompute_only_ids", [])
            ),
        )
    if operation_type == "supersede_proposition":
        return await supersede_proposition(
            session=session,
            corpus_id=corpus_id,
            old_proposition_id=uuid.UUID(payload["old_proposition_id"]),
            new_proposition_id=uuid.UUID(payload["new_proposition_id"]),
            affected_ids=tuple(uuid.UUID(x) for x in payload.get("affected_ids", [])),
            actor=payload.get("actor", "system"),
            recompute_only_ids=tuple(
                uuid.UUID(x) for x in payload.get("recompute_only_ids", [])
            ),
        )
    if operation_type == "reject_attestation":
        return await reject_attestation(
            session=session,
            corpus_id=corpus_id,
            attestation_id=uuid.UUID(payload["attestation_id"]),
            actor=payload.get("actor", "system"),
            reason=payload.get("reason", ""),
        )
    if operation_type == "merge_handles":
        return await merge_handles(
            session=session,
            corpus_id=corpus_id,
            canonical_handle_id=uuid.UUID(payload["canonical_handle_id"]),
            merged_handle_id=uuid.UUID(payload["merged_handle_id"]),
            actor=payload.get("actor", "system"),
        )
    if operation_type == "split_handle":
        return await split_handle(
            session=session,
            corpus_id=corpus_id,
            handle_id=uuid.UUID(payload["handle_id"]),
            new_handle_name=payload["new_handle_name"],
            new_handle_kind=payload["new_handle_kind"],
            proposition_ids_to_move=[uuid.UUID(x) for x in payload["proposition_ids_to_move"]],
            actor=payload.get("actor", "system"),
        )
    raise ValueError(f"Unknown operation type: {operation_type}")


async def rollback_changeset(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    changeset_id: uuid.UUID,
) -> RepairResult:
    from mapu.repair.rollback import dispatch_rollback

    repo = ChangesetRepo(session, corpus_id)
    cs = await repo.get(changeset_id)
    if cs is None:
        raise ValueError(f"Changeset {changeset_id} not found")

    if cs.status != ChangesetStatus.APPLIED.value:
        raise ValueError(
            f"Changeset {changeset_id} has status '{cs.status}', "
            "must be 'applied' to roll back"
        )

    operations = await repo.operations_for_changeset(changeset_id)

    result = RepairResult(
        changeset_id=changeset_id,
        success=False,
        operations_executed=0,
        recomputed_propositions=0,
        gaps_created=0,
    )

    savepoint = await session.begin_nested()
    try:
        for op in reversed(operations):
            if op.result is None:
                msg = (
                    f"Skipped operation {op.operation_type} "
                    f"(ordinal {op.ordinal}): no recorded result"
                )
                result.errors.append(msg)
                continue
            rollback_result = await dispatch_rollback(
                session, corpus_id, op.operation_type, op.payload, op.result,
            )
            result.operations_executed += 1
            result.recomputed_propositions += rollback_result.get("recomputed_states", 0)

        await savepoint.commit()
        if result.errors:
            result.success = False
            with contextlib.suppress(Exception):
                await repo.transition(changeset_id, ChangesetStatus.ROLLBACK_FAILED.value)
        else:
            await repo.mark_rolled_back(changeset_id)
            result.success = True

    except Exception as exc:
        await savepoint.rollback()
        result.errors.append(str(exc))
        try:
            await repo.transition(changeset_id, ChangesetStatus.ROLLBACK_FAILED.value)
        except Exception as inner_exc:
            result.errors.append(f"Failed to mark rollback_failed: {inner_exc}")

    return result
