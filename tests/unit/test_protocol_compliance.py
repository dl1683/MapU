"""Tests verifying protocol compliance across implementations."""

from __future__ import annotations

from mapu.evidence.chunking import Chunker, SimpleCharTokenCounter, SpanAwareChunker, TokenCounter
from mapu.evidence.docx import DocxParser
from mapu.evidence.parsers import DocumentParser
from mapu.evidence.pdf import PdfParser
from mapu.evidence.plaintext import PlaintextParser
from mapu.extraction.ml import (
    GLiNERExtractor,
    REBELExtractor,
    SetFitExtractor,
    SRLExtractor,
)
from mapu.extraction.rules import (
    AmendmentExtractor,
    CrossReferenceExtractor,
    DateExtractor,
    DefinedTermExtractor,
)
from mapu.extraction.types import Extractor
from mapu.providers.embedding_local import HashEmbeddingProvider
from mapu.providers.embeddings import EmbeddingProvider


class TestDocumentParserProtocol:
    def test_plaintext_is_document_parser(self) -> None:
        assert isinstance(PlaintextParser(), DocumentParser)

    def test_pdf_is_document_parser(self) -> None:
        assert isinstance(PdfParser(), DocumentParser)

    def test_docx_is_document_parser(self) -> None:
        assert isinstance(DocxParser(), DocumentParser)


class TestChunkerProtocol:
    def test_span_aware_is_chunker(self) -> None:
        assert isinstance(SpanAwareChunker(), Chunker)


class TestTokenCounterProtocol:
    def test_simple_char_is_token_counter(self) -> None:
        assert isinstance(SimpleCharTokenCounter(), TokenCounter)


class TestEmbeddingProviderProtocol:
    def test_hash_is_embedding_provider(self) -> None:
        assert isinstance(HashEmbeddingProvider(), EmbeddingProvider)


class TestExtractorProtocol:
    def test_date_is_extractor(self) -> None:
        assert isinstance(DateExtractor(), Extractor)

    def test_cross_reference_is_extractor(self) -> None:
        assert isinstance(CrossReferenceExtractor(), Extractor)

    def test_defined_term_is_extractor(self) -> None:
        assert isinstance(DefinedTermExtractor(), Extractor)

    def test_amendment_is_extractor(self) -> None:
        assert isinstance(AmendmentExtractor(), Extractor)

    def test_gliner_is_extractor(self) -> None:
        assert isinstance(GLiNERExtractor(), Extractor)

    def test_rebel_is_extractor(self) -> None:
        assert isinstance(REBELExtractor(), Extractor)

    def test_setfit_is_extractor(self) -> None:
        assert isinstance(SetFitExtractor(), Extractor)

    def test_srl_is_extractor(self) -> None:
        assert isinstance(SRLExtractor(), Extractor)
