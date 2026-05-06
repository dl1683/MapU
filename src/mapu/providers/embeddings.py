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
