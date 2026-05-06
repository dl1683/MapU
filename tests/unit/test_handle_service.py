"""Unit tests for handle service logic."""

from __future__ import annotations

from mapu.entity.service import HandleService


class TestBuildEmbedText:
    def test_name_only(self) -> None:
        result = HandleService._build_embed_text("Apple Inc", [])
        assert result == "Apple Inc"

    def test_name_with_aliases(self) -> None:
        result = HandleService._build_embed_text("Apple Inc", ["AAPL", "Apple"])
        assert result == "Apple Inc | AAPL | Apple"

    def test_single_alias(self) -> None:
        result = HandleService._build_embed_text("Tesla", ["TSLA"])
        assert result == "Tesla | TSLA"
