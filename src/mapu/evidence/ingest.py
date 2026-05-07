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
        parser = self._parsers.get_parser(blob.mime_type)
        parsed = await parser.parse(blob)

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

        for i, node in enumerate(parsed.nodes):
            if (
                node.parent_index is not None
                and (node.parent_index < 0 or node.parent_index >= i)
            ):
                raise ValueError(
                    f"Node {i} has invalid parent_index {node.parent_index}"
                )

        for i, span in enumerate(parsed.spans):
            if (
                span.node_index is not None
                and (span.node_index < 0 or span.node_index >= len(parsed.nodes))
            ):
                raise ValueError(
                    f"Span {i} has invalid node_index {span.node_index}"
                )

        node_models: list[StructureNode] = []
        for node in parsed.nodes:
            parent_id = node_models[node.parent_index].id if node.parent_index is not None else None
            sn = StructureNode(
                id=uuid.uuid4(),
                expression_id=expr.id,
                corpus_id=self._corpus_id,
                parent_id=parent_id,
                node_type=node.node_type,
                ordinal=node.ordinal,
                metadata_=node.metadata,
            )
            self._session.add(sn)
            node_models.append(sn)
            result.node_count += 1
        await self._session.flush()

        span_models: list[TextSpan] = []
        for span in parsed.spans:
            node_id = node_models[span.node_index].id if span.node_index is not None else None
            ts = TextSpan(
                id=uuid.uuid4(),
                expression_id=expr.id,
                corpus_id=self._corpus_id,
                node_id=node_id,
                text=span.text,
                start_char=span.start_char,
                end_char=span.end_char,
            )
            self._session.add(ts)
            span_models.append(ts)
            result.span_ids.append(ts.id)
            result.span_count += 1
        await self._session.flush()

        candidates = self._chunker.chunk(parsed)

        span_count = len(parsed.spans)
        for i, candidate in enumerate(candidates):
            if (
                candidate.start_span_index is not None
                and (candidate.start_span_index < 0 or candidate.start_span_index >= span_count)
            ):
                raise ValueError(
                    f"Chunk {i} has invalid start_span_index {candidate.start_span_index}"
                )
            if (
                candidate.end_span_index is not None
                and (candidate.end_span_index < 0 or candidate.end_span_index >= span_count)
            ):
                raise ValueError(
                    f"Chunk {i} has invalid end_span_index {candidate.end_span_index}"
                )

        chunk_texts: list[str] = []
        chunk_models: list[Chunk] = []

        for candidate in candidates:
            start_span_id = (
                span_models[candidate.start_span_index].id
                if candidate.start_span_index is not None else None
            )
            end_span_id = (
                span_models[candidate.end_span_index].id
                if candidate.end_span_index is not None else None
            )
            c = Chunk(
                id=uuid.uuid4(),
                expression_id=expr.id,
                corpus_id=self._corpus_id,
                text=candidate.text,
                start_span_id=start_span_id,
                end_span_id=end_span_id,
                token_count=candidate.token_count,
            )
            self._session.add(c)
            chunk_texts.append(candidate.text)
            chunk_models.append(c)
            result.chunk_ids.append(c.id)
            result.chunk_count += 1
        await self._session.flush()

        if self._embedder and chunk_texts:
            model_ref: EmbeddingModelRef = self._embedder.model_ref
            batch_size = 64
            for offset in range(0, len(chunk_texts), batch_size):
                batch_texts = chunk_texts[offset:offset + batch_size]
                batch_models = chunk_models[offset:offset + batch_size]
                vectors = await self._embedder.embed_texts(batch_texts)
                for chunk_model, vector in zip(batch_models, vectors, strict=True):
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
