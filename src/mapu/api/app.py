"""Litestar application factory for MapU REST API."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from litestar import Litestar
from litestar.config.cors import CORSConfig
from litestar.connection import ASGIConnection
from litestar.di import Provide
from litestar.handlers import BaseRouteHandler
from litestar.openapi.config import OpenAPIConfig
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.api.controllers import all_controllers
from mapu.config import Settings
from mapu.db.engine import build_engine


def _api_key_guard(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    from litestar.exceptions import NotAuthorizedException

    api_key = connection.app.state.get("api_key", "")
    if not api_key:
        return
    provided = connection.headers.get("x-api-key", "")
    if provided != api_key:
        raise NotAuthorizedException(detail="Invalid or missing API key")


def create_app(settings: Settings | None = None) -> Litestar:
    settings = settings or Settings()
    engine, session_factory = build_engine(settings.database)
    cors_config = _build_cors_config(settings.server.cors_origins)

    async def provide_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session
            await session.commit()

    async def on_shutdown() -> None:
        await engine.dispose()

    app = Litestar(
        route_handlers=all_controllers(),
        dependencies={"db_session": Provide(provide_session, use_cache=False)},
        on_shutdown=[on_shutdown],
        openapi_config=OpenAPIConfig(
            title="MapU API",
            version="0.1.0",
            description="Persistent knowledge substrate for document-heavy reasoning",
        ),
        cors_config=cors_config,
        guards=[_api_key_guard],
        debug=False,
    )
    app.state["api_key"] = settings.server.api_key
    return app


def _build_cors_config(origins: str) -> CORSConfig | None:
    allow_origins = [origin.strip() for origin in origins.split(",") if origin.strip()]
    if not allow_origins:
        return None
    return CORSConfig(
        allow_origins=allow_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["content-type", "x-api-key"],
    )


app = create_app()
