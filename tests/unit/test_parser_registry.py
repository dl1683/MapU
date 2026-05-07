"""Unit tests for parser registry with all parser types."""

from __future__ import annotations

from mapu.evidence.docx import DocxParser
from mapu.evidence.parsers import ParserRegistry
from mapu.evidence.pdf import PdfParser
from mapu.evidence.plaintext import PlaintextParser


class TestFullParserRegistry:
    def test_all_parsers_registered(self) -> None:
        registry = ParserRegistry()
        registry.register(PlaintextParser())
        registry.register(PdfParser())
        registry.register(DocxParser())

        supported = registry.supported_types()
        assert "text/plain" in supported
        assert "application/pdf" in supported
        assert (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in supported
        )

    def test_parser_dispatch(self) -> None:
        registry = ParserRegistry()
        registry.register(PlaintextParser())
        registry.register(PdfParser())
        registry.register(DocxParser())

        assert isinstance(registry.get_parser("text/plain"), PlaintextParser)
        assert isinstance(registry.get_parser("application/pdf"), PdfParser)

    def test_parser_protocol_compliance(self) -> None:
        from mapu.evidence.parsers import DocumentParser

        assert isinstance(PlaintextParser(), DocumentParser)
        assert isinstance(PdfParser(), DocumentParser)
        assert isinstance(DocxParser(), DocumentParser)

    def test_create_default_registers_all_parsers(self) -> None:
        registry = ParserRegistry.create_default()
        supported = registry.supported_types()
        assert "text/plain" in supported
        assert "application/pdf" in supported
        assert (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            in supported
        )
        assert isinstance(registry.get_parser("text/plain"), PlaintextParser)
        assert isinstance(registry.get_parser("application/pdf"), PdfParser)
        assert isinstance(registry.get_parser(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ), DocxParser)
