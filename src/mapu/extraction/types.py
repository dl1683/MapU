"""Extraction pipeline types: context, candidates, signals, and protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from mapu.types import AttestationStrength, FrameType, Stance


@dataclass(frozen=True)
class BaseParse:
    """spaCy base parse results. Offsets are span-local (relative to span text, not document)."""

    tokens: tuple[str, ...]
    pos_tags: tuple[str, ...]
    lemmas: tuple[str, ...]
    sentence_spans: tuple[tuple[int, int], ...]
    entities: tuple[EntityMention, ...]


@dataclass(frozen=True)
class ExtractionContext:
    """Input to an extractor: a single text span with metadata."""

    corpus_id: uuid.UUID
    document_id: uuid.UUID
    expression_id: uuid.UUID
    span_id: uuid.UUID
    node_id: uuid.UUID | None
    text: str
    start_char: int
    end_char: int
    base_parse: BaseParse | None = None
    prior_signals: tuple[ExtractionSignal, ...] = ()


@dataclass(frozen=True)
class EntityMention:
    """An entity mention detected in text."""

    text: str
    kind: str
    start_char: int
    end_char: int
    confidence: float
    source: str


@dataclass(frozen=True)
class ExtractionSignal:
    """A non-proposition signal produced by an extractor (date, cross-ref, etc.)."""

    signal_type: str
    data: dict[str, Any] = field(default_factory=dict)
    start_char: int = 0
    end_char: int = 0
    source: str = ""


@dataclass(frozen=True)
class PropositionFrameCandidate:
    """A candidate proposition extracted from text, before grounding."""

    span_id: uuid.UUID
    frame_type: FrameType
    subject: EntityMention
    predicate: str
    object: EntityMention | None
    value: dict[str, Any] | None
    polarity: bool
    modality: str | None
    valid_range: tuple[datetime | None, datetime | None] | None
    normalized_text: str
    qualifiers: dict[str, Any]
    stance: Stance
    attestation_strength: AttestationStrength | None
    extraction_method: str
    extraction_confidence: float


@dataclass(frozen=True)
class ExtractorOutput:
    """Combined output from a single extractor."""

    frames: tuple[PropositionFrameCandidate, ...] = ()
    signals: tuple[ExtractionSignal, ...] = ()


@runtime_checkable
class Extractor(Protocol):
    """Protocol for all extraction tools (rule-based, spaCy, ML, etc.)."""

    @property
    def name(self) -> str: ...

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput: ...
