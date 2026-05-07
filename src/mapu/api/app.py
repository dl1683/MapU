"""Litestar application factory for MapU REST API."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from litestar import Litestar
from litestar.di import Provide
from litestar.openapi.config import OpenAPIConfig
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.api.controllers import all_controllers
from mapu.config import Settings
from mapu.db.engine import build_engine


def create_app(settings: Settings | None = None) -> Litestar:
    settings = settings or Settings()
    engine, session_factory = build_engine(settings.database)

    async def provide_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session
            await session.commit()

    async def on_shutdown() -> None:
        await engine.dispose()

    return Litestar(
        route_handlers=all_controllers(),
        dependencies={"db_session": Provide(provide_session, use_cache=False)},
        on_shutdown=[on_shutdown],
        openapi_config=OpenAPIConfig(
            title="MapU API",
            version="0.1.0",
            description="Persistent knowledge substrate for document-heavy reasoning",
        ),
        debug=False,
    )


app = create_app()
