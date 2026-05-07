"""Add composite indexes for gap/situation/activity listing performance.

Revision ID: 202605070004
Revises: 202605070003
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op

revision: str = "202605070004"
down_revision: str = "202605070003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gap_corpus_status_created "
            "ON gap(corpus_id, status, created_at DESC)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sit_corpus_created "
            "ON situation(corpus_id, created_at DESC)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_act_corpus_type "
            "ON activity(corpus_id, event_type, created_at DESC)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_act_corpus_type")
    op.execute("DROP INDEX IF EXISTS idx_sit_corpus_created")
    op.execute("DROP INDEX IF EXISTS idx_gap_corpus_status_created")
