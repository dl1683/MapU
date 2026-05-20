"""Add corpus cleanup indexes for destructive CLI/MCP workflows.

Revision ID: 202605200001
Revises: 202605180001
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op

revision: str = "202605200001"
down_revision: str = "202605180001"
branch_labels: str | None = None
depends_on: str | None = None

_CLEANUP_INDEXES: tuple[tuple[str, str], ...] = (
    ("idx_cleanup_changeset_operation_corpus", "changeset_operation"),
    ("idx_cleanup_gap_target_corpus", "gap_target"),
    ("idx_cleanup_computation_run_corpus", "computation_run"),
    ("idx_cleanup_supersession_edge_corpus", "supersession_edge"),
    ("idx_cleanup_derivation_edge_corpus", "derivation_edge"),
    ("idx_cleanup_proposition_state_basis_corpus", "proposition_state_basis"),
    ("idx_cleanup_proposition_state_corpus", "proposition_state"),
    ("idx_cleanup_attestation_situation_corpus", "attestation_situation"),
    ("idx_cleanup_attestation_corpus", "attestation"),
    ("idx_cleanup_proposition_participant_corpus", "proposition_participant"),
    ("idx_cleanup_identity_decision_corpus", "identity_decision"),
    ("idx_cleanup_chunk_corpus", "chunk"),
    ("idx_cleanup_text_span_corpus", "text_span"),
    ("idx_cleanup_structure_node_corpus", "structure_node"),
    ("idx_cleanup_document_expression_corpus", "document_expression"),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for index_name, table_name in _CLEANUP_INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} "
                f"ON {table_name}(corpus_id)"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for index_name, _table_name in reversed(_CLEANUP_INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")
