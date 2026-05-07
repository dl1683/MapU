"""Rollback handlers: reverse previously-applied repair operations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.attestation import Attestation
from mapu.models.lineage import SupersessionEdge
from mapu.repos.audit import ActivityRepo
from mapu.truth.service import TruthComputeService


async def dispatch_rollback(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    operation_type: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    if operation_type == "retract_proposition":
        return await _rollback_retraction(session, corpus_id, payload, result)
    if operation_type == "supersede_proposition":
        return await _rollback_supersession(session, corpus_id, payload, result)
    if operation_type == "reject_attestation":
        return await _rollback_attestation_rejection(session, corpus_id, payload, result)
    raise ValueError(f"Rollback not supported for operation: {operation_type}")


async def _rollback_retraction(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    proposition_id = uuid.UUID(payload["proposition_id"])

    raw_retraction_id = payload.get("retraction_proposition_id")
    if raw_retraction_id and raw_retraction_id != "None":
        retraction_id = uuid.UUID(raw_retraction_id)
        await session.execute(
            delete(SupersessionEdge)
            .where(
                SupersessionEdge.old_proposition_id == proposition_id,
                SupersessionEdge.new_proposition_id == retraction_id,
                SupersessionEdge.corpus_id == corpus_id,
            )
        )

    await session.execute(
        update(Attestation)
        .where(
            Attestation.proposition_id == proposition_id,
            Attestation.corpus_id == corpus_id,
            Attestation.system_invalidated.isnot(None),
        )
        .values(system_invalidated=None)
    )

    truth_svc = TruthComputeService(session, corpus_id)
    recomputed = await truth_svc.recompute_for_proposition(proposition_id)

    affected_ids = [uuid.UUID(x) for x in payload.get("affected_ids", [])]
    for aid in affected_ids:
        await truth_svc.recompute_for_proposition(aid)

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="rollback_retraction",
        actor="system",
        entity_type="proposition",
        entity_id=proposition_id,
        details={"original_result": result},
    )

    return {"recomputed_states": len(recomputed)}


async def _rollback_supersession(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    old_id = uuid.UUID(payload["old_proposition_id"])
    new_id = uuid.UUID(payload["new_proposition_id"])

    await session.execute(
        delete(SupersessionEdge)
        .where(
            SupersessionEdge.old_proposition_id == old_id,
            SupersessionEdge.new_proposition_id == new_id,
            SupersessionEdge.corpus_id == corpus_id,
        )
    )

    truth_svc = TruthComputeService(session, corpus_id)
    recomputed = await truth_svc.recompute_for_proposition(old_id)

    affected_ids = [uuid.UUID(x) for x in payload.get("affected_ids", [])]
    for aid in affected_ids:
        await truth_svc.recompute_for_proposition(aid)

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="rollback_supersession",
        actor="system",
        entity_type="proposition",
        entity_id=old_id,
        details={"original_result": result},
    )

    return {"recomputed_states": len(recomputed)}


async def _rollback_attestation_rejection(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    attestation_id = uuid.UUID(payload["attestation_id"])

    stmt = select(Attestation).where(
        Attestation.id == attestation_id,
        Attestation.corpus_id == corpus_id,
    )
    att_result = await session.execute(stmt)
    att = att_result.scalar_one_or_none()
    if att is not None:
        att.status = "accepted"
        att.system_invalidated = None
        await session.flush()

        truth_svc = TruthComputeService(session, corpus_id)
        recomputed = await truth_svc.recompute_for_proposition(att.proposition_id)
    else:
        recomputed = []

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="rollback_attestation_rejection",
        actor="system",
        entity_type="attestation",
        entity_id=attestation_id,
        details={"original_result": result},
    )

    return {"recomputed_states": len(recomputed)}
