"""DocumentParser protocol and MIME-based registry."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mapu.evidence.types import DocumentBlob, ParsedDocument


@runtime_checkable
class DocumentParser(Protocol):
    """Protocol for document parsers. Each parser handles specific MIME types."""

    @property
    def parser_id(self) -> str: ...

    @property
    def supported_mime_types(self) -> frozenset[str]: ...

    async def parse(self, document: DocumentBlob) -> ParsedDocument: ...


class ParserRegistry:
    """MIME-type-based parser dispatch."""

    def __init__(self) -> None:
        self._parsers: dict[str, DocumentParser] = {}

    def register(self, parser: DocumentParser) -> None:
        for mime_type in parser.supported_mime_types:
            self._parsers[mime_type] = parser

    def get_parser(self, mime_type: str) -> DocumentParser:
        parser = self._parsers.get(mime_type)
        if parser is None:
            raise ValueError(f"No parser registered for MIME type: {mime_type}")
        return parser

    def supported_types(self) -> frozenset[str]:
        return frozenset(self._parsers.keys())
