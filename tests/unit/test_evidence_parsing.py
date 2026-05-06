"""Unit tests for document parsing."""

from __future__ import annotations

import pytest

from mapu.evidence.parsers import ParserRegistry
from mapu.evidence.plaintext import PlaintextParser
from mapu.evidence.types import DocumentBlob


class TestPlaintextParser:
    @pytest.fixture
    def parser(self) -> PlaintextParser:
        return PlaintextParser()

    async def test_parse_simple(self, parser: PlaintextParser) -> None:
        blob = DocumentBlob(
            content=b"Hello world.\n\nSecond paragraph.",
            mime_type="text/plain",
            source_uri="test://simple",
        )
        result = await parser.parse(blob)
        assert result.parser_id == "plaintext_v1"
        assert len(result.nodes) == 2
        assert result.nodes[0].text == "Hello world."
        assert result.nodes[1].text == "Second paragraph."
        assert len(result.spans) == 2
        assert result.full_text == "Hello world.\n\nSecond paragraph."

    async def test_parse_single_line(self, parser: PlaintextParser) -> None:
        blob = DocumentBlob(
            content=b"Just one line.",
            mime_type="text/plain",
            source_uri="test://single",
        )
        result = await parser.parse(blob)
        assert len(result.nodes) == 1
        assert result.nodes[0].text == "Just one line."

    async def test_parse_empty(self, parser: PlaintextParser) -> None:
        blob = DocumentBlob(
            content=b"",
            mime_type="text/plain",
            source_uri="test://empty",
        )
        result = await parser.parse(blob)
        assert len(result.nodes) == 0
        assert len(result.spans) == 0

    async def test_parse_preserves_source_uri(self, parser: PlaintextParser) -> None:
        blob = DocumentBlob(
            content=b"Content here.",
            mime_type="text/plain",
            source_uri="test://uri-check",
        )
        result = await parser.parse(blob)
        assert result.metadata["source_uri"] == "test://uri-check"

    async def test_span_offsets(self, parser: PlaintextParser) -> None:
        blob = DocumentBlob(
            content=b"First.\n\nSecond.",
            mime_type="text/plain",
            source_uri="test://offsets",
        )
        result = await parser.parse(blob)
        assert result.spans[0].start_char == 0
        assert result.spans[0].end_char == 6
        assert result.spans[1].start_char == 8
        assert result.spans[1].end_char == 15

    async def test_supported_mime_types(self, parser: PlaintextParser) -> None:
        assert "text/plain" in parser.supported_mime_types

    async def test_utf8_decoding(self, parser: PlaintextParser) -> None:
        blob = DocumentBlob(
            content="Héllo wörld.".encode(),
            mime_type="text/plain",
            source_uri="test://utf8",
        )
        result = await parser.parse(blob)
        assert result.nodes[0].text == "Héllo wörld."

    async def test_multi_newline_paragraphs(self, parser: PlaintextParser) -> None:
        blob = DocumentBlob(
            content=b"Para one.\n\n\n\nPara two.",
            mime_type="text/plain",
            source_uri="test://multi-newline",
        )
        result = await parser.parse(blob)
        assert len(result.nodes) == 2


class TestParserRegistry:
    def test_register_and_retrieve(self) -> None:
        registry = ParserRegistry()
        parser = PlaintextParser()
        registry.register(parser)
        assert registry.get_parser("text/plain") is parser

    def test_unknown_mime_type_raises(self) -> None:
        registry = ParserRegistry()
        with pytest.raises(ValueError, match="No parser registered"):
            registry.get_parser("application/pdf")

    def test_supported_types(self) -> None:
        registry = ParserRegistry()
        registry.register(PlaintextParser())
        assert "text/plain" in registry.supported_types()
