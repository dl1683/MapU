"""Add pg_trgm GIN indexes for ILIKE query performance.

Revision ID: 202605070001
Revises: 202605060001
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op

revision: str = "202605070001"
down_revision: str = "202605060001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_handle_name_trgm "
            "ON handle USING GIN (canonical_name gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prop_predicate_trgm "
            "ON proposition USING GIN (predicate gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_prop_text_trgm "
            "ON proposition USING GIN (normalized_text gin_trgm_ops)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_prop_text_trgm")
    op.execute("DROP INDEX IF EXISTS idx_prop_predicate_trgm")
    op.execute("DROP INDEX IF EXISTS idx_handle_name_trgm")
