"""Integration test fixtures using testcontainers for real PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mapu.models.corpus import Corpus


@pytest.fixture(scope="session")
def postgres_container():
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:pg17", driver=None) as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    user = postgres_container.username
    password = postgres_container.password
    dbname = postgres_container.dbname
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"


@pytest.fixture(scope="session")
def _migrated_database(database_url):
    """Run Alembic migrations against the test database."""
    from alembic import command
    from alembic.config import Config

    sync_url = database_url.replace("+asyncpg", "")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture(scope="session")
def async_engine(database_url, _migrated_database):
    engine = create_async_engine(database_url, echo=False)
    yield engine
    import asyncio
    asyncio.get_event_loop().run_until_complete(engine.dispose())


@pytest.fixture(scope="session")
def session_factory(async_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def session(session_factory) -> AsyncSession:
    async with session_factory() as session:
        await session.begin()
        yield session
        await session.rollback()


@pytest.fixture
async def corpus_a(session: AsyncSession) -> Corpus:
    c = Corpus(
        id=uuid.uuid4(),
        name="test_corpus_a",
        description="Integration test corpus A",
        metadata_={},
        created_at=datetime.now(UTC),
    )
    session.add(c)
    await session.flush()
    return c


@pytest.fixture
async def corpus_b(session: AsyncSession) -> Corpus:
    c = Corpus(
        id=uuid.uuid4(),
        name="test_corpus_b",
        description="Integration test corpus B",
        metadata_={},
        created_at=datetime.now(UTC),
    )
    session.add(c)
    await session.flush()
    return c
