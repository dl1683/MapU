"""Pure dataclasses for document parsing and chunking pipeline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DocumentBlob:
    """Raw document content before parsing."""

    content: bytes
    mime_type: str
    source_uri: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedNode:
    """A structural element within a parsed document (section, paragraph, table, etc.)."""

    node_type: str
    ordinal: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    children: tuple[ParsedNode, ...] = ()
    parent_index: int | None = None


@dataclass(frozen=True)
class ParsedSpan:
    """A contiguous text span extracted from a document."""

    text: str
    start_char: int
    end_char: int
    node_index: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    """Complete parse result: structured nodes and text spans."""

    parser_id: str
    nodes: tuple[ParsedNode, ...]
    spans: tuple[ParsedSpan, ...]
    full_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChunkCandidate:
    """A candidate chunk before embedding, with span boundary references."""

    text: str
    start_char: int
    end_char: int
    token_count: int
    start_span_index: int | None = None
    end_span_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


EmbeddingVector = list[float]


@dataclass(frozen=True)
class EmbeddingModelRef:
    """Identifies an embedding model. tag is the exact string persisted to DB."""

    provider: str
    model_name: str
    dimensions: int

    @property
    def tag(self) -> str:
        return f"{self.provider}:{self.model_name}:{self.dimensions}"


@dataclass(frozen=True)
class EmbeddedChunk:
    """A chunk with its computed embedding vector."""

    chunk_id: uuid.UUID
    text: str
    embedding: EmbeddingVector
    model_ref: EmbeddingModelRef


@dataclass(frozen=True)
class RetrievalResult:
    """A chunk returned from a similarity search."""

    chunk_id: uuid.UUID
    text: str
    score: float
    expression_id: uuid.UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
