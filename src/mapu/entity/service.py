"""Handle CRUD and alias management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.entity import Handle
from mapu.providers.embeddings import EmbeddingProvider


class HandleService:
    """Manages handle creation, alias updates, and embedding computation."""

    def __init__(
        self,
        session: AsyncSession,
        corpus_id: uuid.UUID,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._corpus_id = corpus_id
        self._embedder = embedding_provider

    async def create(
        self,
        canonical_name: str,
        kind: str,
        aliases: list[str] | None = None,
    ) -> Handle:
        handle = Handle(
            id=uuid.uuid4(),
            corpus_id=self._corpus_id,
            canonical_name=canonical_name,
            kind=kind,
            aliases=aliases or [],
            created_at=datetime.now(UTC),
        )

        if self._embedder:
            embed_text = self._build_embed_text(canonical_name, aliases or [])
            vectors = await self._embedder.embed_texts([embed_text])
            handle.embedding = list(vectors[0])
            handle.embedding_model = self._embedder.model_ref.tag

        self._session.add(handle)
        await self._session.flush()
        return handle

    async def add_alias(self, handle_id: uuid.UUID, alias: str) -> Handle | None:
        handle = await self._get_scoped(handle_id)
        if handle is None:
            return None
        current_aliases = list(handle.aliases) if handle.aliases else []
        if alias not in current_aliases:
            current_aliases.append(alias)
            handle.aliases = current_aliases
            await self._recompute_embedding(handle)
            await self._session.flush()
        return handle

    async def remove_alias(self, handle_id: uuid.UUID, alias: str) -> Handle | None:
        handle = await self._get_scoped(handle_id)
        if handle is None:
            return None
        current_aliases = list(handle.aliases) if handle.aliases else []
        if alias in current_aliases:
            current_aliases.remove(alias)
            handle.aliases = current_aliases
            await self._recompute_embedding(handle)
            await self._session.flush()
        return handle

    async def merge(
        self, source_id: uuid.UUID, target_id: uuid.UUID
    ) -> Handle | None:
        source = await self._get_scoped(source_id)
        target = await self._get_scoped(target_id)
        if source is None or target is None:
            return None

        merged_aliases = list(target.aliases) if target.aliases else []
        if source.canonical_name not in merged_aliases:
            merged_aliases.append(source.canonical_name)
        for alias in source.aliases or []:
            if alias not in merged_aliases:
                merged_aliases.append(alias)

        target.aliases = merged_aliases
        source.status = "merged"

        await self._recompute_embedding(target)
        await self._session.flush()
        return target

    async def deactivate(self, handle_id: uuid.UUID) -> bool:
        stmt = (
            update(Handle)
            .where(Handle.id == handle_id, Handle.corpus_id == self._corpus_id)
            .values(status="merged")
        )
        result = await self._session.execute(stmt)
        return bool(getattr(result, "rowcount", 0) > 0)

    async def get_active(self, handle_id: uuid.UUID) -> Handle | None:
        stmt = select(Handle).where(
            Handle.id == handle_id,
            Handle.corpus_id == self._corpus_id,
            Handle.status == "active",
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_scoped(self, handle_id: uuid.UUID) -> Handle | None:
        stmt = select(Handle).where(
            Handle.id == handle_id,
            Handle.corpus_id == self._corpus_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _recompute_embedding(self, handle: Handle) -> None:
        if self._embedder is None:
            return
        embed_text = self._build_embed_text(
            handle.canonical_name, list(handle.aliases) if handle.aliases else []
        )
        vectors = await self._embedder.embed_texts([embed_text])
        handle.embedding = list(vectors[0])
        handle.embedding_model = self._embedder.model_ref.tag

    @staticmethod
    def _build_embed_text(canonical_name: str, aliases: list[str]) -> str:
        parts = [canonical_name] + aliases
        return " | ".join(parts)
