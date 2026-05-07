"""Add unique constraint for default situations per corpus.

Revision ID: 202605070003
Revises: 202605070002
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op

revision: str = "202605070003"
down_revision: str = "202605070002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_situation_corpus_default "
            "ON situation(corpus_id) "
            "WHERE kind = 'default'"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_situation_corpus_default")
