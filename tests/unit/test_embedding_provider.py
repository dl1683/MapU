"""Unit tests for embedding providers."""

from __future__ import annotations

import math

import pytest

from mapu.evidence.types import EmbeddingModelRef
from mapu.providers.embedding_local import HashEmbeddingProvider


class TestEmbeddingModelRef:
    def test_tag_format(self) -> None:
        ref = EmbeddingModelRef(
            provider="openai",
            model_name="text-embedding-3-small",
            dimensions=1536,
        )
        assert ref.tag == "openai:text-embedding-3-small:1536"

    def test_local_tag(self) -> None:
        ref = EmbeddingModelRef(
            provider="local",
            model_name="all-MiniLM-L6-v2",
            dimensions=384,
        )
        assert ref.tag == "local:all-MiniLM-L6-v2:384"


class TestHashEmbeddingProvider:
    @pytest.fixture
    def provider(self) -> HashEmbeddingProvider:
        return HashEmbeddingProvider(dimensions=128)

    async def test_correct_dimensions(self, provider: HashEmbeddingProvider) -> None:
        results = await provider.embed_texts(["hello world"])
        assert len(results) == 1
        assert len(results[0]) == 128

    async def test_deterministic(self, provider: HashEmbeddingProvider) -> None:
        r1 = await provider.embed_texts(["test input"])
        r2 = await provider.embed_texts(["test input"])
        assert r1[0] == r2[0]

    async def test_different_texts_different_vectors(
        self, provider: HashEmbeddingProvider
    ) -> None:
        results = await provider.embed_texts(["hello", "world"])
        assert results[0] != results[1]

    async def test_normalized(self, provider: HashEmbeddingProvider) -> None:
        results = await provider.embed_texts(["normalize me"])
        magnitude = math.sqrt(sum(x * x for x in results[0]))
        assert abs(magnitude - 1.0) < 1e-6

    async def test_batch_processing(self, provider: HashEmbeddingProvider) -> None:
        texts = [f"text_{i}" for i in range(10)]
        results = await provider.embed_texts(texts)
        assert len(results) == 10

    async def test_model_ref(self, provider: HashEmbeddingProvider) -> None:
        ref = provider.model_ref
        assert ref.provider == "local"
        assert ref.model_name == "hash-deterministic"
        assert ref.dimensions == 128

    async def test_default_dimensions(self) -> None:
        provider = HashEmbeddingProvider()
        results = await provider.embed_texts(["test"])
        assert len(results[0]) == 384

    async def test_all_finite(self, provider: HashEmbeddingProvider) -> None:
        results = await provider.embed_texts(["test finite"])
        for val in results[0]:
            assert math.isfinite(val)
