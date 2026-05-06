"""Embedding-based handle search, model-tagged."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.evidence.types import EmbeddingModelRef, EmbeddingVector


@dataclass(frozen=True)
class HandleSearchResult:
    """Result from entity similarity search."""

    handle_id: uuid.UUID
    canonical_name: str
    kind: str
    score: float


class HandleSearchService:
    """Vector-based handle search, scoped by corpus, model, and active status."""

    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        model_ref: EmbeddingModelRef,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id
        self._model_ref = model_ref

    async def search(
        self,
        query_vector: EmbeddingVector,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[HandleSearchResult]:
        stmt = text("""
            SELECT id, canonical_name, kind,
                   1 - (embedding <=> :query_vec::vector) AS score
            FROM handle
            WHERE corpus_id = :corpus_id
              AND embedding_model = :model_name
              AND status = 'active'
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :query_vec::vector
            LIMIT :top_k
        """)

        result = await self._session.execute(
            stmt,
            {
                "query_vec": str(query_vector),
                "corpus_id": self._corpus_id,
                "model_name": self._model_ref.tag,
                "top_k": top_k,
            },
        )

        results: list[HandleSearchResult] = []
        for row in result:
            score = float(row[3])
            if score >= min_score:
                results.append(HandleSearchResult(
                    handle_id=row[0],
                    canonical_name=row[1],
                    kind=row[2],
                    score=score,
                ))
        return results

    async def find_similar(
        self,
        handle_id: uuid.UUID,
        top_k: int = 5,
        min_score: float = 0.5,
    ) -> list[HandleSearchResult]:
        get_embedding_stmt = text("""
            SELECT embedding FROM handle
            WHERE id = :handle_id AND corpus_id = :corpus_id
              AND embedding_model = :model_name
              AND embedding IS NOT NULL
        """)
        result = await self._session.execute(
            get_embedding_stmt,
            {
                "handle_id": handle_id,
                "corpus_id": self._corpus_id,
                "model_name": self._model_ref.tag,
            },
        )
        row = result.first()
        if row is None:
            return []

        return await self.search(
            query_vector=list(row[0]),
            top_k=top_k + 1,
            min_score=min_score,
        )
