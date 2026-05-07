"""Add HNSW vector index and authority ordering indexes.

Revision ID: 202605070002
Revises: 202605070001
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op

revision: str = "202605070002"
down_revision: str = "202605070001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ce_corpus_model "
            "ON chunk_embedding(corpus_id, model_name)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ce_embedding_hnsw "
            "ON chunk_embedding USING hnsw ((embedding::vector(384)) vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64) "
            "WHERE dimensions = 384"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_att_accepted_spe "
            "ON attestation(corpus_id, proposition_id, source_policy_eval_id) "
            "WHERE status = 'accepted' AND system_invalidated IS NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_spe_authority "
            "ON source_policy_eval(authority_score DESC, id)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prop_corpus_created "
            "ON proposition(corpus_id, system_created DESC)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_prop_corpus_created")
    op.execute("DROP INDEX IF EXISTS idx_spe_authority")
    op.execute("DROP INDEX IF EXISTS idx_att_accepted_spe")
    op.execute("DROP INDEX IF EXISTS idx_ce_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_ce_corpus_model")
