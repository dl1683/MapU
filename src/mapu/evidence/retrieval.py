"""Model-tagged chunk embedding retrieval."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.evidence.types import EmbeddingModelRef, EmbeddingVector, RetrievalResult
from mapu.models.evidence import Chunk, ChunkEmbedding


@dataclass(frozen=True)
class RetrievalConfig:
    """Configuration for retrieval queries."""

    top_k: int = 10
    min_score: float = 0.0


class ChunkRetrievalService:
    """Retrieve chunks by vector similarity, scoped by corpus and model."""

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
        config: RetrievalConfig | None = None,
    ) -> list[RetrievalResult]:
        cfg = config or RetrievalConfig()

        dims = self._model_ref.dimensions
        stmt = text(f"""
            SELECT ce.chunk_id, c.text, c.expression_id,
                   1 - (ce.embedding::vector({dims}) <=> :query_vec::vector({dims})) AS score
            FROM chunk_embedding ce
            JOIN chunk c ON c.id = ce.chunk_id AND c.corpus_id = ce.corpus_id
            WHERE ce.corpus_id = :corpus_id
              AND ce.model_name = :model_name
              AND ce.dimensions = {dims}
            ORDER BY ce.embedding::vector({dims}) <=> :query_vec::vector({dims})
            LIMIT :top_k
        """)

        result = await self._session.execute(
            stmt,
            {
                "query_vec": str(query_vector),
                "corpus_id": self._corpus_id,
                "model_name": self._model_ref.tag,
                "top_k": cfg.top_k,
            },
        )

        results: list[RetrievalResult] = []
        for row in result:
            score = float(row[3])
            if score >= cfg.min_score:
                results.append(RetrievalResult(
                    chunk_id=row[0],
                    text=row[1],
                    score=score,
                    expression_id=row[2],
                ))
        return results

    async def get_by_chunk_ids(
        self, chunk_ids: list[uuid.UUID]
    ) -> list[RetrievalResult]:
        if not chunk_ids:
            return []
        stmt = (
            select(Chunk.id, Chunk.text, Chunk.expression_id)
            .where(
                Chunk.id.in_(chunk_ids),
                Chunk.corpus_id == self._corpus_id,
            )
        )
        result = await self._session.execute(stmt)
        return [
            RetrievalResult(
                chunk_id=row[0],
                text=row[1],
                score=1.0,
                expression_id=row[2],
            )
            for row in result
        ]

    async def embeddings_for_model(
        self, chunk_id: uuid.UUID
    ) -> list[ChunkEmbedding]:
        stmt = select(ChunkEmbedding).where(
            ChunkEmbedding.chunk_id == chunk_id,
            ChunkEmbedding.corpus_id == self._corpus_id,
            ChunkEmbedding.model_name == self._model_ref.tag,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
