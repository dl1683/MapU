"""Proposition models: Proposition, PropositionParticipant."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class Proposition(Base):
    __tablename__ = "proposition"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    frame_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_handle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    object_handle_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    polarity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    modality: Mapped[str | None] = mapped_column(Text)
    valid_range: Mapped[object | None] = mapped_column(TSTZRANGE)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    qualifiers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    semantic_key: Mapped[str] = mapped_column(Text, nullable=False)
    system_created: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class PropositionParticipant(Base):
    __tablename__ = "proposition_participant"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    handle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
