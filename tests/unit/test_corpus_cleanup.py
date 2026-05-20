from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

from mapu.repos.corpus_cleanup import CORPUS_SCOPED_DELETE_TABLES, delete_corpus_rows


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    async def execute(self, statement: object, params: dict[str, object] | None = None) -> None:
        self.calls.append((str(statement), params))


@pytest.mark.asyncio
async def test_delete_corpus_rows_removes_dependencies_before_corpus() -> None:
    session = RecordingSession()
    corpus_id = uuid.uuid4()

    await delete_corpus_rows(session, corpus_id)

    statements = [sql for sql, _params in session.calls]
    assert statements[0] == "DELETE FROM activity WHERE corpus_id = :corpus_id"
    assert statements[-2] == "DELETE FROM document_work WHERE corpus_id = :corpus_id"
    assert statements[-1] == "DELETE FROM corpus WHERE id = :corpus_id"
    assert len(statements) == len(CORPUS_SCOPED_DELETE_TABLES) + 1
    assert all(params == {"corpus_id": corpus_id} for _sql, params in session.calls)


@pytest.mark.asyncio
async def test_delete_corpus_rows_deletes_document_work_after_child_evidence() -> None:
    session = RecordingSession()

    await delete_corpus_rows(session, uuid.uuid4())

    statements = [sql for sql, _params in session.calls]
    document_work_index = statements.index("DELETE FROM document_work WHERE corpus_id = :corpus_id")
    for child in (
        "document_expression",
        "structure_node",
        "text_span",
        "chunk",
        "chunk_embedding",
        "source_policy_eval",
        "situation",
    ):
        child_index = statements.index(f"DELETE FROM {child} WHERE corpus_id = :corpus_id")
        assert child_index < document_work_index


def test_cleanup_index_migration_covers_high_volume_delete_tables() -> None:
    migration_path = (
        Path(__file__).parents[2]
        / "src"
        / "mapu"
        / "db"
        / "migrations"
        / "versions"
        / "202605200001_corpus_cleanup_indexes.py"
    )
    spec = importlib.util.spec_from_file_location("cleanup_indexes_migration", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    indexed_tables = {table_name for _index_name, table_name in module._CLEANUP_INDEXES}
    assert indexed_tables == {
        "changeset_operation",
        "gap_target",
        "computation_run",
        "supersession_edge",
        "derivation_edge",
        "proposition_state_basis",
        "proposition_state",
        "attestation_situation",
        "attestation",
        "proposition_participant",
        "identity_decision",
        "chunk",
        "text_span",
        "structure_node",
        "document_expression",
    }
