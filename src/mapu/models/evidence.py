"""Evidence layer models: DocumentWork, DocumentExpression, StructureNode, TextSpan, Chunk, ChunkEmbedding."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, LargeBinary, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class DocumentWork(Base):
    __tablename__ = "document_work"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    raw_content: Mapped[bytes | None] = mapped_column(LargeBinary)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(nullable=False)


class DocumentExpression(Base):
    __tablename__ = "document_expression"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    parser_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class StructureNode(Base):
    __tablename__ = "structure_node"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expression_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    node_type: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)


class TextSpan(Base):
    __tablename__ = "text_span"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expression_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)


class Chunk(Base):
    __tablename__ = "chunk"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expression_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_span_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    end_span_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embedding"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector, nullable=False)
