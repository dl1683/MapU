"""Foundation truth schema.

Revision ID: 202605060001
Revises:
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op

revision: str = "202605060001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
    -- Extensions
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS btree_gist;

    -- ============================================
    -- 1. WORKSPACE
    -- ============================================

    CREATE TABLE corpus (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name TEXT NOT NULL,
      description TEXT,
      metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- ============================================
    -- 2-7. EVIDENCE (IMMUTABLE)
    -- ============================================

    CREATE TABLE document_work (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      raw_content BYTEA,
      mime_type TEXT NOT NULL,
      source_uri TEXT,
      metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
      ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (id, corpus_id)
    );

    CREATE TABLE document_expression (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      document_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      parser_version TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (id, corpus_id),
      FOREIGN KEY (document_id, corpus_id) REFERENCES document_work(id, corpus_id)
    );

    CREATE TABLE structure_node (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      expression_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      parent_id UUID,
      node_type TEXT NOT NULL,
      ordinal INT NOT NULL DEFAULT 0,
      metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
      UNIQUE (id, corpus_id),
      FOREIGN KEY (expression_id, corpus_id) REFERENCES document_expression(id, corpus_id),
      FOREIGN KEY (parent_id, corpus_id) REFERENCES structure_node(id, corpus_id)
    );

    CREATE TABLE text_span (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      expression_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      node_id UUID,
      text TEXT NOT NULL,
      start_char INT NOT NULL,
      end_char INT NOT NULL,
      CHECK (end_char > start_char),
      UNIQUE (id, corpus_id),
      FOREIGN KEY (expression_id, corpus_id) REFERENCES document_expression(id, corpus_id),
      FOREIGN KEY (node_id, corpus_id) REFERENCES structure_node(id, corpus_id)
    );

    CREATE TABLE chunk (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      expression_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      text TEXT NOT NULL,
      start_span_id UUID,
      end_span_id UUID,
      token_count INT NOT NULL CHECK (token_count > 0),
      UNIQUE (id, corpus_id),
      FOREIGN KEY (expression_id, corpus_id) REFERENCES document_expression(id, corpus_id),
      FOREIGN KEY (start_span_id, corpus_id) REFERENCES text_span(id, corpus_id),
      FOREIGN KEY (end_span_id, corpus_id) REFERENCES text_span(id, corpus_id)
    );

    CREATE TABLE chunk_embedding (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      chunk_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      model_name TEXT NOT NULL,
      dimensions INT NOT NULL CHECK (dimensions > 0),
      embedding vector NOT NULL,
      UNIQUE (chunk_id, model_name),
      FOREIGN KEY (chunk_id, corpus_id) REFERENCES chunk(id, corpus_id)
    );

    -- ============================================
    -- 8-9. ENTITY (REVERSIBLE)
    -- ============================================

    CREATE TABLE handle (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      canonical_name TEXT NOT NULL,
      kind TEXT NOT NULL,
      aliases TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
      embedding vector,
      embedding_model TEXT,
      status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'merged', 'split')),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (id, corpus_id)
    );

    CREATE TABLE identity_decision (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      handle_a_id UUID NOT NULL,
      handle_b_id UUID NOT NULL,
      decision TEXT NOT NULL CHECK (decision IN ('same_entity', 'different_entity', 'uncertain')),
      confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
      evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
      decided_by TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      invalidated_at TIMESTAMPTZ,
      CHECK (handle_a_id <> handle_b_id),
      FOREIGN KEY (handle_a_id, corpus_id) REFERENCES handle(id, corpus_id),
      FOREIGN KEY (handle_b_id, corpus_id) REFERENCES handle(id, corpus_id)
    );

    -- ============================================
    -- 10-11. CONTEXT
    -- ============================================

    CREATE TABLE situation (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      kind TEXT NOT NULL,
      name TEXT NOT NULL,
      parent_id UUID,
      document_id UUID,
      valid_range TSTZRANGE,
      assumptions JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (id, corpus_id),
      FOREIGN KEY (parent_id, corpus_id) REFERENCES situation(id, corpus_id),
      FOREIGN KEY (document_id, corpus_id) REFERENCES document_work(id, corpus_id)
    );

    CREATE TABLE query_view (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      name TEXT NOT NULL,
      description TEXT,
      is_default BOOLEAN NOT NULL DEFAULT FALSE,
      policy JSONB NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- ============================================
    -- 12-13. PROPOSITION (STRUCTURED INDEX)
    -- ============================================

    CREATE TABLE proposition (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      frame_type TEXT NOT NULL,
      subject_handle_id UUID NOT NULL,
      predicate TEXT NOT NULL,
      object_handle_id UUID,
      value JSONB,
      polarity BOOLEAN NOT NULL DEFAULT TRUE,
      modality TEXT,
      valid_range TSTZRANGE,
      normalized_text TEXT NOT NULL,
      qualifiers JSONB NOT NULL DEFAULT '{}'::jsonb,
      semantic_key TEXT NOT NULL,
      system_created TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (id, corpus_id),
      FOREIGN KEY (subject_handle_id, corpus_id) REFERENCES handle(id, corpus_id),
      FOREIGN KEY (object_handle_id, corpus_id) REFERENCES handle(id, corpus_id)
    );

    CREATE TABLE proposition_participant (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      proposition_id UUID NOT NULL,
      handle_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      role TEXT NOT NULL,
      ordinal INT NOT NULL DEFAULT 0,
      UNIQUE (proposition_id, handle_id, role),
      FOREIGN KEY (proposition_id, corpus_id) REFERENCES proposition(id, corpus_id),
      FOREIGN KEY (handle_id, corpus_id) REFERENCES handle(id, corpus_id)
    );

    -- ============================================
    -- 14. AUTHORITY
    -- ============================================

    CREATE TABLE source_policy_eval (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      document_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      policy_version TEXT NOT NULL DEFAULT 'v1',
      evaluator TEXT NOT NULL DEFAULT 'rule_based',
      document_type TEXT,
      formality DOUBLE PRECISION CHECK (formality >= 0 AND formality <= 1),
      attestation_type TEXT,
      publication_context TEXT,
      cross_reference_count INT NOT NULL DEFAULT 0 CHECK (cross_reference_count >= 0),
      provenance_verified BOOLEAN NOT NULL DEFAULT FALSE,
      source_identity TEXT,
      independence_group TEXT,
      authority_score DOUBLE PRECISION NOT NULL CHECK (authority_score >= 0 AND authority_score <= 1),
      evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (id, corpus_id),
      FOREIGN KEY (document_id, corpus_id) REFERENCES document_work(id, corpus_id)
    );

    -- ============================================
    -- 15-16. ATTESTATION
    -- ============================================

    CREATE TABLE attestation (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      span_id UUID,
      proposition_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      source_policy_eval_id UUID,
      stance TEXT NOT NULL CHECK (stance IN ('asserts', 'denies', 'reports', 'questions', 'conditions', 'derived')),
      extraction_method TEXT NOT NULL,
      extraction_confidence DOUBLE PRECISION NOT NULL CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
      attestation_strength TEXT CHECK (attestation_strength IS NULL OR attestation_strength IN (
        'direct_statement', 'allegation', 'inference', 'observation',
        'measurement', 'computation', 'expert_judgment'
      )),
      corroborating_methods JSONB,
      status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'accepted', 'rejected', 'quarantined')),
      system_created TIMESTAMPTZ NOT NULL DEFAULT now(),
      system_invalidated TIMESTAMPTZ,
      UNIQUE (id, corpus_id),
      FOREIGN KEY (span_id, corpus_id) REFERENCES text_span(id, corpus_id),
      FOREIGN KEY (proposition_id, corpus_id) REFERENCES proposition(id, corpus_id),
      FOREIGN KEY (source_policy_eval_id, corpus_id) REFERENCES source_policy_eval(id, corpus_id)
    );

    CREATE TABLE attestation_situation (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      attestation_id UUID NOT NULL,
      situation_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      assignment_confidence DOUBLE PRECISION NOT NULL CHECK (assignment_confidence >= 0 AND assignment_confidence <= 1),
      assignment_basis TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      invalidated_at TIMESTAMPTZ,
      FOREIGN KEY (attestation_id, corpus_id) REFERENCES attestation(id, corpus_id),
      FOREIGN KEY (situation_id, corpus_id) REFERENCES situation(id, corpus_id)
    );

    -- ============================================
    -- 17-18. TRUTH STATE
    -- ============================================

    CREATE TABLE proposition_state (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      proposition_id UUID NOT NULL,
      situation_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      truth_status TEXT NOT NULL CHECK (truth_status IN (
        'accepted', 'denied', 'contested', 'reported', 'unknown', 'retracted', 'superseded'
      )),
      review_status TEXT NOT NULL DEFAULT 'auto_computed' CHECK (review_status IN (
        'auto_computed', 'human_reviewed', 'needs_review', 'overridden'
      )),
      reviewed_by TEXT,
      reviewed_at TIMESTAMPTZ,
      truth_policy_version TEXT NOT NULL DEFAULT 'v1.1',
      effective_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL, '[)'),
      computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      basis_hash TEXT NOT NULL,
      UNIQUE (id, corpus_id),
      FOREIGN KEY (proposition_id, corpus_id) REFERENCES proposition(id, corpus_id),
      FOREIGN KEY (situation_id, corpus_id) REFERENCES situation(id, corpus_id),
      EXCLUDE USING GIST (
        corpus_id WITH =,
        proposition_id WITH =,
        situation_id WITH =,
        effective_range WITH &&
      )
    );

    CREATE TABLE proposition_state_basis (
      state_id UUID NOT NULL,
      attestation_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      role TEXT NOT NULL CHECK (role IN ('supporting', 'contradicting', 'neutral')),
      PRIMARY KEY (state_id, attestation_id),
      FOREIGN KEY (state_id, corpus_id) REFERENCES proposition_state(id, corpus_id) ON DELETE CASCADE,
      FOREIGN KEY (attestation_id, corpus_id) REFERENCES attestation(id, corpus_id)
    );

    -- ============================================
    -- 19-20. LINEAGE
    -- ============================================

    CREATE TABLE derivation_edge (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      parent_proposition_id UUID NOT NULL,
      child_proposition_id UUID NOT NULL,
      derivation_type TEXT NOT NULL,
      derivation_method TEXT NOT NULL,
      confidence DOUBLE PRECISION CHECK (confidence >= 0 AND confidence <= 1),
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK (parent_proposition_id <> child_proposition_id),
      FOREIGN KEY (parent_proposition_id, corpus_id) REFERENCES proposition(id, corpus_id),
      FOREIGN KEY (child_proposition_id, corpus_id) REFERENCES proposition(id, corpus_id)
    );

    CREATE TABLE supersession_edge (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      old_proposition_id UUID NOT NULL,
      new_proposition_id UUID NOT NULL,
      supersession_type TEXT NOT NULL,
      effective_at TIMESTAMPTZ NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      CHECK (old_proposition_id <> new_proposition_id),
      FOREIGN KEY (old_proposition_id, corpus_id) REFERENCES proposition(id, corpus_id),
      FOREIGN KEY (new_proposition_id, corpus_id) REFERENCES proposition(id, corpus_id)
    );

    -- ============================================
    -- 21-22. COMPUTATION
    -- ============================================

    CREATE TABLE computation_spec (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      name TEXT NOT NULL,
      evaluator_type TEXT NOT NULL,
      version INT NOT NULL DEFAULT 1 CHECK (version > 0),
      definition JSONB NOT NULL,
      source_proposition_id UUID,
      reviewed_by TEXT,
      reviewed_at TIMESTAMPTZ,
      status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'approved', 'deprecated')),
      effective_range TSTZRANGE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (id, corpus_id),
      UNIQUE (corpus_id, name, version),
      FOREIGN KEY (source_proposition_id, corpus_id) REFERENCES proposition(id, corpus_id)
    );

    CREATE TABLE computation_run (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      spec_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      spec_version INT NOT NULL CHECK (spec_version > 0),
      as_of TIMESTAMPTZ NOT NULL,
      input_values JSONB NOT NULL,
      result JSONB NOT NULL,
      engine_version TEXT NOT NULL,
      errors JSONB,
      result_proposition_id UUID,
      computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      FOREIGN KEY (spec_id, corpus_id) REFERENCES computation_spec(id, corpus_id),
      FOREIGN KEY (result_proposition_id, corpus_id) REFERENCES proposition(id, corpus_id)
    );

    -- ============================================
    -- 23-24. GAP
    -- ============================================

    CREATE TABLE gap (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      kind TEXT NOT NULL,
      description TEXT NOT NULL,
      severity TEXT NOT NULL DEFAULT 'moderate' CHECK (severity IN ('critical', 'moderate', 'minor')),
      status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
      detected_by TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      resolved_at TIMESTAMPTZ,
      UNIQUE (id, corpus_id)
    );

    CREATE TABLE gap_target (
      gap_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      target_type TEXT NOT NULL CHECK (target_type IN ('proposition', 'handle')),
      target_id UUID NOT NULL,
      PRIMARY KEY (gap_id, target_type, target_id),
      FOREIGN KEY (gap_id, corpus_id) REFERENCES gap(id, corpus_id) ON DELETE CASCADE
    );

    -- ============================================
    -- 25-26. REVIEW
    -- ============================================

    CREATE TABLE changeset (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      actor TEXT NOT NULL,
      actor_type TEXT NOT NULL CHECK (actor_type IN ('human', 'ai_agent', 'system')),
      description TEXT,
      status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN (
        'proposed', 'auto_applied', 'approved', 'rejected',
        'applied', 'rolled_back', 'failed', 'rollback_failed'
      )),
      risk_level TEXT NOT NULL DEFAULT 'low' CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
      blast_radius JSONB,
      reviewed_by TEXT,
      reviewed_at TIMESTAMPTZ,
      review_reason TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      applied_at TIMESTAMPTZ,
      rolled_back_at TIMESTAMPTZ,
      UNIQUE (id, corpus_id)
    );

    CREATE TABLE changeset_operation (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      changeset_id UUID NOT NULL,
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      ordinal INT NOT NULL,
      operation_type TEXT NOT NULL,
      payload JSONB NOT NULL,
      result JSONB,
      executed_at TIMESTAMPTZ,
      UNIQUE (changeset_id, ordinal),
      FOREIGN KEY (changeset_id, corpus_id) REFERENCES changeset(id, corpus_id) ON DELETE CASCADE
    );

    -- ============================================
    -- 27. AUDIT
    -- ============================================

    CREATE TABLE activity (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      corpus_id UUID NOT NULL REFERENCES corpus(id),
      event_type TEXT NOT NULL,
      entity_type TEXT,
      entity_id UUID,
      details JSONB NOT NULL DEFAULT '{}'::jsonb,
      actor TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- ============================================
    -- TRIGGERS
    -- ============================================

    CREATE OR REPLACE FUNCTION check_derivation_acyclicity()
    RETURNS TRIGGER AS $$
    BEGIN
      IF EXISTS (
        WITH RECURSIVE ancestors AS (
          SELECT parent_proposition_id AS ancestor_id
          FROM derivation_edge
          WHERE child_proposition_id = NEW.parent_proposition_id
            AND corpus_id = NEW.corpus_id
          UNION
          SELECT de.parent_proposition_id
          FROM derivation_edge de
          JOIN ancestors a ON de.child_proposition_id = a.ancestor_id
          WHERE de.corpus_id = NEW.corpus_id
        )
        SELECT 1 FROM ancestors WHERE ancestor_id = NEW.child_proposition_id
      ) THEN
        RAISE EXCEPTION 'derivation_edge would create cycle: % -> %',
          NEW.parent_proposition_id, NEW.child_proposition_id;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_derivation_acyclicity
      BEFORE INSERT OR UPDATE OF parent_proposition_id, child_proposition_id, corpus_id
      ON derivation_edge
      FOR EACH ROW EXECUTE FUNCTION check_derivation_acyclicity();

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

    CREATE TRIGGER trg_gap_target_fk
      BEFORE INSERT OR UPDATE ON gap_target
      FOR EACH ROW EXECUTE FUNCTION check_gap_target_exists();

    -- ============================================
    -- INDEXES
    -- ============================================

    -- Attestation situation: one active assignment per pair
    CREATE UNIQUE INDEX idx_att_sit_active ON attestation_situation(attestation_id, situation_id)
      WHERE invalidated_at IS NULL;

    -- Evidence
    CREATE INDEX idx_dw_corpus ON document_work(corpus_id);
    CREATE INDEX idx_de_doc ON document_expression(document_id);
    CREATE INDEX idx_sn_expr ON structure_node(expression_id);
    CREATE INDEX idx_sn_parent ON structure_node(parent_id) WHERE parent_id IS NOT NULL;
    CREATE INDEX idx_ts_expr ON text_span(expression_id);
    CREATE INDEX idx_ts_node ON text_span(node_id);
    CREATE INDEX idx_ch_expr ON chunk(expression_id);
    CREATE INDEX idx_ce_chunk ON chunk_embedding(chunk_id);

    -- Entity
    CREATE INDEX idx_handle_corpus_kind ON handle(corpus_id, kind);
    CREATE INDEX idx_handle_name ON handle(corpus_id, canonical_name);
    CREATE INDEX idx_id_handles ON identity_decision(handle_a_id, handle_b_id);

    -- Context
    CREATE INDEX idx_sit_corpus ON situation(corpus_id);
    CREATE INDEX idx_qv_corpus ON query_view(corpus_id);
    CREATE UNIQUE INDEX idx_qv_default ON query_view(corpus_id) WHERE is_default = TRUE;

    -- Proposition
    CREATE INDEX idx_prop_corpus ON proposition(corpus_id);
    CREATE INDEX idx_prop_subject_pred ON proposition(subject_handle_id, predicate);
    CREATE INDEX idx_prop_object ON proposition(object_handle_id) WHERE object_handle_id IS NOT NULL;
    CREATE INDEX idx_prop_frame ON proposition(corpus_id, frame_type);
    CREATE INDEX idx_prop_valid ON proposition USING GIST (valid_range);
    CREATE UNIQUE INDEX idx_prop_semkey ON proposition(corpus_id, semantic_key);
    CREATE INDEX idx_prop_value ON proposition USING GIN (value) WHERE value IS NOT NULL;
    CREATE INDEX idx_prop_qual ON proposition USING GIN (qualifiers) WHERE qualifiers <> '{}'::jsonb;
    CREATE INDEX idx_pp_prop ON proposition_participant(proposition_id);
    CREATE INDEX idx_pp_handle ON proposition_participant(handle_id);

    -- Authority
    CREATE INDEX idx_spe_document ON source_policy_eval(document_id);
    CREATE INDEX idx_spe_corpus ON source_policy_eval(corpus_id);

    -- Attestation
    CREATE INDEX idx_att_prop ON attestation(proposition_id);
    CREATE INDEX idx_att_span ON attestation(span_id);
    CREATE INDEX idx_att_accepted ON attestation(proposition_id) WHERE status = 'accepted';
    CREATE INDEX idx_att_candidates ON attestation(corpus_id) WHERE status = 'candidate';
    CREATE INDEX idx_att_source ON attestation(source_policy_eval_id);
    CREATE INDEX idx_att_truth ON attestation(proposition_id, status, corpus_id)
      WHERE status = 'accepted' AND system_invalidated IS NULL;
    CREATE INDEX idx_as_att ON attestation_situation(attestation_id);
    CREATE INDEX idx_as_sit ON attestation_situation(situation_id);
    CREATE INDEX idx_as_active ON attestation_situation(attestation_id, situation_id)
      WHERE invalidated_at IS NULL;

    -- Truth
    CREATE INDEX idx_ps_current ON proposition_state(proposition_id, situation_id)
      WHERE upper(effective_range) IS NULL;
    CREATE INDEX idx_psb_state ON proposition_state_basis(state_id);
    CREATE INDEX idx_psb_att ON proposition_state_basis(attestation_id);

    -- Lineage
    CREATE INDEX idx_de_parent ON derivation_edge(parent_proposition_id);
    CREATE INDEX idx_de_child ON derivation_edge(child_proposition_id);
    CREATE INDEX idx_se_old ON supersession_edge(old_proposition_id);
    CREATE INDEX idx_se_new ON supersession_edge(new_proposition_id);
    CREATE INDEX idx_se_old_corpus_effective ON supersession_edge(old_proposition_id, corpus_id, effective_at);

    -- Computation
    CREATE INDEX idx_cs_corpus ON computation_spec(corpus_id);
    CREATE INDEX idx_cr_spec ON computation_run(spec_id);

    -- Gap
    CREATE INDEX idx_gap_corpus ON gap(corpus_id);
    CREATE INDEX idx_gt_gap ON gap_target(gap_id);
    CREATE INDEX idx_gt_target ON gap_target(target_type, target_id);

    -- Review
    CREATE INDEX idx_changeset_corpus_status ON changeset(corpus_id, status);
    CREATE INDEX idx_co_cs ON changeset_operation(changeset_id);

    -- Activity
    CREATE INDEX idx_act_corpus ON activity(corpus_id, created_at DESC);
    CREATE INDEX idx_act_entity ON activity(entity_type, entity_id);
    """)


