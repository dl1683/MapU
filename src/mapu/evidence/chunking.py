"""Chunker and TokenCounter protocols, plus default span-aware chunker."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from mapu.evidence.types import ChunkCandidate, ParsedDocument


@runtime_checkable
class TokenCounter(Protocol):
    """Counts tokens for a given text. Implementation-specific (tiktoken, etc.)."""

    def count(self, text: str) -> int: ...


@runtime_checkable
class Chunker(Protocol):
    """Splits a parsed document into chunk candidates."""

    @property
    def chunker_id(self) -> str: ...

    def chunk(self, parsed: ParsedDocument) -> Sequence[ChunkCandidate]: ...


class SimpleCharTokenCounter:
    """Approximate token counter: 1 token ≈ 4 characters."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


class SpanAwareChunker:
    """Default chunker that respects span boundaries with configurable overlap."""

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 64,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens
        self._counter = token_counter or SimpleCharTokenCounter()

    @property
    def chunker_id(self) -> str:
        return f"span_aware:{self._max_tokens}:{self._overlap_tokens}"

    def chunk(self, parsed: ParsedDocument) -> Sequence[ChunkCandidate]:
        if not parsed.full_text:
            return []

        candidates: list[ChunkCandidate] = []
        text = parsed.full_text
        pos = 0

        while pos < len(text):
            end = self._find_chunk_end(text, pos)
            chunk_text = text[pos:end]
            token_count = self._counter.count(chunk_text)

            start_span = self._find_span_index(parsed, pos)
            end_span = self._find_span_index(parsed, end - 1)

            candidates.append(ChunkCandidate(
                text=chunk_text,
                start_char=pos,
                end_char=end,
                token_count=token_count,
                start_span_index=start_span,
                end_span_index=end_span,
            ))

            if end >= len(text):
                break

            overlap_chars = self._overlap_tokens * 4
            advance = end - overlap_chars
            pos = max(pos + 1, advance)

        return candidates

    def _find_chunk_end(self, text: str, start: int) -> int:
        max_chars = self._max_tokens * 4
        end = min(start + max_chars, len(text))

        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start + max_chars // 2:
                return newline + 1
            space = text.rfind(" ", start, end)
            if space > start + max_chars // 2:
                return space + 1

        return end

    @staticmethod
    def _find_span_index(parsed: ParsedDocument, char_pos: int) -> int | None:
        for i, span in enumerate(parsed.spans):
            if span.start_char <= char_pos < span.end_char:
                return i
        return None
