"""Sentence-transformers embedding provider for semantic retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from mapu.evidence.types import EmbeddingModelRef, EmbeddingVector


class SentenceTransformerEmbeddingProvider:
    """Embedding provider backed by a local sentence-transformers model."""

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        dimensions: int = 384,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._dims = dimensions
        self._device = device
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    @property
    def model_ref(self) -> EmbeddingModelRef:
        return EmbeddingModelRef(
            provider="sentence-transformers",
            model_name=self._model_name,
            dimensions=self._dims,
        )

    def _encode_sync(self, texts: list[str]) -> list[EmbeddingVector]:
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return [row.tolist()[:self._dims] for row in embeddings]

    async def embed_texts(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        import asyncio

        return await asyncio.to_thread(self._encode_sync, list(texts))
