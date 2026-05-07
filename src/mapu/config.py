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

    gliner_enabled: bool = False
    gliner_model: str = "urchade/gliner_small-v2.1"
    gliner_threshold: float = 0.5
    gliner_calibration: float = 0.75

    rebel_enabled: bool = False
    rebel_model: str = "Babelscape/rebel-large"
    rebel_calibration: float = 0.65

    setfit_enabled: bool = False
    setfit_model: str = "sentence-transformers/paraphrase-MiniLM-L3-v2"
    setfit_trained_path: str = ""
    setfit_threshold: float = 0.5

    srl_enabled: bool = False

    ml_device: str = "cpu"

    model_config = {"env_prefix": "MAPU_EXTRACTION_"}


class QuerySettings(BaseSettings):
    llm_synthesis_provider: str = ""
    llm_synthesis_model: str = ""
    llm_synthesis_max_tokens: int = 1024

    model_config = {"env_prefix": "MAPU_QUERY_"}


class ServerSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8000
    api_key: str = ""
    cors_origins: str = ""

    model_config = {"env_prefix": "MAPU_SERVER_"}


class Settings(BaseSettings):
    database: DatabaseSettings = DatabaseSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    chunking: ChunkingSettings = ChunkingSettings()
    parser: ParserSettings = ParserSettings()
    source_policy: SourcePolicySettings = SourcePolicySettings()
    extraction: ExtractionSettings = ExtractionSettings()
    query: QuerySettings = QuerySettings()
    server: ServerSettings = ServerSettings()

    model_config = {"env_prefix": "MAPU_", "env_nested_delimiter": "__"}
