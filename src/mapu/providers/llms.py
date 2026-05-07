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


class OpenAICompatibleLLMProvider:
    """LLM provider using any OpenAI-compatible API (OpenAI, Gemini, local)."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    async def complete_json(
        self, request: LLMRequest,
    ) -> Mapping[str, Any]:
        import json

        import httpx

        url = (self._base_url or "https://api.openai.com/v1") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"answer": content}


def get_default_llm_provider() -> LLMProvider | None:
    """Return the configured LLM provider, or None if not configured."""
    from mapu.config import LLMSettings

    settings = LLMSettings()
    if not settings.provider or not settings.api_key:
        return None

    return OpenAICompatibleLLMProvider(
        api_key=settings.api_key,
        model=settings.model or "gpt-4o-mini",
        base_url=settings.base_url or None,
    )
