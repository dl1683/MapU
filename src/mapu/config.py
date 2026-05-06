"""Configuration loading for MapU."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://mapu:mapu@localhost:5432/mapu"
    echo: bool = False

    model_config = {"env_prefix": "MAPU_DB_"}


class Settings(BaseSettings):
    database: DatabaseSettings = DatabaseSettings()

    model_config = {"env_prefix": "MAPU_"}
