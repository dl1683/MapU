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
        timeout: float = 120.0,
    ) -> None:
        import httpx

        self._model = model
        self._url = (base_url or "https://api.openai.com/v1") + "/chat/completions"
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def complete_json(
        self, request: LLMRequest,
    ) -> Mapping[str, Any]:
        import json

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
        resp = await self._client.post(self._url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"answer": content}


class AnthropicLLMProvider:
    """LLM provider using the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        import httpx

        self._model = model
        self._url = (base_url or "https://api.anthropic.com") + "/v1/messages"
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )

    async def complete_json(
        self, request: LLMRequest,
    ) -> Mapping[str, Any]:
        import json

        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "system": request.system_prompt,
            "messages": [
                {"role": "user", "content": request.user_prompt},
            ],
        }
        if request.temperature > 0:
            payload["temperature"] = request.temperature
        resp = await self._client.post(self._url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["content"][0]["text"]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"answer": content}


_PROVIDER_DEFAULTS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-6",
}

_PROVIDER_FACTORIES: dict[str, type[LLMProvider]] = {
    "openai": OpenAICompatibleLLMProvider,
    "anthropic": AnthropicLLMProvider,
}


def register_llm_provider(name: str, factory: type[LLMProvider], default_model: str = "") -> None:
    _PROVIDER_FACTORIES[name.lower()] = factory
    if default_model:
        _PROVIDER_DEFAULTS[name.lower()] = default_model


_cached_llm_provider: LLMProvider | None = None
_llm_checked = False


def get_default_llm_provider() -> LLMProvider | None:
    """Return the configured LLM provider (cached at process scope)."""
    global _cached_llm_provider, _llm_checked
    if _llm_checked:
        return _cached_llm_provider

    from mapu.config import LLMSettings

    settings = LLMSettings()
    if not settings.provider or not settings.api_key:
        _llm_checked = True
        return None

    provider_type = settings.provider.lower()
    factory_cls = _PROVIDER_FACTORIES.get(provider_type)
    if factory_cls is None:
        raise ValueError(
            f"Unknown LLM provider '{settings.provider}'. "
            f"Registered providers: {', '.join(sorted(_PROVIDER_FACTORIES))}. "
            f"Use register_llm_provider() to add custom providers."
        )
    default_model = _PROVIDER_DEFAULTS.get(provider_type, "")

    _cached_llm_provider = factory_cls(
        api_key=settings.api_key,
        model=settings.model or default_model,
        base_url=settings.base_url or None,
        timeout=settings.timeout,
    )
    _llm_checked = True
    return _cached_llm_provider
