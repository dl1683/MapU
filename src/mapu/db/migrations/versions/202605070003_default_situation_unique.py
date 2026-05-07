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
        "  WHERE kind = 'default' ORDER BY corpus_id, created_at ASC, id ASC"
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
        "  LEFT JOIN survivors sv ON s.id = sv.id "
        "  WHERE s.kind = 'default' AND ats.invalidated_at IS NULL "
        "  ORDER BY ats.attestation_id, ats.corpus_id, "
        "    CASE WHEN sv.id IS NOT NULL THEN 0 ELSE 1 END, ats.created_at ASC, ats.id ASC"
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
        + "DELETE FROM proposition_state AS ps_del "
        "USING dupes d "
        "WHERE ps_del.situation_id = d.id "
        "AND ps_del.corpus_id = d.corpus_id "
        "AND EXISTS ("
        "  SELECT 1 FROM proposition_state ps_surv "
        "  WHERE ps_surv.proposition_id = ps_del.proposition_id "
        "  AND ps_surv.situation_id = d.survivor_id "
        "  AND ps_surv.corpus_id = ps_del.corpus_id"
        ")"
    )
    op.execute(
        _DUPES_CTE
        + ", source_pick AS ("
        "  SELECT DISTINCT ON (ps.proposition_id, ps.corpus_id) "
        "    ps.situation_id AS keep_sit, ps.proposition_id, ps.corpus_id "
        "  FROM proposition_state ps "
        "  JOIN dupes d ON ps.situation_id = d.id AND ps.corpus_id = d.corpus_id "
        "  ORDER BY ps.proposition_id, ps.corpus_id, ps.computed_at DESC, ps.situation_id ASC, ps.id ASC"
        ") "
        "DELETE FROM proposition_state AS ps_del "
        "USING dupes d "
        "WHERE ps_del.situation_id = d.id "
        "AND ps_del.corpus_id = d.corpus_id "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM source_pick sp "
        "  WHERE sp.proposition_id = ps_del.proposition_id "
        "  AND sp.corpus_id = ps_del.corpus_id "
        "  AND sp.keep_sit = ps_del.situation_id"
        ")"
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
        "  WHERE kind = 'default' ORDER BY corpus_id, created_at ASC, id ASC"
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
