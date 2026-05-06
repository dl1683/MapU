"""Attestation models: Attestation, AttestationSituation."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class Attestation(Base):
    __tablename__ = "attestation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    span_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    proposition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    source_policy_eval_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    stance: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(nullable=False)
    attestation_strength: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")
    system_created: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    system_invalidated: Mapped[datetime | None] = mapped_column()


class AttestationSituation(Base):
    __tablename__ = "attestation_situation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attestation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    situation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    assignment_confidence: Mapped[float] = mapped_column(nullable=False)
    assignment_basis: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    invalidated_at: Mapped[datetime | None] = mapped_column()
