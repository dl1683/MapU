"""Identity decision management with pair canonicalization."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.entity import IdentityDecisionModel

_VALID_DECISIONS: frozenset[str] = frozenset({
    "same_entity", "different_entity", "uncertain",
})


def canonicalize_pair(
    handle_a_id: uuid.UUID, handle_b_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """Ensure consistent ordering of handle pairs to prevent reversed duplicates."""
    if str(handle_a_id) <= str(handle_b_id):
        return handle_a_id, handle_b_id
    return handle_b_id, handle_a_id


class IdentityDecisionService:
    """Manages identity decisions between handle pairs."""

    def __init__(self, session: AsyncSession, corpus_id: uuid.UUID) -> None:
        self._session = session
        self._corpus_id = corpus_id

    async def decide(
        self,
        handle_a_id: uuid.UUID,
        handle_b_id: uuid.UUID,
        decision: str,
        confidence: float,
        decided_by: str,
        evidence: dict[str, Any] | None = None,
    ) -> IdentityDecisionModel:
        if handle_a_id == handle_b_id:
            raise ValueError("Cannot create identity decision between a handle and itself")
        if decision not in _VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision {decision!r}; must be one of {sorted(_VALID_DECISIONS)}"
            )
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {confidence}")

        a_id, b_id = canonicalize_pair(handle_a_id, handle_b_id)

        await self._invalidate_active(a_id, b_id)

        model = IdentityDecisionModel(
            id=uuid.uuid4(),
            corpus_id=self._corpus_id,
            handle_a_id=a_id,
            handle_b_id=b_id,
            decision=decision,
            confidence=confidence,
            evidence=evidence or {},
            decided_by=decided_by,
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def active_decision_for_pair(
        self,
        handle_a_id: uuid.UUID,
        handle_b_id: uuid.UUID,
    ) -> IdentityDecisionModel | None:
        a_id, b_id = canonicalize_pair(handle_a_id, handle_b_id)
        stmt = select(IdentityDecisionModel).where(
            IdentityDecisionModel.corpus_id == self._corpus_id,
            IdentityDecisionModel.handle_a_id == a_id,
            IdentityDecisionModel.handle_b_id == b_id,
            IdentityDecisionModel.invalidated_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _invalidate_active(
        self, handle_a_id: uuid.UUID, handle_b_id: uuid.UUID
    ) -> None:
        stmt = (
            update(IdentityDecisionModel)
            .where(
                IdentityDecisionModel.corpus_id == self._corpus_id,
                IdentityDecisionModel.handle_a_id == handle_a_id,
                IdentityDecisionModel.handle_b_id == handle_b_id,
                IdentityDecisionModel.invalidated_at.is_(None),
            )
            .values(invalidated_at=datetime.now(UTC))
        )
        await self._session.execute(stmt)
