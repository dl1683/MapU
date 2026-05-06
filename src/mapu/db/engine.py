"""Async database engine and session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mapu.config import DatabaseSettings


def build_engine(settings: DatabaseSettings) -> tuple[
    "AsyncEngine",  # noqa: F821
    async_sessionmaker[AsyncSession],
]:
    engine = create_async_engine(settings.url, echo=settings.echo)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory
