"""Authority model: SourcePolicyEval."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mapu.db.base import Base


class SourcePolicyEval(Base):
    __tablename__ = "source_policy_eval"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    corpus_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("corpus.id"), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(Text, nullable=False, default="v1")
    evaluator: Mapped[str] = mapped_column(Text, nullable=False, default="rule_based")
    document_type: Mapped[str | None] = mapped_column(Text)
    formality: Mapped[float | None] = mapped_column()
    attestation_type: Mapped[str | None] = mapped_column(Text)
    publication_context: Mapped[str | None] = mapped_column(Text)
    cross_reference_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provenance_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_identity: Mapped[str | None] = mapped_column(Text)
    independence_group: Mapped[str | None] = mapped_column(Text)
    authority_score: Mapped[float] = mapped_column(nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(nullable=False)
