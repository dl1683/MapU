"""Document ingestion service: raw document → expression → spans → chunks → embeddings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.evidence.chunking import Chunker
from mapu.evidence.parsers import ParserRegistry
from mapu.evidence.types import DocumentBlob, EmbeddingModelRef
from mapu.models.evidence import (
    Chunk,
    ChunkEmbedding,
    DocumentExpression,
    DocumentWork,
    StructureNode,
    TextSpan,
)
from mapu.providers.embeddings import EmbeddingProvider


@dataclass
class IngestResult:
    """Summary of what was persisted during ingestion."""

    document_id: uuid.UUID
    expression_id: uuid.UUID
    node_count: int = 0
    span_count: int = 0
    chunk_count: int = 0
    embedding_count: int = 0
    span_ids: list[uuid.UUID] = field(default_factory=list)
    chunk_ids: list[uuid.UUID] = field(default_factory=list)


class IngestionService:
    """Orchestrates the full ingestion pipeline."""

    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        parser_registry: ParserRegistry,
        chunker: Chunker,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id
        self._parsers = parser_registry
        self._chunker = chunker
        self._embedder = embedding_provider

    async def ingest(self, blob: DocumentBlob) -> IngestResult:
        now = datetime.now(UTC)

        doc = DocumentWork(
            id=uuid.uuid4(),
            corpus_id=self._corpus_id,
            raw_content=blob.content,
            mime_type=blob.mime_type,
            source_uri=blob.source_uri,
            metadata_=blob.metadata,
            ingested_at=now,
        )
        self._session.add(doc)
        await self._session.flush()

        parser = self._parsers.get_parser(blob.mime_type)
        parsed = await parser.parse(blob)

        expr = DocumentExpression(
            id=uuid.uuid4(),
            document_id=doc.id,
            corpus_id=self._corpus_id,
            parser_version=parsed.parser_id,
            created_at=now,
        )
        self._session.add(expr)
        await self._session.flush()

        result = IngestResult(document_id=doc.id, expression_id=expr.id)

        for node in parsed.nodes:
            sn = StructureNode(
                id=uuid.uuid4(),
                expression_id=expr.id,
                corpus_id=self._corpus_id,
                node_type=node.node_type,
                ordinal=node.ordinal,
                metadata_=node.metadata,
            )
            self._session.add(sn)
            result.node_count += 1
        await self._session.flush()

        for span in parsed.spans:
            ts = TextSpan(
                id=uuid.uuid4(),
                expression_id=expr.id,
                corpus_id=self._corpus_id,
                text=span.text,
                start_char=span.start_char,
                end_char=span.end_char,
            )
            self._session.add(ts)
            result.span_ids.append(ts.id)
            result.span_count += 1
        await self._session.flush()

        candidates = self._chunker.chunk(parsed)
        chunk_texts: list[str] = []
        chunk_models: list[Chunk] = []

        for candidate in candidates:
            c = Chunk(
                id=uuid.uuid4(),
                expression_id=expr.id,
                corpus_id=self._corpus_id,
                text=candidate.text,
                token_count=candidate.token_count,
            )
            self._session.add(c)
            chunk_texts.append(candidate.text)
            chunk_models.append(c)
            result.chunk_ids.append(c.id)
            result.chunk_count += 1
        await self._session.flush()

        if self._embedder and chunk_texts:
            vectors = await self._embedder.embed_texts(chunk_texts)
            model_ref: EmbeddingModelRef = self._embedder.model_ref
            for chunk_model, vector in zip(chunk_models, vectors, strict=True):
                ce = ChunkEmbedding(
                    id=uuid.uuid4(),
                    chunk_id=chunk_model.id,
                    corpus_id=self._corpus_id,
                    model_name=model_ref.tag,
                    dimensions=model_ref.dimensions,
                    embedding=list(vector),
                )
                self._session.add(ce)
                result.embedding_count += 1
            await self._session.flush()

        return result
