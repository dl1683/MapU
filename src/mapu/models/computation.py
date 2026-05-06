"""Computation models: ComputationSpec, ComputationRun."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class ComputationSpec(Base):
    __tablename__ = "computation_spec"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    evaluator_type: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_proposition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column()
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")
    effective_range: Mapped[object | None] = mapped_column(TSTZRANGE)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))


class ComputationRun(Base):
    __tablename__ = "computation_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    spec_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    spec_version: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of: Mapped[datetime] = mapped_column(nullable=False)
    input_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(Text, nullable=False)
    errors: Mapped[dict | None] = mapped_column(JSONB)
    result_proposition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    computed_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
