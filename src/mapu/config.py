"""Configuration loading for MapU."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _settings_config(prefix: str) -> SettingsConfigDict:
    return SettingsConfigDict(env_prefix=prefix, env_file=".env", extra="ignore")


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://mapu:mapu@localhost:5432/mapu"
    echo: bool = False

    model_config = _settings_config("MAPU_DB_")


class EmbeddingSettings(BaseSettings):
    provider: str = "local"
    model: str = "hash-deterministic"
    dimensions: int = 384
    batch_size: int = Field(default=64, gt=0)
    device: str = "cpu"

    model_config = _settings_config("MAPU_EMBEDDING_")


class ChunkingSettings(BaseSettings):
    max_tokens: int = 512
    overlap_tokens: int = 64

    model_config = _settings_config("MAPU_CHUNKING_")


class ParserSettings(BaseSettings):
    enabled_types: str = "text/plain"

    model_config = _settings_config("MAPU_PARSER_")


class SourcePolicySettings(BaseSettings):
    default_document_type: str = "other"

    model_config = _settings_config("MAPU_SOURCE_POLICY_")


class ExtractionSettings(BaseSettings):
    auto_accept_min: float = 0.85
    candidate_min: float = 0.3
    spacy_model: str = "en_core_web_sm"

    gliner_enabled: bool = True
    gliner_model: str = "urchade/gliner_small-v2.1"
    gliner_threshold: float = 0.5
    gliner_calibration: float = 0.75

    gliner_relex_enabled: bool = False
    gliner_relex_model: str = "knowledgator/gliner-relex-base-v1.0"
    gliner_relex_entity_threshold: float = 0.4
    gliner_relex_relation_threshold: float = 0.7
    gliner_relex_calibration: float = 0.75

    setfit_enabled: bool = False
    setfit_model: str = "sentence-transformers/paraphrase-MiniLM-L3-v2"
    setfit_trained_path: str = ""
    setfit_threshold: float = 0.5

    srl_enabled: bool = False

    llm_enabled: bool = False
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.0
    llm_min_confidence: float = 0.5

    ml_device: str = "cpu"

    model_config = _settings_config("MAPU_EXTRACTION_")


class LLMSettings(BaseSettings):
    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    timeout: float = 120.0

    model_config = _settings_config("MAPU_LLM_")


class QuerySettings(BaseSettings):
    llm_synthesis_provider: str = ""
    llm_synthesis_model: str = ""
    llm_synthesis_max_tokens: int = 1024

    model_config = _settings_config("MAPU_QUERY_")


class ServerSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8000
    api_key: str = ""
    cors_origins: str = ""

    model_config = _settings_config("MAPU_SERVER_")


class Settings(BaseSettings):
    database: DatabaseSettings = DatabaseSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    parser: ParserSettings = ParserSettings()
    source_policy: SourcePolicySettings = SourcePolicySettings()
    extraction: ExtractionSettings = ExtractionSettings()
    llm: LLMSettings = LLMSettings()
    query: QuerySettings = QuerySettings()
    server: ServerSettings = ServerSettings()

    model_config = SettingsConfigDict(
        env_prefix="MAPU_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )
