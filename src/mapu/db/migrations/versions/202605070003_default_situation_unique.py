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
    _DUPES_CTE = (
        "WITH survivors AS ("
        "  SELECT DISTINCT ON (corpus_id) id, corpus_id FROM situation "
        "  WHERE kind = 'default' ORDER BY corpus_id, created_at ASC"
        "), dupes AS ("
        "  SELECT s.id, s.corpus_id, sv.id AS survivor_id "
        "  FROM situation s JOIN survivors sv USING (corpus_id) "
        "  WHERE s.kind = 'default' AND s.id != sv.id"
        ") "
    )

    op.execute(
        _DUPES_CTE
        + ", keepers AS ("
        "  SELECT DISTINCT ON (ats.attestation_id, ats.corpus_id) ats.id "
        "  FROM attestation_situation ats "
        "  JOIN situation s ON ats.situation_id = s.id "
        "  WHERE s.kind = 'default' AND ats.invalidated_at IS NULL "
        "  ORDER BY ats.attestation_id, ats.corpus_id, ats.created_at ASC"
        ") "
        "DELETE FROM attestation_situation AS ats_del "
        "USING dupes d "
        "WHERE ats_del.situation_id = d.id "
        "AND ats_del.corpus_id = d.corpus_id "
        "AND ats_del.invalidated_at IS NULL "
        "AND ats_del.id NOT IN (SELECT id FROM keepers)"
    )

    op.execute(
        _DUPES_CTE
        + ", keepers AS ("
        "  SELECT DISTINCT ON (ps.proposition_id, ps.corpus_id) ps.id "
        "  FROM proposition_state ps "
        "  JOIN situation s ON ps.situation_id = s.id "
        "  WHERE s.kind = 'default' "
        "  ORDER BY ps.proposition_id, ps.corpus_id, ps.computed_at DESC"
        ") "
        "DELETE FROM proposition_state AS ps_del "
        "USING dupes d "
        "WHERE ps_del.situation_id = d.id "
        "AND ps_del.corpus_id = d.corpus_id "
        "AND ps_del.id NOT IN (SELECT id FROM keepers)"
    )

    op.execute(
        _DUPES_CTE
        + "UPDATE attestation_situation AS ats SET situation_id = d.survivor_id "
        "FROM dupes d WHERE ats.situation_id = d.id AND ats.corpus_id = d.corpus_id"
    )
    op.execute(
        _DUPES_CTE
        + "UPDATE proposition_state AS ps SET situation_id = d.survivor_id "
        "FROM dupes d WHERE ps.situation_id = d.id AND ps.corpus_id = d.corpus_id"
    )
    op.execute(
        _DUPES_CTE
        + "UPDATE situation AS ch SET parent_id = d.survivor_id "
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
