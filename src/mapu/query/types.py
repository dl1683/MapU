"""Query engine types: intents, tiers, results, and protocols."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any, Protocol, runtime_checkable


class QueryIntent(StrEnum):
    IDENTITY = "identity"
    RELATIONSHIP = "relationship"
    LIST = "list"
    TEMPORAL = "temporal"
    TEMPORAL_DIFF = "temporal_diff"
    MEASUREMENT = "measurement"
    GAP = "gap"
    CROSS_DOC = "cross_doc"
    INVESTIGATION = "investigation"


class Tier(IntEnum):
    DIRECT = 0
    STRUCTURED = 1
    SYNTHESIS = 2
    INVESTIGATION = 3


@dataclass(frozen=True)
class QueryRequest:
    """A user or agent query submitted to the query engine."""

    corpus_id: uuid.UUID
    question: str
    situation_id: uuid.UUID | None = None
    max_results: int = 20
    include_candidates: bool = False


@dataclass(frozen=True)
class PropositionHit:
    """A proposition matched by a query, with relevance metadata."""

    proposition_id: uuid.UUID
    normalized_text: str
    frame_type: str
    predicate: str
    subject_name: str
    subject_kind: str
    object_name: str | None
    object_kind: str | None
    truth_status: str | None
    extraction_confidence: float
    authority_score: float | None
    source_span_text: str | None
    relevance_score: float


@dataclass(frozen=True)
class QueryResult:
    """Result of processing a query through the cascade governor."""

    request: QueryRequest
    intent: QueryIntent
    tier_used: Tier
    hits: tuple[PropositionHit, ...]
    synthesis: str | None = None
    gaps: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryPlan:
    """Internal plan produced by the cascade governor before execution."""

    intent: QueryIntent
    selected_tier: Tier
    entities_extracted: tuple[str, ...]
    predicates_extracted: tuple[str, ...]
    escalation_reason: str | None = None


@runtime_checkable
class IntentClassifier(Protocol):
    """Protocol for query intent classification."""

    async def classify(self, question: str) -> tuple[QueryIntent, float]: ...


@runtime_checkable
class TierExecutor(Protocol):
    """Protocol for a tier-specific query executor."""

    @property
    def tier(self) -> Tier: ...

    async def execute(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> Sequence[PropositionHit]: ...


@runtime_checkable
class Synthesizer(Protocol):
    """Protocol for generating natural-language answers from proposition hits."""

    async def synthesize(
        self,
        question: str,
        hits: Sequence[PropositionHit],
        intent: QueryIntent,
    ) -> str: ...
