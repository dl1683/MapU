"""Pydantic request/response DTOs for the REST API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CorpusCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str = ""


class CorpusResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None


class QueryRequestDTO(BaseModel):
    question: str = Field(min_length=1)
    max_results: int = Field(default=20, ge=1, le=500)
    situation_id: uuid.UUID | None = None
    as_of: datetime | None = None


class HitResponse(BaseModel):
    proposition_id: uuid.UUID
    normalized_text: str
    predicate: str
    subject_name: str
    object_name: str | None = None
    confidence: float
    authority_score: float | None = None
    truth_status: str | None = None
    source_span_text: str | None = None
    expression_id: uuid.UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class ChunkHitResponse(BaseModel):
    chunk_id: uuid.UUID
    text: str
    score: float


class QueryResponse(BaseModel):
    intent: str
    tier_used: str
    synthesis: str | None = None
    hits: list[HitResponse]
    gaps: list[str]
    chunk_hits: list[ChunkHitResponse] = []


class IngestRequestDTO(BaseModel):
    content: str = Field(min_length=1, max_length=10_000_000)
    mime_type: str = "text/plain"
    source_uri: str = ""
    document_type: str | None = None
    publication_context: str | None = None
    source_identity: str | None = None
    independence_group: str | None = None

    @field_validator("content")
    @classmethod
    def check_byte_length(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 10_000_000:
            msg = "Content exceeds 10MB when encoded to UTF-8"
            raise ValueError(msg)
        return v


class IngestResponse(BaseModel):
    document_id: uuid.UUID
    expression_id: uuid.UUID
    spans: int
    chunks: int
    embeddings: int
    propositions: int = 0


class HandleResponse(BaseModel):
    id: uuid.UUID
    canonical_name: str
    kind: str
    aliases: list[str]


class RepairPreviewResponse(BaseModel):
    root_proposition_id: uuid.UUID
    affected_count: int
    recompute_only_count: int
    risk_level: str
    max_depth: int
    depth_limited: bool


class RepairProposeRequest(BaseModel):
    proposition_id: uuid.UUID
    operation: Literal["retract"] = "retract"
    reason: str = ""
    actor: str = "user"


class RepairProposeResponse(BaseModel):
    changeset_id: uuid.UUID
    risk_level: str
    affected_count: int


class RepairApproveResponse(BaseModel):
    changeset_id: uuid.UUID
    status: str


class RepairApplyResponse(BaseModel):
    changeset_id: uuid.UUID
    success: bool
    operations_executed: int
    recomputed_propositions: int
    gaps_created: int
    errors: list[str]


class ContributePropositionRequest(BaseModel):
    subject_name: str = Field(min_length=1)
    subject_kind: str = "entity"
    predicate: str = Field(min_length=1)
    object_name: str | None = None
    object_kind: str | None = None
    normalized_text: str = Field(min_length=1)
    frame_type: str = "finding"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    stance: str = Field(
        default="asserts",
        pattern="^(asserts|denies|reports|questions|conditions)$",
    )
    actor: str = "human"


class ContributePropositionResponse(BaseModel):
    proposition_id: uuid.UUID
    attestation_id: uuid.UUID


class ReviewAttestationRequest(BaseModel):
    attestation_id: uuid.UUID
    decision: str = Field(pattern="^(accepted|rejected|quarantined)$")
    actor: str = "human"
    reason: str = ""


class ReviewAttestationResponse(BaseModel):
    attestation_id: uuid.UUID
    new_status: str
    changeset_id: uuid.UUID | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
