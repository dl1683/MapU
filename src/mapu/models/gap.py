"""Gap models: Gap, GapTarget."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class Gap(Base):
    __tablename__ = "gap"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="moderate")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    detected_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column()


class GapTarget(Base):
    __tablename__ = "gap_target"

    gap_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(Text, primary_key=True)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
