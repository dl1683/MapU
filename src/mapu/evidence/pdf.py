"""PDF document parser using pypdf."""

from __future__ import annotations

import io

from pypdf import PdfReader

from mapu.evidence.types import (
    DocumentBlob,
    ParsedDocument,
    ParsedNode,
    ParsedSpan,
)


class PdfParser:
    """Parses PDF documents into structured nodes (pages) and text spans."""

    @property
    def parser_id(self) -> str:
        return "pdf_pypdf_v1"

    @property
    def supported_mime_types(self) -> frozenset[str]:
        return frozenset({"application/pdf"})

    async def parse(self, document: DocumentBlob) -> ParsedDocument:
        reader = PdfReader(io.BytesIO(document.content))

        nodes: list[ParsedNode] = []
        spans: list[ParsedSpan] = []
        full_parts: list[str] = []
        char_offset = 0

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if not text.strip():
                nodes.append(ParsedNode(
                    node_type="page",
                    ordinal=page_num,
                    text="",
                    metadata={"page_number": page_num + 1, "warning": "no_extractable_text"},
                ))
                continue

            nodes.append(ParsedNode(
                node_type="page",
                ordinal=page_num,
                text=text.strip(),
                metadata={"page_number": page_num + 1},
            ))

            spans.append(ParsedSpan(
                text=text.strip(),
                start_char=char_offset,
                end_char=char_offset + len(text),
                node_index=len(nodes) - 1,
            ))

            full_parts.append(text)
            char_offset += len(text)

            if page_num < len(reader.pages) - 1:
                full_parts.append("\n")
                char_offset += 1

        full_text = "\n".join(
            p.extract_text() or "" for p in reader.pages
        ) if reader.pages else ""

        return ParsedDocument(
            parser_id=self.parser_id,
            nodes=tuple(nodes),
            spans=tuple(spans),
            full_text=full_text,
            metadata={
                "source_uri": document.source_uri,
                "page_count": len(reader.pages),
            },
        )
