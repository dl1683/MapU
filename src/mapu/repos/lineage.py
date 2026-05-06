"""Lineage repository for derivation and supersession edges."""

from __future__ import annotations

import uuid

from sqlalchemy import exists, select, text

from mapu.models.lineage import DerivationEdge, SupersessionEdge
from mapu.repos.base import CorpusScopedRepo

MAX_REPAIR_CASCADE_DEPTH = 50


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

    async def descendants_bounded(
        self, proposition_id: uuid.UUID, max_depth: int = MAX_REPAIR_CASCADE_DEPTH
    ) -> set[uuid.UUID]:
        """Compute bounded blast radius using recursive CTE."""
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
            SELECT DISTINCT id FROM descendants
        """)
        result = await self.session.execute(
            stmt,
            {"prop_id": proposition_id, "corpus_id": self.corpus_id, "max_depth": max_depth},
        )
        return {row[0] for row in result}


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
        stmt = select(
            exists().where(
                SupersessionEdge.old_proposition_id == proposition_id,
                SupersessionEdge.corpus_id == self.corpus_id,
            )
        )
        result = await self.session.execute(stmt)
        return bool(result.scalar())

    async def is_retracted(self, proposition_id: uuid.UUID) -> bool:
        stmt = select(
            exists().where(
                SupersessionEdge.old_proposition_id == proposition_id,
                SupersessionEdge.corpus_id == self.corpus_id,
                SupersessionEdge.supersession_type == "retraction",
            )
        )
        result = await self.session.execute(stmt)
        return bool(result.scalar())
