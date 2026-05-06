"""Evidence repository for document work, expressions, spans, chunks."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from mapu.models.evidence import (
    Chunk,
    ChunkEmbedding,
    DocumentExpression,
    DocumentWork,
    StructureNode,
    TextSpan,
)
from mapu.repos.base import CorpusScopedRepo


class DocumentWorkRepo(CorpusScopedRepo[DocumentWork]):
    model = DocumentWork


class DocumentExpressionRepo(CorpusScopedRepo[DocumentExpression]):
    model = DocumentExpression

    async def get_for_document(self, document_id: uuid.UUID) -> list[DocumentExpression]:
        stmt = select(DocumentExpression).where(
            DocumentExpression.document_id == document_id,
            DocumentExpression.corpus_id == self.corpus_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class StructureNodeRepo(CorpusScopedRepo[StructureNode]):
    model = StructureNode


class TextSpanRepo(CorpusScopedRepo[TextSpan]):
    model = TextSpan


class ChunkRepo(CorpusScopedRepo[Chunk]):
    model = Chunk


class ChunkEmbeddingRepo(CorpusScopedRepo[ChunkEmbedding]):
    model = ChunkEmbedding

    async def get_for_chunk(self, chunk_id: uuid.UUID) -> list[ChunkEmbedding]:
        stmt = select(ChunkEmbedding).where(
            ChunkEmbedding.chunk_id == chunk_id,
            ChunkEmbedding.corpus_id == self.corpus_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
