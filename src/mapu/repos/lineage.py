"""Lineage repository for derivation and supersession edges."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import exists, select, text

from mapu.models.lineage import DerivationEdge, SupersessionEdge
from mapu.repos.base import CorpusScopedRepo

MAX_REPAIR_CASCADE_DEPTH = 50


class RepairCascadeDepthExceeded(Exception):
    """Raised when the blast radius traversal hits the depth limit."""

    def __init__(self, proposition_id: uuid.UUID, max_depth: int) -> None:
        super().__init__(
            f"Repair cascade for {proposition_id} exceeded depth limit {max_depth}"
        )
        self.proposition_id = proposition_id
        self.max_depth = max_depth


@dataclass(frozen=True)
class DescendantInfo:
    id: uuid.UUID
    depth: int


class DerivationEdgeRepo(CorpusScopedRepo[DerivationEdge]):
    model = DerivationEdge

    async def add_derivation(
        self,
        parent_id: uuid.UUID,
        child_id: uuid.UUID,
        derivation_type: str,
        derivation_method: str,
        confidence: float | None = None,
    ) -> DerivationEdge:
        edge = DerivationEdge(
            corpus_id=self.corpus_id,
            parent_proposition_id=parent_id,
            child_proposition_id=child_id,
            derivation_type=derivation_type,
            derivation_method=derivation_method,
            confidence=confidence,
        )
        return await self.add(edge)

    async def children(self, proposition_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(DerivationEdge.child_proposition_id).where(
            DerivationEdge.parent_proposition_id == proposition_id,
            DerivationEdge.corpus_id == self.corpus_id,
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def parents(self, proposition_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(DerivationEdge.parent_proposition_id).where(
            DerivationEdge.child_proposition_id == proposition_id,
            DerivationEdge.corpus_id == self.corpus_id,
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def parents_batch(
        self, proposition_ids: set[uuid.UUID],
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        if not proposition_ids:
            return {}
        stmt = select(
            DerivationEdge.child_proposition_id,
            DerivationEdge.parent_proposition_id,
        ).where(
            DerivationEdge.child_proposition_id.in_(proposition_ids),
            DerivationEdge.corpus_id == self.corpus_id,
        )
        result = await self.session.execute(stmt)
        mapping: dict[uuid.UUID, list[uuid.UUID]] = {pid: [] for pid in proposition_ids}
        for row in result:
            mapping[row[0]].append(row[1])
        return mapping

    async def descendants_bounded(
        self, proposition_id: uuid.UUID, max_depth: int = MAX_REPAIR_CASCADE_DEPTH
    ) -> set[uuid.UUID]:
        """Compute bounded blast radius using recursive CTE.

        Raises RepairCascadeDepthExceeded if any node reaches max_depth,
        indicating the true blast radius may extend further.
        """
        info = await self.descendants_with_depth(proposition_id, max_depth)
        return {d.id for d in info}

    async def descendants_with_depth(
        self, proposition_id: uuid.UUID, max_depth: int = MAX_REPAIR_CASCADE_DEPTH,
    ) -> list[DescendantInfo]:
        stmt = text("""
            WITH RECURSIVE descendants AS (
                SELECT child_proposition_id AS id, 1 AS depth
                FROM derivation_edge
                WHERE parent_proposition_id = :prop_id AND corpus_id = :corpus_id
                UNION
                SELECT de.child_proposition_id, d.depth + 1
                FROM derivation_edge de
                JOIN descendants d ON de.parent_proposition_id = d.id
                WHERE de.corpus_id = :corpus_id AND d.depth < :max_depth
            )
            SELECT id, depth FROM descendants
        """)
        result = await self.session.execute(
            stmt,
            {"prop_id": proposition_id, "corpus_id": self.corpus_id, "max_depth": max_depth},
        )
        rows = list(result)
        infos: list[DescendantInfo] = []
        for row in rows:
            if row[1] >= max_depth:
                raise RepairCascadeDepthExceeded(proposition_id, max_depth)
            infos.append(DescendantInfo(id=row[0], depth=row[1]))
        return infos

    async def ancestors_bounded(
        self, proposition_id: uuid.UUID, max_depth: int = MAX_REPAIR_CASCADE_DEPTH,
    ) -> list[DescendantInfo]:
        stmt = text("""
            WITH RECURSIVE ancestors AS (
                SELECT parent_proposition_id AS id, 1 AS depth
                FROM derivation_edge
                WHERE child_proposition_id = :prop_id AND corpus_id = :corpus_id
                UNION
                SELECT de.parent_proposition_id, a.depth + 1
                FROM derivation_edge de
                JOIN ancestors a ON de.child_proposition_id = a.id
                WHERE de.corpus_id = :corpus_id AND a.depth < :max_depth
            )
            SELECT id, depth FROM ancestors
        """)
        result = await self.session.execute(
            stmt,
            {"prop_id": proposition_id, "corpus_id": self.corpus_id, "max_depth": max_depth},
        )
        return [DescendantInfo(id=row[0], depth=row[1]) for row in result]


class SupersessionEdgeRepo(CorpusScopedRepo[SupersessionEdge]):
    model = SupersessionEdge

    async def add_supersession(
        self,
        old_id: uuid.UUID,
        new_id: uuid.UUID,
        supersession_type: str,
        effective_at: object,
    ) -> SupersessionEdge:
        edge = SupersessionEdge(
            corpus_id=self.corpus_id,
            old_proposition_id=old_id,
            new_proposition_id=new_id,
            supersession_type=supersession_type,
            effective_at=effective_at,
        )
        return await self.add(edge)

    async def is_superseded(self, proposition_id: uuid.UUID) -> bool:
        from sqlalchemy import func

        stmt = select(
            exists().where(
                SupersessionEdge.old_proposition_id == proposition_id,
                SupersessionEdge.corpus_id == self.corpus_id,
                SupersessionEdge.effective_at <= func.now(),
            )
        )
        result = await self.session.execute(stmt)
        return bool(result.scalar())

    async def is_retracted(self, proposition_id: uuid.UUID) -> bool:
        from sqlalchemy import func

        stmt = select(
            exists().where(
                SupersessionEdge.old_proposition_id == proposition_id,
                SupersessionEdge.corpus_id == self.corpus_id,
                SupersessionEdge.supersession_type == "retraction",
                SupersessionEdge.effective_at <= func.now(),
            )
        )
        result = await self.session.execute(stmt)
        return bool(result.scalar())
