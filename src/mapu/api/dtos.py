"""Pydantic request/response DTOs for the REST API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

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
    epistemic_status: str = "unknown"
    synthesis: str | None = None
    hits: list[HitResponse]
    gaps: list[str]
    chunk_hits: list[ChunkHitResponse] = []
    metadata: dict[str, Any] = {}


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


class InvestigationBudgetDTO(BaseModel):
    max_llm_calls: int = Field(default=10, ge=1, le=50)
    max_actions: int = Field(default=25, ge=1, le=100)
    max_documents_read: int = Field(default=50, ge=1, le=200)
    target_coverage: float = Field(default=0.9, ge=0.1, le=1.0)


class InvestigationRequestDTO(BaseModel):
    question: str = Field(min_length=1)
    initial_entities: list[str] = []
    initial_predicates: list[str] = []
    situation_id: uuid.UUID | None = None
    budget: InvestigationBudgetDTO = InvestigationBudgetDTO()


class InvestigationEvidenceResponse(BaseModel):
    proposition_id: uuid.UUID
    normalized_text: str
    source_span: str | None = None
    authority_score: float | None = None
    document_id: uuid.UUID | None = None
    is_proposition: bool = True


class DerivedFindingResponse(BaseModel):
    normalized_text: str
    predicate: str
    subject_name: str
    object_name: str | None = None
    confidence: float


class InvestigationResponse(BaseModel):
    answer: str
    evidence: list[InvestigationEvidenceResponse]
    gaps: list[str]
    findings: list[DerivedFindingResponse]
    persisted_proposition_ids: list[uuid.UUID]
    termination_reason: str
    metadata: dict[str, Any] = {}


class ActivityResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    actor: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    details: dict[str, Any] = {}
    created_at: datetime


class GapResponse(BaseModel):
    id: uuid.UUID
    kind: str
    description: str
    severity: str
    status: str
    detected_by: str
    created_at: datetime
    resolved_at: datetime | None = None


class SituationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    kind: str = "user"
    parent_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    assumptions: dict[str, Any] = {}


class SituationResponse(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    parent_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    assumptions: dict[str, Any] = {}
    created_at: datetime
