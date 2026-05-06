"""Authority repository for SourcePolicyEval."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from mapu.models.authority import SourcePolicyEval
from mapu.repos.base import CorpusScopedRepo


class SourcePolicyEvalRepo(CorpusScopedRepo[SourcePolicyEval]):
    model = SourcePolicyEval

    async def get_for_document(
        self, document_id: uuid.UUID
    ) -> list[SourcePolicyEval]:
        stmt = select(SourcePolicyEval).where(
            SourcePolicyEval.document_id == document_id,
            SourcePolicyEval.corpus_id == self.corpus_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_document(
        self, document_id: uuid.UUID
    ) -> SourcePolicyEval | None:
        stmt = (
            select(SourcePolicyEval)
            .where(
                SourcePolicyEval.document_id == document_id,
                SourcePolicyEval.corpus_id == self.corpus_id,
            )
            .order_by(SourcePolicyEval.evaluated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
