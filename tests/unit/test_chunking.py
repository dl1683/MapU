"""Unit tests for chunking."""

from __future__ import annotations

import pytest

from mapu.evidence.chunking import SimpleCharTokenCounter, SpanAwareChunker
from mapu.evidence.types import ParsedDocument, ParsedNode, ParsedSpan


class TestSimpleCharTokenCounter:
    def test_empty_string(self) -> None:
        counter = SimpleCharTokenCounter()
        assert counter.count("") == 1

    def test_short_string(self) -> None:
        counter = SimpleCharTokenCounter()
        assert counter.count("hi") == 1

    def test_normal_string(self) -> None:
        counter = SimpleCharTokenCounter()
        assert counter.count("hello world this is a test") == 6

    def test_long_string(self) -> None:
        counter = SimpleCharTokenCounter()
        text = "a" * 400
        assert counter.count(text) == 100


class TestSpanAwareChunker:
    @pytest.fixture
    def short_doc(self) -> ParsedDocument:
        text = "Short document."
        return ParsedDocument(
            parser_id="test",
            nodes=(ParsedNode(node_type="paragraph", ordinal=0, text=text),),
            spans=(ParsedSpan(text=text, start_char=0, end_char=len(text)),),
            full_text=text,
        )

    @pytest.fixture
    def long_doc(self) -> ParsedDocument:
        para = "Word " * 200
        text = f"{para}\n\n{para}"
        return ParsedDocument(
            parser_id="test",
            nodes=(
                ParsedNode(node_type="paragraph", ordinal=0, text=para.strip()),
                ParsedNode(node_type="paragraph", ordinal=1, text=para.strip()),
            ),
            spans=(
                ParsedSpan(text=para.strip(), start_char=0, end_char=len(para)),
                ParsedSpan(
                    text=para.strip(),
                    start_char=len(para) + 2,
                    end_char=len(para) * 2 + 2,
                ),
            ),
            full_text=text,
        )

    def test_short_doc_single_chunk(self, short_doc: ParsedDocument) -> None:
        chunker = SpanAwareChunker(max_tokens=512)
        chunks = chunker.chunk(short_doc)
        assert len(chunks) == 1
        assert chunks[0].text == "Short document."

    def test_chunker_id_format(self) -> None:
        chunker = SpanAwareChunker(max_tokens=256, overlap_tokens=32)
        assert chunker.chunker_id == "span_aware:256:32"

    def test_empty_document(self) -> None:
        doc = ParsedDocument(
            parser_id="test",
            nodes=(),
            spans=(),
            full_text="",
        )
        chunker = SpanAwareChunker()
        assert len(chunker.chunk(doc)) == 0

    def test_long_doc_multiple_chunks(self, long_doc: ParsedDocument) -> None:
        chunker = SpanAwareChunker(max_tokens=100, overlap_tokens=10)
        chunks = chunker.chunk(long_doc)
        assert len(chunks) > 1
        for c in chunks:
            assert c.token_count <= 100

    def test_chunks_cover_full_text(self, long_doc: ParsedDocument) -> None:
        chunker = SpanAwareChunker(max_tokens=100, overlap_tokens=10)
        chunks = chunker.chunk(long_doc)
        covered = set()
        for c in chunks:
            for i in range(c.start_char, c.end_char):
                covered.add(i)
        for i in range(len(long_doc.full_text)):
            assert i in covered, f"Character {i} not covered by any chunk"

    def test_chunk_token_count_positive(self, short_doc: ParsedDocument) -> None:
        chunker = SpanAwareChunker()
        chunks = chunker.chunk(short_doc)
        for c in chunks:
            assert c.token_count > 0
