"""Unit tests for ingestion service logic (pure, no DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from mapu.evidence.chunking import SpanAwareChunker
from mapu.evidence.ingest import IngestionService
from mapu.evidence.parsers import ParserRegistry
from mapu.evidence.plaintext import PlaintextParser
from mapu.evidence.types import DocumentBlob
from mapu.providers.embedding_local import HashEmbeddingProvider


def _make_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestIngestionService:
    @pytest.fixture
    def registry(self) -> ParserRegistry:
        r = ParserRegistry()
        r.register(PlaintextParser())
        return r

    @pytest.fixture
    def chunker(self) -> SpanAwareChunker:
        return SpanAwareChunker(max_tokens=100, overlap_tokens=10)

    @pytest.fixture
    def embedder(self) -> HashEmbeddingProvider:
        return HashEmbeddingProvider(dimensions=32)

    @pytest.fixture
    def corpus_id(self) -> uuid.UUID:
        return uuid.uuid4()

    async def test_ingest_plaintext(
        self,
        registry: ParserRegistry,
        chunker: SpanAwareChunker,
        corpus_id: uuid.UUID,
    ) -> None:
        session = _make_mock_session()
        service = IngestionService(session, corpus_id, registry, chunker)
        blob = DocumentBlob(
            content=b"Hello world. This is a test document.",
            mime_type="text/plain",
            source_uri="test://unit",
        )
        result = await service.ingest(blob)
        assert result.document_id is not None
        assert result.expression_id is not None
        assert result.span_count > 0
        assert result.chunk_count > 0
        assert result.embedding_count == 0

    async def test_ingest_with_embeddings(
        self,
        registry: ParserRegistry,
        chunker: SpanAwareChunker,
        embedder: HashEmbeddingProvider,
        corpus_id: uuid.UUID,
    ) -> None:
        session = _make_mock_session()
        service = IngestionService(
            session, corpus_id, registry, chunker, embedding_provider=embedder
        )
        blob = DocumentBlob(
            content=b"Hello world. This is a test document.",
            mime_type="text/plain",
            source_uri="test://unit-embed",
        )
        result = await service.ingest(blob)
        assert result.embedding_count == result.chunk_count
        assert result.embedding_count > 0

    async def test_ingest_unsupported_mime_type(
        self,
        registry: ParserRegistry,
        chunker: SpanAwareChunker,
        corpus_id: uuid.UUID,
    ) -> None:
        session = _make_mock_session()
        service = IngestionService(session, corpus_id, registry, chunker)
        blob = DocumentBlob(
            content=b"binary data",
            mime_type="application/octet-stream",
            source_uri="test://binary",
        )
        with pytest.raises(ValueError, match="No parser registered"):
            await service.ingest(blob)

    async def test_ingest_empty_document(
        self,
        registry: ParserRegistry,
        chunker: SpanAwareChunker,
        corpus_id: uuid.UUID,
    ) -> None:
        session = _make_mock_session()
        service = IngestionService(session, corpus_id, registry, chunker)
        blob = DocumentBlob(
            content=b"",
            mime_type="text/plain",
            source_uri="test://empty",
        )
        result = await service.ingest(blob)
        assert result.span_count == 0
        assert result.chunk_count == 0
        assert result.embedding_count == 0
