"""Plaintext document parser."""

from __future__ import annotations

from mapu.evidence.types import (
    DocumentBlob,
    ParsedDocument,
    ParsedNode,
    ParsedSpan,
)


class PlaintextParser:
    """Parses plain text documents into structured nodes and spans."""

    @property
    def parser_id(self) -> str:
        return "plaintext_v1"

    @property
    def supported_mime_types(self) -> frozenset[str]:
        return frozenset({"text/plain"})

    async def parse(self, document: DocumentBlob) -> ParsedDocument:
        text = document.content.decode("utf-8", errors="replace")
        paragraphs = self._split_paragraphs(text)

        nodes: list[ParsedNode] = []
        spans: list[ParsedSpan] = []
        char_offset = 0

        for para in paragraphs:
            if not para.strip():
                char_offset += len(para) + 1
                continue

            nodes.append(ParsedNode(
                node_type="paragraph",
                ordinal=len(nodes),
                text=para.strip(),
            ))

            start = text.index(para, char_offset)
            end = start + len(para)
            spans.append(ParsedSpan(
                text=para.strip(),
                start_char=start,
                end_char=end,
                node_index=len(nodes) - 1,
            ))
            char_offset = end

        return ParsedDocument(
            parser_id=self.parser_id,
            nodes=tuple(nodes),
            spans=tuple(spans),
            full_text=text,
            metadata={"source_uri": document.source_uri},
        )

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        return text.split("\n\n") if "\n\n" in text else text.split("\n")
