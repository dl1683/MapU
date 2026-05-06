"""Configuration loading for MapU."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://mapu:mapu@localhost:5432/mapu"
    echo: bool = False

    model_config = {"env_prefix": "MAPU_DB_"}


class EmbeddingSettings(BaseSettings):
    provider: str = "local"
    model: str = "hash-deterministic"
    dimensions: int = 384
    batch_size: int = 64

    model_config = {"env_prefix": "MAPU_EMBEDDING_"}


class ChunkingSettings(BaseSettings):
    max_tokens: int = 512
    overlap_tokens: int = 64

    model_config = {"env_prefix": "MAPU_CHUNKING_"}


class ParserSettings(BaseSettings):
    enabled_types: str = "text/plain"

    model_config = {"env_prefix": "MAPU_PARSER_"}


class SourcePolicySettings(BaseSettings):
    default_document_type: str = "unknown"

    model_config = {"env_prefix": "MAPU_SOURCE_POLICY_"}


class ExtractionSettings(BaseSettings):
    auto_accept_min: float = 0.85
    candidate_min: float = 0.3
    spacy_model: str = "en_core_web_sm"

    model_config = {"env_prefix": "MAPU_EXTRACTION_"}


class Settings(BaseSettings):
    database: DatabaseSettings = DatabaseSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    parser: ParserSettings = ParserSettings()
    source_policy: SourcePolicySettings = SourcePolicySettings()
    extraction: ExtractionSettings = ExtractionSettings()

    model_config = {"env_prefix": "MAPU_", "env_nested_delimiter": "__"}
