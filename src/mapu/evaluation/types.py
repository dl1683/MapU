"""Benchmark case and result types for the evaluation framework."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class BenchmarkDomain(StrEnum):
    CODE = "code"
    LEGAL = "legal"
    FINANCE = "finance"
    BIOMEDICAL = "biomedical"
    INTELLIGENCE = "intelligence"
    ACADEMIC = "academic"


class EvalPhase(StrEnum):
    EXTRACTION = "extraction"
    GROUNDING = "grounding"
    TRUTH = "truth"
    QUERY = "query"
    INVESTIGATION = "investigation"


@dataclass(frozen=True)
class ExpectedEntity:
    text: str
    kind: str


@dataclass(frozen=True)
class ExpectedProposition:
    normalized_text: str
    predicate: str
    subject: str
    object: str | None = None
    frame_type: str = "finding"


@dataclass(frozen=True)
class ExpectedTruthStatus:
    proposition_text: str
    expected_status: str


@dataclass(frozen=True)
class ExpectedQueryHit:
    proposition_text: str
    min_rank: int | None = None


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    domain: BenchmarkDomain
    description: str
    source_text: str
    source_mime_type: str = "text/plain"
    source_metadata: dict[str, str] = field(default_factory=dict)
    expected_entities: tuple[ExpectedEntity, ...] = ()
    expected_propositions: tuple[ExpectedProposition, ...] = ()
    expected_truth: tuple[ExpectedTruthStatus, ...] = ()
    expected_query_hits: tuple[ExpectedQueryHit, ...] = ()
    query_question: str | None = None
    tags: tuple[str, ...] = ()


@dataclass
class PhaseResult:
    phase: EvalPhase
    success: bool
    details: dict[str, object] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class CaseResult:
    case_id: str
    domain: str
    corpus_id: uuid.UUID | None = None
    phases: list[PhaseResult] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class SuiteResult:
    suite_name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    git_commit: str = ""
    case_results: list[CaseResult] = field(default_factory=list)
    aggregate_metrics: dict[str, float] = field(default_factory=dict)
    duration_ms: float = 0.0
