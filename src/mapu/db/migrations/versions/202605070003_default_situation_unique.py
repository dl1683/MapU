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
    op.execute(
        "WITH survivors AS ("
        "  SELECT DISTINCT ON (corpus_id) id, corpus_id FROM situation "
        "  WHERE kind = 'default' ORDER BY corpus_id, created_at ASC"
        "), dupes AS ("
        "  SELECT s.id, s.corpus_id, sv.id AS survivor_id "
        "  FROM situation s JOIN survivors sv USING (corpus_id) "
        "  WHERE s.kind = 'default' AND s.id != sv.id"
        ") "
        "UPDATE attestation_situation AS ats SET situation_id = d.survivor_id "
        "FROM dupes d WHERE ats.situation_id = d.id AND ats.corpus_id = d.corpus_id"
    )
    op.execute(
        "WITH survivors AS ("
        "  SELECT DISTINCT ON (corpus_id) id, corpus_id FROM situation "
        "  WHERE kind = 'default' ORDER BY corpus_id, created_at ASC"
        "), dupes AS ("
        "  SELECT s.id, s.corpus_id, sv.id AS survivor_id "
        "  FROM situation s JOIN survivors sv USING (corpus_id) "
        "  WHERE s.kind = 'default' AND s.id != sv.id"
        ") "
        "UPDATE proposition_state AS ps SET situation_id = d.survivor_id "
        "FROM dupes d WHERE ps.situation_id = d.id AND ps.corpus_id = d.corpus_id"
    )
    op.execute(
        "WITH survivors AS ("
        "  SELECT DISTINCT ON (corpus_id) id, corpus_id FROM situation "
        "  WHERE kind = 'default' ORDER BY corpus_id, created_at ASC"
        "), dupes AS ("
        "  SELECT s.id, s.corpus_id, sv.id AS survivor_id "
        "  FROM situation s JOIN survivors sv USING (corpus_id) "
        "  WHERE s.kind = 'default' AND s.id != sv.id"
        ") "
        "UPDATE situation AS ch SET parent_id = d.survivor_id "
        "FROM dupes d WHERE ch.parent_id = d.id AND ch.corpus_id = d.corpus_id"
    )
    op.execute(
        "DELETE FROM situation WHERE id NOT IN ("
        "  SELECT DISTINCT ON (corpus_id) id FROM situation "
        "  WHERE kind = 'default' ORDER BY corpus_id, created_at ASC"
        ") AND kind = 'default'"
    )
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_situation_corpus_default "
            "ON situation(corpus_id) "
            "WHERE kind = 'default'"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_situation_corpus_default")
