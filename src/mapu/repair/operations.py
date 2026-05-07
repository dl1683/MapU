"""Repair operation handlers: retract, supersede, reject, split, merge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.attestation import Attestation
from mapu.models.entity import Handle, IdentityDecisionModel
from mapu.models.proposition import Proposition, PropositionParticipant
from mapu.repos.audit import ActivityRepo
from mapu.repos.gap import GapRepo
from mapu.repos.lineage import SupersessionEdgeRepo
from mapu.truth.service import TruthComputeService


async def retract_proposition(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    proposition_id: uuid.UUID,
    retraction_proposition_id: uuid.UUID,
    affected_ids: tuple[uuid.UUID, ...],
    reason: str,
    actor: str,
) -> dict[str, Any]:
    supersession_repo = SupersessionEdgeRepo(session, corpus_id)
    await supersession_repo.add_supersession(
        old_id=proposition_id,
        new_id=retraction_proposition_id,
        supersession_type="retraction",
        effective_at=datetime.now(UTC),
    )

    now = datetime.now(UTC)
    await session.execute(
        update(Attestation)
        .where(
            Attestation.proposition_id == proposition_id,
            Attestation.corpus_id == corpus_id,
            Attestation.system_invalidated.is_(None),
        )
        .values(system_invalidated=now)
    )

    truth_svc = TruthComputeService(session, corpus_id)
    recomputed = await truth_svc.recompute_for_proposition(proposition_id)

    for aid in affected_ids:
        await truth_svc.recompute_for_proposition(aid)

    gap_repo = GapRepo(session, corpus_id)
    from mapu.models.gap import Gap
    gap = Gap(
        corpus_id=corpus_id,
        kind="retraction",
        description=f"Proposition retracted: {reason}",
        severity="moderate",
        detected_by=actor,
    )
    gap = await gap_repo.add(gap)
    await gap_repo.add_target(gap.id, "proposition", proposition_id)

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="retraction",
        actor=actor,
        entity_type="proposition",
        entity_id=proposition_id,
        details={
            "reason": reason,
            "retraction_proposition_id": str(retraction_proposition_id),
            "affected_count": len(affected_ids),
        },
    )

    return {
        "retracted_proposition_id": str(proposition_id),
        "recomputed_states": len(recomputed),
        "gap_id": str(gap.id),
    }


async def supersede_proposition(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    old_proposition_id: uuid.UUID,
    new_proposition_id: uuid.UUID,
    affected_ids: tuple[uuid.UUID, ...],
    actor: str,
) -> dict[str, Any]:
    supersession_repo = SupersessionEdgeRepo(session, corpus_id)
    await supersession_repo.add_supersession(
        old_id=old_proposition_id,
        new_id=new_proposition_id,
        supersession_type="supersession",
        effective_at=datetime.now(UTC),
    )

    truth_svc = TruthComputeService(session, corpus_id)
    recomputed = await truth_svc.recompute_for_proposition(old_proposition_id)

    for aid in affected_ids:
        await truth_svc.recompute_for_proposition(aid)

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="supersession",
        actor=actor,
        entity_type="proposition",
        entity_id=old_proposition_id,
        details={
            "new_proposition_id": str(new_proposition_id),
            "affected_count": len(affected_ids),
        },
    )

    return {
        "old_proposition_id": str(old_proposition_id),
        "new_proposition_id": str(new_proposition_id),
        "recomputed_states": len(recomputed),
    }


async def reject_attestation(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    attestation_id: uuid.UUID,
    actor: str,
    reason: str = "",
) -> dict[str, Any]:
    stmt = select(Attestation).where(
        Attestation.id == attestation_id,
        Attestation.corpus_id == corpus_id,
    )
    result = await session.execute(stmt)
    att = result.scalar_one_or_none()
    if att is None:
        raise ValueError(f"Attestation {attestation_id} not found")

    att.status = "rejected"
    att.system_invalidated = datetime.now(UTC)
    await session.flush()

    truth_svc = TruthComputeService(session, corpus_id)
    recomputed = await truth_svc.recompute_for_proposition(att.proposition_id)

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="attestation_rejection",
        actor=actor,
        entity_type="attestation",
        entity_id=attestation_id,
        details={
            "proposition_id": str(att.proposition_id),
            "reason": reason,
        },
    )

    return {
        "attestation_id": str(attestation_id),
        "proposition_id": str(att.proposition_id),
        "recomputed_states": len(recomputed),
    }


async def merge_handles(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    canonical_handle_id: uuid.UUID,
    merged_handle_id: uuid.UUID,
    actor: str,
) -> dict[str, Any]:
    stmt = select(Handle).where(Handle.id == merged_handle_id, Handle.corpus_id == corpus_id)
    result = await session.execute(stmt)
    merged = result.scalar_one_or_none()
    if merged is None:
        raise ValueError(f"Handle {merged_handle_id} not found")

    stmt = select(Handle).where(Handle.id == canonical_handle_id, Handle.corpus_id == corpus_id)
    result = await session.execute(stmt)
    canonical = result.scalar_one_or_none()
    if canonical is None:
        raise ValueError(f"Handle {canonical_handle_id} not found")

    await session.execute(
        update(Proposition)
        .where(
            Proposition.subject_handle_id == merged_handle_id,
            Proposition.corpus_id == corpus_id,
        )
        .values(subject_handle_id=canonical_handle_id)
    )
    await session.execute(
        update(Proposition)
        .where(
            Proposition.object_handle_id == merged_handle_id,
            Proposition.corpus_id == corpus_id,
        )
        .values(object_handle_id=canonical_handle_id)
    )
    await session.execute(
        update(PropositionParticipant)
        .where(
            PropositionParticipant.handle_id == merged_handle_id,
            PropositionParticipant.corpus_id == corpus_id,
        )
        .values(handle_id=canonical_handle_id)
    )

    existing_aliases = set(canonical.aliases or [])
    existing_aliases.add(merged.canonical_name)
    existing_aliases.update(merged.aliases or [])
    canonical.aliases = list(existing_aliases)

    merged.status = "merged"
    await session.flush()

    identity = IdentityDecisionModel(
        corpus_id=corpus_id,
        handle_a_id=canonical_handle_id,
        handle_b_id=merged_handle_id,
        decision="same_entity",
        confidence=1.0,
        evidence={"method": "manual_merge", "actor": actor},
        decided_by=actor,
    )
    session.add(identity)
    await session.flush()

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="handle_merge",
        actor=actor,
        entity_type="handle",
        entity_id=canonical_handle_id,
        details={
            "merged_handle_id": str(merged_handle_id),
            "canonical_handle_id": str(canonical_handle_id),
        },
    )

    return {
        "canonical_handle_id": str(canonical_handle_id),
        "merged_handle_id": str(merged_handle_id),
        "identity_decision_id": str(identity.id),
    }


async def split_handle(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    handle_id: uuid.UUID,
    new_handle_name: str,
    new_handle_kind: str,
    proposition_ids_to_move: list[uuid.UUID],
    actor: str,
) -> dict[str, Any]:
    new_handle = Handle(
        corpus_id=corpus_id,
        canonical_name=new_handle_name,
        kind=new_handle_kind,
    )
    session.add(new_handle)
    await session.flush()

    for pid in proposition_ids_to_move:
        stmt = select(Proposition).where(
            Proposition.id == pid, Proposition.corpus_id == corpus_id,
        )
        result = await session.execute(stmt)
        prop = result.scalar_one_or_none()
        if prop is None:
            continue
        if prop.subject_handle_id == handle_id:
            prop.subject_handle_id = new_handle.id
        if prop.object_handle_id == handle_id:
            prop.object_handle_id = new_handle.id

    await session.execute(
        update(PropositionParticipant)
        .where(
            PropositionParticipant.handle_id == handle_id,
            PropositionParticipant.corpus_id == corpus_id,
            PropositionParticipant.proposition_id.in_(proposition_ids_to_move),
        )
        .values(handle_id=new_handle.id)
    )
    await session.flush()

    identity = IdentityDecisionModel(
        corpus_id=corpus_id,
        handle_a_id=handle_id,
        handle_b_id=new_handle.id,
        decision="different_entity",
        confidence=1.0,
        evidence={"method": "manual_split", "actor": actor},
        decided_by=actor,
    )
    session.add(identity)
    await session.flush()

    activity_repo = ActivityRepo(session, corpus_id)
    await activity_repo.log(
        event_type="handle_split",
        actor=actor,
        entity_type="handle",
        entity_id=handle_id,
        details={
            "new_handle_id": str(new_handle.id),
            "propositions_moved": len(proposition_ids_to_move),
        },
    )

    return {
        "original_handle_id": str(handle_id),
        "new_handle_id": str(new_handle.id),
        "propositions_moved": len(proposition_ids_to_move),
        "identity_decision_id": str(identity.id),
    }
