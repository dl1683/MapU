"""Local/test-safe embedding provider using hash-based deterministic vectors."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Sequence

from mapu.evidence.types import EmbeddingModelRef, EmbeddingVector


class HashEmbeddingProvider:
    """Deterministic embedding provider for tests. Produces consistent vectors from text hashes.

    Not suitable for production semantic search — vectors have no semantic meaning.
    Use for integration tests and offline development.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self._dimensions = dimensions
        self._model_ref = EmbeddingModelRef(
            provider="local",
            model_name="hash-deterministic",
            dimensions=dimensions,
        )

    @property
    def model_ref(self) -> EmbeddingModelRef:
        return self._model_ref

    async def embed_texts(self, texts: Sequence[str]) -> Sequence[EmbeddingVector]:
        return [self._hash_embed(t) for t in texts]

    def _hash_embed(self, text: str) -> EmbeddingVector:
        digest = hashlib.sha512(text.encode("utf-8")).digest()
        floats_from_hash = self._dimensions
        raw: list[float] = []
        i = 0
        while len(raw) < floats_from_hash:
            chunk_input = digest + struct.pack(">I", i)
            h = hashlib.sha256(chunk_input).digest()
            for j in range(0, len(h) - 3, 4):
                if len(raw) >= floats_from_hash:
                    break
                val = struct.unpack(">f", h[j : j + 4])[0]
                if not math.isfinite(val):
                    val = 0.0
                raw.append(val)
            i += 1

        magnitude = math.sqrt(sum(x * x for x in raw))
        if magnitude > 0:
            return [x / magnitude for x in raw]
        return [0.0] * self._dimensions
