"""EmbeddingProvider protocol and factory."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

_log = logging.getLogger(__name__)

from mapu.evidence.types import EmbeddingModelRef, EmbeddingVector


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers. Implementations wrap specific APIs or local models."""

    @property
    def model_ref(self) -> EmbeddingModelRef: ...

    async def embed_texts(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]: ...


_PROVIDER_FACTORIES: dict[str, Callable[..., EmbeddingProvider]] = {}


def register_embedding_provider(
    name: str, factory: Callable[..., EmbeddingProvider],
) -> None:
    _PROVIDER_FACTORIES[name.lower()] = factory


def _register_builtins() -> None:
    def _make_hash(**kwargs: object) -> EmbeddingProvider:
        from mapu.providers.embedding_local import HashEmbeddingProvider
        return HashEmbeddingProvider(dimensions=kwargs.get("dimensions", 384))

    def _make_st(**kwargs: object) -> EmbeddingProvider:
        from mapu.providers.embedding_st import SentenceTransformerEmbeddingProvider
        return SentenceTransformerEmbeddingProvider(
            model_name=str(kwargs.get("model_name", "all-MiniLM-L6-v2")),
            dimensions=int(kwargs.get("dimensions", 384)),
            device=str(kwargs.get("device", "cpu")),
        )

    register_embedding_provider("local", _make_hash)
    register_embedding_provider("hash-deterministic", _make_hash)
    register_embedding_provider("sentence-transformers", _make_st)


_register_builtins()

_cached_embedding_provider: EmbeddingProvider | None = None


def get_default_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedding provider (cached at process scope)."""
    global _cached_embedding_provider
    if _cached_embedding_provider is not None:
        return _cached_embedding_provider

    from mapu.config import EmbeddingSettings

    settings = EmbeddingSettings()
    provider_name = settings.provider.lower()
    factory = _PROVIDER_FACTORIES.get(provider_name)
    if factory is None:
        raise ValueError(
            f"Unknown embedding provider '{settings.provider}'. "
            f"Registered: {', '.join(sorted(_PROVIDER_FACTORIES))}. "
            f"Use register_embedding_provider() to add custom providers."
        )

    _cached_embedding_provider = factory(
        model_name=settings.model,
        dimensions=settings.dimensions,
        device=settings.device,
    )
    if provider_name in ("local", "hash-deterministic"):
        _log.warning(
            "Using hash-based embedding provider (no semantic meaning). "
            "Set MAPU_EMBEDDING_PROVIDER=sentence-transformers for production."
        )
    return _cached_embedding_provider
