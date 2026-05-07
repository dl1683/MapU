"""EmbeddingProvider protocol and factory."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from mapu.evidence.types import EmbeddingModelRef, EmbeddingVector


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers. Implementations wrap specific APIs or local models."""

    @property
    def model_ref(self) -> EmbeddingModelRef: ...

    async def embed_texts(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]: ...


class EmbeddingProviderFactory:
    """Registry-based factory for embedding providers."""

    def __init__(self) -> None:
        self._creators: dict[str, type[EmbeddingProvider]] = {}

    def register(self, provider_name: str, cls: type[EmbeddingProvider]) -> None:
        self._creators[provider_name] = cls

    def available_providers(self) -> frozenset[str]:
        return frozenset(self._creators.keys())


_cached_embedding_provider: EmbeddingProvider | None = None


def get_default_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedding provider (cached at process scope)."""
    global _cached_embedding_provider
    if _cached_embedding_provider is not None:
        return _cached_embedding_provider

    from mapu.config import EmbeddingSettings

    settings = EmbeddingSettings()

    if settings.provider == "sentence-transformers":
        from mapu.providers.embedding_st import SentenceTransformerEmbeddingProvider
        _cached_embedding_provider = SentenceTransformerEmbeddingProvider(
            model_name=settings.model,
            dimensions=settings.dimensions,
            device=settings.device,
        )
    else:
        from mapu.providers.embedding_local import HashEmbeddingProvider
        _cached_embedding_provider = HashEmbeddingProvider(dimensions=settings.dimensions)

    return _cached_embedding_provider
