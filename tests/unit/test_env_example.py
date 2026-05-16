from __future__ import annotations

from pathlib import Path

from mapu.config import (
    ChunkingSettings,
    DatabaseSettings,
    EmbeddingSettings,
    ExtractionSettings,
    LLMSettings,
    ParserSettings,
    QuerySettings,
    ServerSettings,
    SourcePolicySettings,
)


def _env_names(prefix: str, settings_type: type) -> set[str]:
    return {f"{prefix}{name.upper()}" for name in settings_type.model_fields}


def test_env_example_documents_all_settings() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env_example = (repo_root / ".env.example").read_text(encoding="utf-8")
    documented = {
        line.split("=", 1)[0]
        for line in env_example.splitlines()
        if line.startswith("MAPU_") and "=" in line
    }

    expected = set()
    expected |= _env_names("MAPU_DB_", DatabaseSettings)
    expected |= _env_names("MAPU_EMBEDDING_", EmbeddingSettings)
    expected |= _env_names("MAPU_CHUNKING_", ChunkingSettings)
    expected |= _env_names("MAPU_PARSER_", ParserSettings)
    expected |= _env_names("MAPU_SOURCE_POLICY_", SourcePolicySettings)
    expected |= _env_names("MAPU_EXTRACTION_", ExtractionSettings)
    expected |= _env_names("MAPU_LLM_", LLMSettings)
    expected |= _env_names("MAPU_QUERY_", QuerySettings)
    expected |= _env_names("MAPU_SERVER_", ServerSettings)

    assert documented >= expected
