"""Unit tests for PDF parser."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter

from mapu.evidence.pdf import PdfParser
from mapu.evidence.types import DocumentBlob


def _make_pdf(pages: list[str]) -> bytes:
    """Create a minimal PDF with given page texts."""
    writer = PdfWriter()
    for text in pages:
        writer.add_blank_page(width=612, height=792)
        page = writer.pages[-1]
        page.merge_page(
            PdfWriter()._create_text_page(text)  # noqa: SLF001
        )
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _make_simple_pdf(text: str) -> bytes:
    """Create a trivial one-page PDF with pypdf."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestPdfParser:
    @pytest.fixture
    def parser(self) -> PdfParser:
        return PdfParser()

    async def test_parser_id(self, parser: PdfParser) -> None:
        assert parser.parser_id == "pdf_pypdf_v1"

    async def test_supported_types(self, parser: PdfParser) -> None:
        assert "application/pdf" in parser.supported_mime_types

    async def test_parse_blank_pdf(self, parser: PdfParser) -> None:
        pdf_bytes = _make_simple_pdf("")
        blob = DocumentBlob(
            content=pdf_bytes,
            mime_type="application/pdf",
            source_uri="test://blank.pdf",
        )
        result = await parser.parse(blob)
        assert result.parser_id == "pdf_pypdf_v1"
        assert result.metadata["page_count"] == 1
