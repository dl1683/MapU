"""Unit tests for ingestion service logic (pure, no DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mapu.evidence.chunking import SpanAwareChunker
from mapu.evidence.ingest import IngestionService
from mapu.evidence.parsers import ParserRegistry
from mapu.evidence.plaintext import PlaintextParser
from mapu.evidence.types import DocumentBlob, ParsedDocument, ParsedNode, ParsedSpan
from mapu.extraction import get_default_extractors
from mapu.extraction.service import ExtractionResult
from mapu.providers.embedding_local import HashEmbeddingProvider


def _make_mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    nested = AsyncMock()
    nested.__aenter__ = AsyncMock(return_value=nested)
    nested.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=nested)
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

    @patch("mapu.evidence.ingest.ExtractionService")
    async def test_ingest_with_extractors_runs_extraction(
        self,
        mock_extraction_cls: MagicMock,
        registry: ParserRegistry,
        chunker: SpanAwareChunker,
        corpus_id: uuid.UUID,
    ) -> None:
        mock_svc = AsyncMock()
        mock_svc.extract_expression.return_value = ExtractionResult(
            expression_id=uuid.uuid4(), materialized=[MagicMock(), MagicMock()],
        )
        mock_extraction_cls.return_value = mock_svc

        session = _make_mock_session()
        extractors = get_default_extractors()
        service = IngestionService(
            session, corpus_id, registry, chunker, extractors=extractors,
        )
        blob = DocumentBlob(
            content=b"Hello world. This is a test document.",
            mime_type="text/plain",
            source_uri="test://extraction",
        )
        result = await service.ingest(blob)
        assert result.propositions_extracted == 2
        mock_extraction_cls.assert_called_once()
        mock_svc.extract_expression.assert_awaited_once()

    async def test_ingest_without_extractors_skips_extraction(
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
            source_uri="test://no-extract",
        )
        result = await service.ingest(blob)
        assert result.propositions_extracted == 0


class TestIngestIndexValidation:
    @pytest.fixture
    def chunker(self) -> SpanAwareChunker:
        return SpanAwareChunker(max_tokens=100, overlap_tokens=10)

    @pytest.fixture
    def corpus_id(self) -> uuid.UUID:
        return uuid.uuid4()

    def _make_bad_parser(self, parsed: ParsedDocument) -> ParserRegistry:
        class BadParser:
            parser_id = "bad"
            supported_mime_types = frozenset({"text/bad"})

            async def parse(self, _blob: DocumentBlob) -> ParsedDocument:
                return parsed

        registry = ParserRegistry()
        registry.register(BadParser())
        return registry

    async def test_negative_parent_index_rejected(
        self, chunker: SpanAwareChunker, corpus_id: uuid.UUID
    ) -> None:
        parsed = ParsedDocument(
            parser_id="bad",
            nodes=(ParsedNode(node_type="section", ordinal=0, text="x", parent_index=-1),),
            spans=(),
            full_text="x",
        )
        registry = self._make_bad_parser(parsed)
        session = _make_mock_session()
        service = IngestionService(session, corpus_id, registry, chunker)
        blob = DocumentBlob(content=b"x", mime_type="text/bad", source_uri="test://bad")
        with pytest.raises(ValueError, match="invalid parent_index"):
            await service.ingest(blob)

    async def test_out_of_range_node_index_rejected(
        self, chunker: SpanAwareChunker, corpus_id: uuid.UUID
    ) -> None:
        parsed = ParsedDocument(
            parser_id="bad",
            nodes=(ParsedNode(node_type="section", ordinal=0, text="x"),),
            spans=(ParsedSpan(text="x", start_char=0, end_char=1, node_index=5),),
            full_text="x",
        )
        registry = self._make_bad_parser(parsed)
        session = _make_mock_session()
        service = IngestionService(session, corpus_id, registry, chunker)
        blob = DocumentBlob(content=b"x", mime_type="text/bad", source_uri="test://bad")
        with pytest.raises(ValueError, match="invalid node_index"):
            await service.ingest(blob)
