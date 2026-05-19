"""Persist structured continuity contracts on gaps.

Revision ID: 202605180001
Revises: 202605070004
Create Date: 2026-05-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202605180001"
down_revision: str = "202605070004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "gap",
        sa.Column(
            "uncertainty_reason",
            sa.Text(),
            nullable=False,
            server_default="missing_evidence",
        ),
    )
    op.add_column(
        "gap",
        sa.Column(
            "evidence_hypothesis",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "gap",
        sa.Column(
            "next_action",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("gap", sa.Column("expected_resolution", sa.Text(), nullable=True))
    op.add_column(
        "gap",
        sa.Column(
            "governance_tier",
            sa.Text(),
            nullable=False,
            server_default="provisional",
        ),
    )
    op.add_column("gap", sa.Column("priority_score", sa.Float(), nullable=True))
    op.add_column("gap", sa.Column("resolution_summary", sa.Text(), nullable=True))
    op.add_column("gap", sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_check_constraint(
        "ck_gap_governance_tier",
        "gap",
        "governance_tier IN ('guaranteed', 'provisional', 'stale')",
    )
    op.create_check_constraint(
        "ck_gap_priority_score_nonnegative",
        "gap",
        "priority_score IS NULL OR priority_score >= 0",
    )
    op.create_index(
        "idx_gap_continuity_priority",
        "gap",
        ["corpus_id", "status", "governance_tier", "priority_score"],
    )
    op.create_index(
        "idx_gap_evidence_hypothesis_gin",
        "gap",
        ["evidence_hypothesis"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_gap_next_action_gin",
        "gap",
        ["next_action"],
        postgresql_using="gin",
    )

    op.execute("ALTER TABLE gap_target DROP CONSTRAINT IF EXISTS gap_target_target_type_check")
    op.execute("""
    ALTER TABLE gap_target ADD CONSTRAINT gap_target_target_type_check CHECK (
      target_type IN ('proposition', 'handle', 'document', 'span', 'chunk', 'activity', 'changeset')
    )
    """)
    op.execute("""
    CREATE OR REPLACE FUNCTION check_gap_target_exists()
    RETURNS TRIGGER AS $$
    BEGIN
      IF NEW.target_type = 'proposition' THEN
        IF NOT EXISTS (
          SELECT 1 FROM proposition
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent proposition % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      ELSIF NEW.target_type = 'handle' THEN
        IF NOT EXISTS (
          SELECT 1 FROM handle
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent handle % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      ELSIF NEW.target_type = 'document' THEN
        IF NOT EXISTS (
          SELECT 1 FROM document_work
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent document % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      ELSIF NEW.target_type = 'span' THEN
        IF NOT EXISTS (
          SELECT 1 FROM text_span
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent span % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      ELSIF NEW.target_type = 'chunk' THEN
        IF NOT EXISTS (
          SELECT 1 FROM chunk
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent chunk % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      ELSIF NEW.target_type = 'activity' THEN
        IF NOT EXISTS (
          SELECT 1 FROM activity
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent activity % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      ELSIF NEW.target_type = 'changeset' THEN
        IF NOT EXISTS (
          SELECT 1 FROM changeset
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent changeset % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      ELSE
        RAISE EXCEPTION 'unsupported gap_target target_type %', NEW.target_type;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE gap_target DROP CONSTRAINT IF EXISTS gap_target_target_type_check")
    op.execute("""
    ALTER TABLE gap_target ADD CONSTRAINT gap_target_target_type_check CHECK (
      target_type IN ('proposition', 'handle')
    )
    """)
    op.execute("""
    CREATE OR REPLACE FUNCTION check_gap_target_exists()
    RETURNS TRIGGER AS $$
    BEGIN
      IF NEW.target_type = 'proposition' THEN
        IF NOT EXISTS (
          SELECT 1 FROM proposition
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent proposition % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      ELSIF NEW.target_type = 'handle' THEN
        IF NOT EXISTS (
          SELECT 1 FROM handle
          WHERE id = NEW.target_id AND corpus_id = NEW.corpus_id
        ) THEN
          RAISE EXCEPTION 'gap_target references non-existent handle % in corpus %',
            NEW.target_id, NEW.corpus_id;
        END IF;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.drop_index("idx_gap_next_action_gin", table_name="gap")
    op.drop_index("idx_gap_evidence_hypothesis_gin", table_name="gap")
    op.drop_index("idx_gap_continuity_priority", table_name="gap")
    op.drop_constraint("ck_gap_priority_score_nonnegative", "gap", type_="check")
    op.drop_constraint("ck_gap_governance_tier", "gap", type_="check")
    op.drop_column("gap", "last_evaluated_at")
    op.drop_column("gap", "resolution_summary")
    op.drop_column("gap", "priority_score")
    op.drop_column("gap", "governance_tier")
    op.drop_column("gap", "expected_resolution")
    op.drop_column("gap", "next_action")
    op.drop_column("gap", "evidence_hypothesis")
    op.drop_column("gap", "uncertainty_reason")
