"""Review models: Changeset, ChangesetOperation."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class Changeset(Base):
    __tablename__ = "changeset"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")
    risk_level: Mapped[str] = mapped_column(Text, nullable=False, default="low")
    blast_radius: Mapped[dict | None] = mapped_column(JSONB)
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column()
    review_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column()
    rolled_back_at: Mapped[datetime | None] = mapped_column()


class ChangesetOperation(Base):
    __tablename__ = "changeset_operation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    changeset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    executed_at: Mapped[datetime | None] = mapped_column()