def downgrade() -> None:
    op.execute("""
    DROP TRIGGER IF EXISTS trg_gap_target_fk ON gap_target;
    DROP TRIGGER IF EXISTS trg_derivation_acyclicity ON derivation_edge;
    DROP FUNCTION IF EXISTS check_gap_target_exists() CASCADE;
    DROP FUNCTION IF EXISTS check_derivation_acyclicity() CASCADE;
    DROP TABLE IF EXISTS activity CASCADE;
    DROP TABLE IF EXISTS changeset_operation CASCADE;
    DROP TABLE IF EXISTS changeset CASCADE;
    DROP TABLE IF EXISTS gap_target CASCADE;
    DROP TABLE IF EXISTS gap CASCADE;
    DROP TABLE IF EXISTS computation_run CASCADE;
    DROP TABLE IF EXISTS computation_spec CASCADE;
    DROP TABLE IF EXISTS supersession_edge CASCADE;
    DROP TABLE IF EXISTS derivation_edge CASCADE;
    DROP TABLE IF EXISTS proposition_state_basis CASCADE;
    DROP TABLE IF EXISTS proposition_state CASCADE;
    DROP TABLE IF EXISTS attestation_situation CASCADE;
    DROP TABLE IF EXISTS attestation CASCADE;
    DROP TABLE IF EXISTS source_policy_eval CASCADE;
    DROP TABLE IF EXISTS proposition_participant CASCADE;
    DROP TABLE IF EXISTS proposition CASCADE;
    DROP TABLE IF EXISTS query_view CASCADE;
    DROP TABLE IF EXISTS situation CASCADE;
    DROP TABLE IF EXISTS identity_decision CASCADE;
    DROP TABLE IF EXISTS handle CASCADE;
    DROP TABLE IF EXISTS chunk_embedding CASCADE;
    DROP TABLE IF EXISTS chunk CASCADE;
    DROP TABLE IF EXISTS text_span CASCADE;
    DROP TABLE IF EXISTS structure_node CASCADE;
    DROP TABLE IF EXISTS document_expression CASCADE;
    DROP TABLE IF EXISTS document_work CASCADE;
    DROP TABLE IF EXISTS corpus CASCADE;
    """)
