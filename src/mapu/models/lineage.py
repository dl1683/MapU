"""Lineage models: DerivationEdge, SupersessionEdge."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class DerivationEdge(Base):
    __tablename__ = "derivation_edge"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    parent_proposition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    child_proposition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    derivation_type: Mapped[str] = mapped_column(Text, nullable=False)
    derivation_method: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(nullable=False)


class SupersessionEdge(Base):
    __tablename__ = "supersession_edge"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    old_proposition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    new_proposition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supersession_type: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
