"""Blast radius computation for repair operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.proposition import Proposition
from mapu.repair.types import BlastRadiusReport, RiskLevel
from mapu.repos.gap import GapRepo
from mapu.repos.lineage import (
    DerivationEdgeRepo,
    DescendantInfo,
    RepairCascadeDepthExceeded,
)


def _classify_risk(
    affected_count: int, depth: int, depth_limited: bool,
) -> RiskLevel:
    if depth_limited:
        return RiskLevel.CRITICAL
    if affected_count > 100 or depth > 10:
        return RiskLevel.HIGH
    if affected_count > 10 or depth > 5:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


async def compute_blast_radius(
    session: AsyncSession,
    corpus_id: uuid.UUID,
    proposition_id: uuid.UUID,
    max_depth: int = 50,
) -> BlastRadiusReport:
    derivation_repo = DerivationEdgeRepo(session, corpus_id)
    gap_repo = GapRepo(session, corpus_id)

    depth_limited = False
    max_depth_seen = 0

    try:
        descendants = await derivation_repo.descendants_with_depth(
            proposition_id, max_depth=max_depth,
        )
    except RepairCascadeDepthExceeded:
        descendants = await _safe_descendants(derivation_repo, proposition_id, max_depth)
        depth_limited = True

    if descendants:
        max_depth_seen = max(d.depth for d in descendants)

    all_descendant_ids = {d.id for d in descendants}

    affected_ids: list[uuid.UUID] = []
    recompute_only_ids: list[uuid.UUID] = []

    for desc in descendants:
        parent_ids = await derivation_repo.parents(desc.id)
        surviving_parents = [
            p for p in parent_ids
            if p != proposition_id and p not in all_descendant_ids
        ]
        if surviving_parents:
            recompute_only_ids.append(desc.id)
        else:
            affected_ids.append(desc.id)

    all_prop_ids = [proposition_id, *affected_ids, *recompute_only_ids]
    handle_ids: set[uuid.UUID] = set()
    for pid in all_prop_ids:
        stmt = select(
            Proposition.subject_handle_id, Proposition.object_handle_id,
        ).where(
            Proposition.id == pid,
            Proposition.corpus_id == corpus_id,
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row:
            handle_ids.add(row[0])
            if row[1] is not None:
                handle_ids.add(row[1])

    gap_ids: set[uuid.UUID] = set()
    for pid in all_prop_ids:
        gids = await gap_repo.gaps_for_target("proposition", pid)
        gap_ids.update(gids)

    risk = _classify_risk(
        len(affected_ids) + len(recompute_only_ids), max_depth_seen, depth_limited,
    )

    return BlastRadiusReport(
        root_proposition_id=proposition_id,
        affected_proposition_ids=tuple(affected_ids),
        recompute_only_proposition_ids=tuple(recompute_only_ids),
        affected_handle_ids=tuple(handle_ids),
        affected_gap_ids=tuple(gap_ids),
        max_depth_seen=max_depth_seen,
        depth_limited=depth_limited,
        risk_level=risk,
    )


async def _safe_descendants(
    repo: DerivationEdgeRepo,
    proposition_id: uuid.UUID,
    max_depth: int,
) -> list[DescendantInfo]:

    visited: set[uuid.UUID] = set()
    result: list[DescendantInfo] = []
    queue: list[tuple[uuid.UUID, int]] = [(proposition_id, 0)]

    while queue:
        current_id, depth = queue.pop(0)
        if depth >= max_depth or current_id in visited:
            continue
        if current_id != proposition_id:
            visited.add(current_id)
            result.append(DescendantInfo(id=current_id, depth=depth))

        children = await repo.children(current_id)
        for child_id in children:
            if child_id not in visited:
                queue.append((child_id, depth + 1))

    return result
