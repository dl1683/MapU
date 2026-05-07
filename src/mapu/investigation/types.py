"""Investigation engine types: budgets, actions, observations, findings, results."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ActionKind(StrEnum):
    STRUCTURED_QUERY = "structured_query"
    EMBEDDING_SEARCH = "embedding_search"
    CHUNK_RETRIEVAL = "chunk_retrieval"
    ENTITY_LOOKUP = "entity_lookup"
    TEMPORAL_DIFF = "temporal_diff"
    GAP_CHECK = "gap_check"


class TerminationReason(StrEnum):
    BUDGET_EXHAUSTED = "budget_exhausted"
    COVERAGE_MET = "coverage_met"
    DIMINISHING_RETURNS = "diminishing_returns"
    CONTRADICTION_FOUND = "contradiction_found"
    CIRCULAR_RETRIEVAL = "circular_retrieval"
    PLANNER_STOP = "planner_stop"


@dataclass(frozen=True)
class InvestigationBudget:
    max_llm_calls: int = 10
    max_actions: int = 25
    max_documents_read: int = 50
    max_time_seconds: int = 300
    target_coverage: float = 0.9
    min_new_info_per_step: float = 0.05


@dataclass(frozen=True)
class InvestigationAction:
    kind: ActionKind
    query: str
    entities: tuple[str, ...] = ()
    predicates: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class InvestigationPlan:
    actions: tuple[InvestigationAction, ...]
    reasoning: str = ""


@dataclass(frozen=True)
class InvestigationEvidence:
    proposition_id: uuid.UUID
    normalized_text: str
    source_span: str | None
    authority_score: float | None
    document_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Observation:
    action: InvestigationAction
    proposition_ids_found: tuple[uuid.UUID, ...] = ()
    new_entities_discovered: tuple[str, ...] = ()
    new_predicates_discovered: tuple[str, ...] = ()
    span_texts: tuple[str, ...] = ()
    document_ids: tuple[uuid.UUID, ...] = ()
    evidence: tuple[InvestigationEvidence, ...] = ()


@dataclass(frozen=True)
class DerivedPropositionDraft:
    normalized_text: str
    frame_type: str
    predicate: str
    subject_name: str
    object_name: str | None = None
    derivation_basis: tuple[uuid.UUID, ...] = ()
    confidence: float = 0.5


@dataclass
class InvestigationState:
    budget: InvestigationBudget
    llm_calls_used: int = 0
    actions_executed: int = 0
    documents_read: int = 0
    observations: list[Observation] = field(default_factory=list)
    known_entity_coverage: float = 0.0
    known_predicate_coverage: float = 0.0
    has_entity_targets: bool = False
    has_predicate_targets: bool = False
    seen_proposition_ids: set[uuid.UUID] = field(default_factory=set)
    seen_document_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def coverage(self) -> float:
        dims: list[float] = []
        if self.has_entity_targets:
            dims.append(self.known_entity_coverage)
        if self.has_predicate_targets:
            dims.append(self.known_predicate_coverage)
        if not dims:
            return 0.0
        return sum(dims) / len(dims)

    def budget_exhausted(self) -> bool:
        return (
            self.llm_calls_used >= self.budget.max_llm_calls
            or self.actions_executed >= self.budget.max_actions
            or self.documents_read >= self.budget.max_documents_read
        )


@dataclass(frozen=True)
class InvestigationResult:
    answer: str
    evidence: tuple[InvestigationEvidence, ...]
    gaps: tuple[str, ...]
    findings: tuple[DerivedPropositionDraft, ...]
    metadata: dict[str, Any]
    termination_reason: TerminationReason
    persisted_proposition_ids: tuple[uuid.UUID, ...] = ()
