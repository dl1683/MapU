"""Dependency-aware corpus cleanup helpers."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import text


class _AsyncExecutable(Protocol):
    async def execute(
        self,
        statement: object,
        params: dict[str, object] | None = None,
    ) -> object: ...


# Tables are ordered from leaves back to corpus roots. The database schema keeps
# evidence immutable during normal operation, so destructive corpus cleanup must
# explicitly remove dependent rows before deleting the corpus row itself.
CORPUS_SCOPED_DELETE_TABLES: tuple[str, ...] = (
    "activity",
    "changeset_operation",
    "changeset",
    "gap_target",
    "gap",
    "computation_run",
    "computation_spec",
    "supersession_edge",
    "derivation_edge",
    "proposition_state_basis",
    "proposition_state",
    "attestation_situation",
    "attestation",
    "source_policy_eval",
    "proposition_participant",
    "proposition",
    "query_view",
    "situation",
    "identity_decision",
    "handle",
    "chunk_embedding",
    "chunk",
    "text_span",
    "structure_node",
    "document_expression",
    "document_work",
)


async def delete_corpus_rows(session: _AsyncExecutable, corpus_id: uuid.UUID) -> None:
    """Delete one corpus and all corpus-scoped dependent rows in FK-safe order."""

    params = {"corpus_id": corpus_id}
    for table_name in CORPUS_SCOPED_DELETE_TABLES:
        await session.execute(
            text(f"DELETE FROM {table_name} WHERE corpus_id = :corpus_id"),
            params,
        )
    await session.execute(text("DELETE FROM corpus WHERE id = :corpus_id"), params)
