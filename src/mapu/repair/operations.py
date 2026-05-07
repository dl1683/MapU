"""Repair operation handlers: retract, supersede, reject, split, merge."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.extraction.grounding import _compute_semantic_key
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
    retraction_proposition_id: uuid.UUID | None,
    affected_ids: tuple[uuid.UUID, ...],
    reason: str,
    actor: str,
    recompute_only_ids: tuple[uuid.UUID, ...] = (),
) -> dict[str, Any]:
    if retraction_proposition_id is not None and retraction_proposition_id != proposition_id:
        supersession_repo = SupersessionEdgeRepo(session, corpus_id)
        await supersession_repo.add_supersession(
            old_id=proposition_id,
            new_id=retraction_proposition_id,
            supersession_type="retraction",
            effective_at=datetime.now(UTC),
        )

    now = datetime.now(UTC)
    active_atts = await session.execute(
        select(Attestation.id)
        .where(
            Attestation.proposition_id == proposition_id,
            Attestation.corpus_id == corpus_id,
            Attestation.system_invalidated.is_(None),
        )
    )
    invalidated_att_ids = [str(row[0]) for row in active_atts.all()]

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

    for aid in (*affected_ids, *recompute_only_ids):
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
            "retraction_proposition_id": (
                str(retraction_proposition_id) if retraction_proposition_id else None
            ),
            "affected_count": len(affected_ids),
        },
    )

    return {
        "retracted_proposition_id": str(proposition_id),
        "invalidated_attestation_ids": invalidated_att_ids,
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
    recompute_only_ids: tuple[uuid.UUID, ...] = (),
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

    for aid in (*affected_ids, *recompute_only_ids):
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

    prior_status = att.status
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
        "prior_status": prior_status,
        "recomputed_states": len(recomputed),
    }


async def _recompute_semantic_keys(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    proposition_ids: list[uuid.UUID],
) -> int:
    """Recompute semantic_key for propositions after handle changes."""
    if not proposition_ids:
        return 0
    stmt = select(Proposition).where(
        Proposition.id.in_(proposition_ids),
        Proposition.corpus_id == corpus_id,
    )
    result = await session.execute(stmt)
    props = result.scalars().all()
    pending: list[tuple[Proposition, str]] = []
    for prop in props:
        valid_range = None
        if prop.valid_range is not None:
            valid_range = (prop.valid_range.lower, prop.valid_range.upper)
        new_key = _compute_semantic_key(
            frame_type=prop.frame_type,
            subject_handle_id=prop.subject_handle_id,
            predicate=prop.predicate,
            object_handle_id=prop.object_handle_id,
            value=prop.value,
            polarity=prop.polarity,
            modality=prop.modality,
            qualifiers=prop.qualifiers,
            valid_range=valid_range,
        )
        if new_key != prop.semantic_key:
            pending.append((prop, new_key))

    seen_keys: dict[str, uuid.UUID] = {}
    for prop, new_key in pending:
        if new_key in seen_keys:
            raise ValueError(
                f"Semantic key collision: propositions {seen_keys[new_key]} and {prop.id} "
                f"would both have key {new_key[:40]}... after handle change"
            )
        seen_keys[new_key] = prop.id

    new_keys = set(seen_keys.keys())
    if new_keys:
        collision_stmt = select(Proposition.semantic_key).where(
            Proposition.corpus_id == corpus_id,
            Proposition.semantic_key.in_(new_keys),
            ~Proposition.id.in_(proposition_ids),
        )
        collision_result = await session.execute(collision_stmt)
        existing_keys = {row[0] for row in collision_result}
        for prop, new_key in pending:
            if new_key in existing_keys:
                raise ValueError(
                    f"Semantic key collision after handle change for proposition {prop.id}: "
                    f"another proposition already has key {new_key[:40]}..."
                )

    count = 0
    for prop, new_key in pending:
        prop.semantic_key = new_key
        count += 1
    if count:
        await session.flush()
    return count


async def merge_handles(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    canonical_handle_id: uuid.UUID,
    merged_handle_id: uuid.UUID,
    actor: str,
) -> dict[str, Any]:
    if canonical_handle_id == merged_handle_id:
        raise ValueError("Cannot merge a handle with itself")

    stmt = select(Handle).where(
        Handle.id == merged_handle_id, Handle.corpus_id == corpus_id,
    )
    result = await session.execute(stmt)
    merged = result.scalar_one_or_none()
    if merged is None:
        raise ValueError(f"Handle {merged_handle_id} not found")

    stmt = select(Handle).where(Handle.id == canonical_handle_id, Handle.corpus_id == corpus_id)
    result = await session.execute(stmt)
    canonical = result.scalar_one_or_none()
    if canonical is None:
        raise ValueError(f"Handle {canonical_handle_id} not found")

    moved_stmt = select(
        Proposition.id, Proposition.subject_handle_id, Proposition.object_handle_id,
    ).where(
        Proposition.corpus_id == corpus_id,
        (Proposition.subject_handle_id == merged_handle_id)
        | (Proposition.object_handle_id == merged_handle_id),
    )
    moved_result = await session.execute(moved_stmt)
    prop_snapshots = [
        {
            "id": str(row[0]),
            "prior_subject": str(row[1]),
            "prior_object": str(row[2]) if row[2] else None,
        }
        for row in moved_result
    ]
    moved_prop_ids = [uuid.UUID(s["id"]) for s in prop_snapshots]

    participant_stmt = select(
        PropositionParticipant.id,
        PropositionParticipant.handle_id,
    ).where(
        PropositionParticipant.handle_id == merged_handle_id,
        PropositionParticipant.corpus_id == corpus_id,
    )
    part_result = await session.execute(participant_stmt)
    participant_snapshots = [
        {"id": str(row[0]), "prior_handle": str(row[1])}
        for row in part_result
    ]

    prior_canonical_aliases = list(canonical.aliases or [])

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

    await _recompute_semantic_keys(session, corpus_id, moved_prop_ids)

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
        "moved_proposition_ids": [str(p) for p in moved_prop_ids],
        "proposition_snapshots": prop_snapshots,
        "participant_snapshots": participant_snapshots,
        "prior_canonical_aliases": prior_canonical_aliases,
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

    if proposition_ids_to_move:
        stmt = select(Proposition).where(
            Proposition.id.in_(proposition_ids_to_move),
            Proposition.corpus_id == corpus_id,
        )
        result = await session.execute(stmt)
        for prop in result.scalars().all():
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

    await _recompute_semantic_keys(
        session, corpus_id, proposition_ids_to_move,
    )

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
        "moved_proposition_ids": [str(p) for p in proposition_ids_to_move],
        "identity_decision_id": str(identity.id),
    }
