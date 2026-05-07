"""Rollback handlers: reverse previously-applied repair operations."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.attestation import Attestation
from mapu.models.entity import Handle, IdentityDecisionModel
from mapu.models.lineage import SupersessionEdge
from mapu.models.proposition import Proposition, PropositionParticipant
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
    if operation_type == "merge_handles":
        return await _rollback_merge_handles(session, corpus_id, payload, result)
    if operation_type == "split_handle":
        return await _rollback_split_handle(session, corpus_id, payload, result)
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

    invalidated_ids = result.get("invalidated_attestation_ids", [])
    if not invalidated_ids:
        raise ValueError(
            "Cannot rollback retraction: operation result missing invalidated_attestation_ids"
        )
    att_uuids = [uuid.UUID(x) for x in invalidated_ids]
    await session.execute(
        update(Attestation)
        .where(
            Attestation.id.in_(att_uuids),
            Attestation.corpus_id == corpus_id,
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
        att.status = result.get("prior_status", "accepted")
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


async def _rollback_merge_handles(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    canonical_id = uuid.UUID(result["canonical_handle_id"])
    merged_id = uuid.UUID(result["merged_handle_id"])
    moved_ids = [uuid.UUID(x) for x in result.get("moved_proposition_ids", [])]

    if moved_ids:
        await session.execute(
            update(Proposition)
            .where(
                Proposition.id.in_(moved_ids),
                Proposition.subject_handle_id == canonical_id,
                Proposition.corpus_id == corpus_id,
            )
            .values(subject_handle_id=merged_id)
        )
        await session.execute(
            update(Proposition)
            .where(
                Proposition.id.in_(moved_ids),
                Proposition.object_handle_id == canonical_id,
                Proposition.corpus_id == corpus_id,
            )
            .values(object_handle_id=merged_id)
        )
        await session.execute(
            update(PropositionParticipant)
            .where(
                PropositionParticipant.proposition_id.in_(moved_ids),
                PropositionParticipant.handle_id == canonical_id,
                PropositionParticipant.corpus_id == corpus_id,
            )
            .values(handle_id=merged_id)
        )

    merged_handle = await session.get(Handle, merged_id)
    if merged_handle is not None:
        merged_handle.status = "active"

    raw_decision_id = result.get("identity_decision_id")
    if raw_decision_id:
        await session.execute(
            delete(IdentityDecisionModel).where(
                IdentityDecisionModel.id == uuid.UUID(raw_decision_id),
            )
        )

    await session.flush()

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="rollback_merge_handles",
        actor="system",
        entity_type="handle",
        entity_id=merged_id,
        details={"original_result": result},
    )

    return {"restored_handle_id": str(merged_id), "moved_back": len(moved_ids)}


async def _rollback_split_handle(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    original_id = uuid.UUID(result["original_handle_id"])
    new_id = uuid.UUID(result["new_handle_id"])

    moved_stmt = select(Proposition.id).where(
        Proposition.corpus_id == corpus_id,
        (Proposition.subject_handle_id == new_id)
        | (Proposition.object_handle_id == new_id),
    )
    moved_result = await session.execute(moved_stmt)
    moved_ids = [row[0] for row in moved_result]

    if moved_ids:
        await session.execute(
            update(Proposition)
            .where(
                Proposition.id.in_(moved_ids),
                Proposition.subject_handle_id == new_id,
                Proposition.corpus_id == corpus_id,
            )
            .values(subject_handle_id=original_id)
        )
        await session.execute(
            update(Proposition)
            .where(
                Proposition.id.in_(moved_ids),
                Proposition.object_handle_id == new_id,
                Proposition.corpus_id == corpus_id,
            )
            .values(object_handle_id=original_id)
        )
        await session.execute(
            update(PropositionParticipant)
            .where(
                PropositionParticipant.handle_id == new_id,
                PropositionParticipant.corpus_id == corpus_id,
            )
            .values(handle_id=original_id)
        )

    raw_decision_id = result.get("identity_decision_id")
    if raw_decision_id:
        await session.execute(
            delete(IdentityDecisionModel).where(
                IdentityDecisionModel.id == uuid.UUID(raw_decision_id),
            )
        )

    new_handle = await session.get(Handle, new_id)
    if new_handle is not None:
        await session.delete(new_handle)

    await session.flush()

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="rollback_split_handle",
        actor="system",
        entity_type="handle",
        entity_id=original_id,
        details={"original_result": result},
    )

    return {"original_handle_id": str(original_id), "moved_back": len(moved_ids)}
