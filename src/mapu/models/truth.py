"""Truth state models: PropositionState, PropositionStateBasis."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import TSTZRANGE, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class PropositionState(Base):
    __tablename__ = "proposition_state"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    situation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    truth_status: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="auto_computed")
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column()
    truth_policy_version: Mapped[str] = mapped_column(Text, nullable=False, default="v1.1")
    effective_range: Mapped[object] = mapped_column(TSTZRANGE, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))
    basis_hash: Mapped[str] = mapped_column(Text, nullable=False)


class PropositionStateBasis(Base):
    __tablename__ = "proposition_state_basis"

    state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    attestation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
