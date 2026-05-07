"""LLM provider protocol for validation and synthesis tasks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMRequest:
    """A request to an LLM provider."""

    system_prompt: str
    user_prompt: str
    max_tokens: int = 512
    temperature: float = 0.0


@dataclass(frozen=True)
class CandidateValidation:
    """Result of LLM validation of an extraction candidate."""

    assessment: str
    confidence_adjustment: float
    explanation: str


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers. Provider-agnostic interface."""

    async def complete_json(
        self, request: LLMRequest,
    ) -> Mapping[str, Any]: ...


@runtime_checkable
class CandidateValidator(Protocol):
    """Protocol for validating extraction candidates via LLM."""

    async def validate(
        self,
        span_text: str,
        candidate_summary: Mapping[str, Any],
    ) -> CandidateValidation: ...
