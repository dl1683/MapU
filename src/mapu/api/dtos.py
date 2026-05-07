"""Pydantic request/response DTOs for the REST API."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class CorpusCreate(BaseModel):
    name: str
    description: str = ""


class CorpusResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None


class QueryRequestDTO(BaseModel):
    question: str
    max_results: int = 20
    situation_id: uuid.UUID | None = None


class HitResponse(BaseModel):
    proposition_id: uuid.UUID
    normalized_text: str
    predicate: str
    subject_name: str
    object_name: str | None = None
    confidence: float
    authority_score: float | None = None


class QueryResponse(BaseModel):
    intent: str
    tier_used: str
    synthesis: str | None = None
    hits: list[HitResponse]
    gaps: list[str]


class IngestRequestDTO(BaseModel):
    content: str
    mime_type: str = "text/plain"
    source_uri: str = ""


class IngestResponse(BaseModel):
    document_id: uuid.UUID
    expression_id: uuid.UUID
    spans: int
    chunks: int


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
    operation: str = "retract"
    reason: str = ""
    actor: str = "user"


class RepairProposeResponse(BaseModel):
    changeset_id: uuid.UUID
    risk_level: str
    affected_count: int


class RepairApplyResponse(BaseModel):
    changeset_id: uuid.UUID
    success: bool
    operations_executed: int
    recomputed_propositions: int
    gaps_created: int
    errors: list[str]


class HealthResponse(BaseModel):
    status: str
    version: str
