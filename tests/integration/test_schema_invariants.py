"""Integration tests for schema invariants enforced by the database.

Tests corpus isolation via composite FKs, DAG acyclicity trigger,
gap_target polymorphic FK trigger, semantic key uniqueness, and
proposition_state temporal constraints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.attestation import Attestation
from mapu.models.audit import Activity
from mapu.models.authority import SourcePolicyEval
from mapu.models.context import Situation
from mapu.models.corpus import Corpus
from mapu.models.entity import Handle
from mapu.models.evidence import Chunk, DocumentExpression, DocumentWork, TextSpan
from mapu.models.gap import Gap, GapTarget
from mapu.models.lineage import DerivationEdge, SupersessionEdge
from mapu.models.proposition import Proposition
from mapu.models.review import Changeset

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


def _make_doc_work(corpus_id: uuid.UUID) -> DocumentWork:
    return DocumentWork(
        id=uuid.uuid4(),
        corpus_id=corpus_id,
        mime_type="text/plain",
        ingested_at=NOW,
    )


def _make_expression(corpus_id: uuid.UUID, document_id: uuid.UUID) -> DocumentExpression:
    return DocumentExpression(
        id=uuid.uuid4(),
        document_id=document_id,
        corpus_id=corpus_id,
        parser_version="v1",
        created_at=NOW,
    )


def _make_span(corpus_id: uuid.UUID, expression_id: uuid.UUID) -> TextSpan:
    return TextSpan(
        id=uuid.uuid4(),
        expression_id=expression_id,
        corpus_id=corpus_id,
        text="test span",
        start_char=0,
        end_char=9,
    )


def _make_source_policy_eval(
    corpus_id: uuid.UUID,
    document_id: uuid.UUID,
    authority_score: float = 0.8,
    document_type: str | None = None,
    publication_context: str | None = None,
    attestation_type: str | None = None,
    independence_group: str | None = None,
) -> SourcePolicyEval:
    return SourcePolicyEval(
        id=uuid.uuid4(),
        document_id=document_id,
        corpus_id=corpus_id,
        authority_score=authority_score,
        document_type=document_type,
        publication_context=publication_context,
        attestation_type=attestation_type,
        independence_group=independence_group,
        evaluated_at=NOW,
    )


def _make_handle(corpus_id: uuid.UUID, name: str = "test", kind: str = "entity") -> Handle:
    return Handle(
        id=uuid.uuid4(),
        corpus_id=corpus_id,
        canonical_name=name,
        kind=kind,
        created_at=NOW,
    )


def _make_proposition(
    corpus_id: uuid.UUID,
    subject_handle_id: uuid.UUID,
    semantic_key: str = "test:key",
    frame_type: str = "finding",
) -> Proposition:
    return Proposition(
        id=uuid.uuid4(),
        corpus_id=corpus_id,
        frame_type=frame_type,
        subject_handle_id=subject_handle_id,
        predicate="test_predicate",
        normalized_text="test proposition",
        semantic_key=semantic_key,
        system_created=NOW,
    )


def _make_situation(corpus_id: uuid.UUID, name: str = "test") -> Situation:
    return Situation(
        id=uuid.uuid4(),
        corpus_id=corpus_id,
        kind="test",
        name=name,
        created_at=NOW,
    )


# ============================================================
# Migration smoke test
# ============================================================


class TestMigrationSchema:
    async def test_all_27_tables_exist(self, session: AsyncSession) -> None:
        result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        tables = {row[0] for row in result}
        expected = {
            "corpus",
            "document_work",
            "document_expression",
            "structure_node",
            "text_span",
            "chunk",
            "chunk_embedding",
            "handle",
            "identity_decision",
            "situation",
            "query_view",
            "proposition",
            "proposition_participant",
            "source_policy_eval",
            "attestation",
            "attestation_situation",
            "proposition_state",
            "proposition_state_basis",
            "derivation_edge",
            "supersession_edge",
            "computation_spec",
            "computation_run",
            "gap",
            "gap_target",
            "changeset",
            "changeset_operation",
            "activity",
        }
        missing = expected - tables
        assert not missing, f"Missing tables: {missing}"

    async def test_extensions_enabled(self, session: AsyncSession) -> None:
        result = await session.execute(
            text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pgcrypto', 'uuid-ossp', 'btree_gist')")
        )
        extensions = {row[0] for row in result}
        assert "vector" in extensions
        assert "btree_gist" in extensions


# ============================================================
# Corpus isolation (composite FK enforcement)
# ============================================================


class TestCorpusIsolation:
    async def test_handle_in_correct_corpus(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id)
        session.add(h)
        await session.flush()
        assert h.id is not None

    async def test_proposition_cross_corpus_handle_rejected(
        self, session: AsyncSession, corpus_a: Corpus, corpus_b: Corpus
    ) -> None:
        """A proposition in corpus_a referencing a handle in corpus_b should fail
        due to composite FK (subject_handle_id, corpus_id) -> handle(id, corpus_id)."""
        h = _make_handle(corpus_b.id)
        session.add(h)
        await session.flush()

        p = _make_proposition(corpus_a.id, h.id, semantic_key="cross_corpus:test")
        session.add(p)
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_attestation_cross_corpus_proposition_rejected(
        self, session: AsyncSession, corpus_a: Corpus, corpus_b: Corpus
    ) -> None:
        """Attestation in corpus_a referencing a proposition in corpus_b fails."""
        h_a = _make_handle(corpus_a.id, name="handle_a")
        h_b = _make_handle(corpus_b.id, name="handle_b")
        session.add_all([h_a, h_b])
        await session.flush()

        p_b = _make_proposition(corpus_b.id, h_b.id, semantic_key="corpus_b:prop")
        session.add(p_b)
        await session.flush()

        doc = _make_doc_work(corpus_a.id)
        session.add(doc)
        await session.flush()

        expr = _make_expression(corpus_a.id, doc.id)
        session.add(expr)
        await session.flush()

        span = _make_span(corpus_a.id, expr.id)
        session.add(span)
        await session.flush()

        spe = _make_source_policy_eval(corpus_a.id, doc.id)
        session.add(spe)
        await session.flush()

        att = Attestation(
            id=uuid.uuid4(),
            span_id=span.id,
            proposition_id=p_b.id,
            corpus_id=corpus_a.id,
            source_policy_eval_id=spe.id,
            stance="asserts",
            extraction_method="test",
            extraction_confidence=0.9,
            status="accepted",
            system_created=NOW,
        )
        session.add(att)
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_same_semantic_key_different_corpora_ok(
        self, session: AsyncSession, corpus_a: Corpus, corpus_b: Corpus
    ) -> None:
        h_a = _make_handle(corpus_a.id, name="h_dup_a")
        h_b = _make_handle(corpus_b.id, name="h_dup_b")
        session.add_all([h_a, h_b])
        await session.flush()

        p_a = _make_proposition(corpus_a.id, h_a.id, semantic_key="shared:key")
        p_b = _make_proposition(corpus_b.id, h_b.id, semantic_key="shared:key")
        session.add_all([p_a, p_b])
        await session.flush()
        assert p_a.id != p_b.id

    async def test_duplicate_semantic_key_same_corpus_rejected(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="h_dup_same")
        session.add(h)
        await session.flush()

        p1 = _make_proposition(corpus_a.id, h.id, semantic_key="dup:same_corpus")
        session.add(p1)
        await session.flush()

        p2 = _make_proposition(corpus_a.id, h.id, semantic_key="dup:same_corpus")
        session.add(p2)
        with pytest.raises(IntegrityError):
            await session.flush()


# ============================================================
# DAG acyclicity trigger
# ============================================================


class TestDAGAcyclicity:
    async def test_simple_derivation_ok(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="dag_h")
        session.add(h)
        await session.flush()

        p1 = _make_proposition(corpus_a.id, h.id, semantic_key="dag:p1")
        p2 = _make_proposition(corpus_a.id, h.id, semantic_key="dag:p2")
        session.add_all([p1, p2])
        await session.flush()

        edge = DerivationEdge(
            corpus_id=corpus_a.id,
            parent_proposition_id=p1.id,
            child_proposition_id=p2.id,
            derivation_type="inference",
            derivation_method="test",
            created_at=NOW,
        )
        session.add(edge)
        await session.flush()
        assert edge.id is not None

    async def test_self_loop_rejected(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="dag_self")
        session.add(h)
        await session.flush()

        p = _make_proposition(corpus_a.id, h.id, semantic_key="dag:self")
        session.add(p)
        await session.flush()

        edge = DerivationEdge(
            corpus_id=corpus_a.id,
            parent_proposition_id=p.id,
            child_proposition_id=p.id,
            derivation_type="inference",
            derivation_method="test",
            created_at=NOW,
        )
        session.add(edge)
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_two_node_cycle_rejected(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="dag_cycle")
        session.add(h)
        await session.flush()

        p1 = _make_proposition(corpus_a.id, h.id, semantic_key="dag:cycle1")
        p2 = _make_proposition(corpus_a.id, h.id, semantic_key="dag:cycle2")
        session.add_all([p1, p2])
        await session.flush()

        edge1 = DerivationEdge(
            corpus_id=corpus_a.id,
            parent_proposition_id=p1.id,
            child_proposition_id=p2.id,
            derivation_type="inference",
            derivation_method="test",
            created_at=NOW,
        )
        session.add(edge1)
        await session.flush()

        edge2 = DerivationEdge(
            corpus_id=corpus_a.id,
            parent_proposition_id=p2.id,
            child_proposition_id=p1.id,
            derivation_type="inference",
            derivation_method="test",
            created_at=NOW,
        )
        session.add(edge2)
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_three_node_cycle_rejected(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="dag_3cycle")
        session.add(h)
        await session.flush()

        p1 = _make_proposition(corpus_a.id, h.id, semantic_key="dag:3c1")
        p2 = _make_proposition(corpus_a.id, h.id, semantic_key="dag:3c2")
        p3 = _make_proposition(corpus_a.id, h.id, semantic_key="dag:3c3")
        session.add_all([p1, p2, p3])
        await session.flush()

        for parent, child in [(p1, p2), (p2, p3)]:
            edge = DerivationEdge(
                corpus_id=corpus_a.id,
                parent_proposition_id=parent.id,
                child_proposition_id=child.id,
                derivation_type="inference",
                derivation_method="test",
                created_at=NOW,
            )
            session.add(edge)
        await session.flush()

        closing_edge = DerivationEdge(
            corpus_id=corpus_a.id,
            parent_proposition_id=p3.id,
            child_proposition_id=p1.id,
            derivation_type="inference",
            derivation_method="test",
            created_at=NOW,
        )
        session.add(closing_edge)
        with pytest.raises(IntegrityError):
            await session.flush()


# ============================================================
# gap_target polymorphic FK trigger
# ============================================================


class TestGapTargetTrigger:
    async def test_gap_continuity_contract_fields_persist(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        gap = Gap(
            id=uuid.uuid4(),
            corpus_id=corpus_a.id,
            kind="query_gap",
            description="Need source-backed evidence before resume",
            severity="critical",
            detected_by="test",
            uncertainty_reason="missing_evidence",
            evidence_hypothesis={
                "source": "query",
                "question": "Where is the source?",
            },
            next_action={
                "action_type": "investigate",
                "question": "Find source-backed evidence",
            },
            expected_resolution="Close with provenance or dismiss explicitly.",
            governance_tier="provisional",
            priority_score=4.0,
            last_evaluated_at=NOW,
            created_at=NOW,
        )
        session.add(gap)
        await session.flush()

        loaded = await session.get(Gap, gap.id)
        assert loaded is not None
        assert loaded.uncertainty_reason == "missing_evidence"
        assert loaded.evidence_hypothesis["source"] == "query"
        assert loaded.next_action["action_type"] == "investigate"
        assert loaded.expected_resolution == "Close with provenance or dismiss explicitly."
        assert loaded.governance_tier == "provisional"
        assert loaded.priority_score == 4.0

    async def test_gap_target_proposition_ok(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="gap_h")
        session.add(h)
        await session.flush()

        p = _make_proposition(corpus_a.id, h.id, semantic_key="gap:p")
        session.add(p)
        await session.flush()

        gap = Gap(
            id=uuid.uuid4(),
            corpus_id=corpus_a.id,
            kind="missing_evidence",
            description="test gap",
            detected_by="test",
            created_at=NOW,
        )
        session.add(gap)
        await session.flush()

        gt = GapTarget(
            gap_id=gap.id,
            corpus_id=corpus_a.id,
            target_type="proposition",
            target_id=p.id,
        )
        session.add(gt)
        await session.flush()

    async def test_gap_target_handle_ok(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="gap_handle_target")
        session.add(h)
        await session.flush()

        gap = Gap(
            id=uuid.uuid4(),
            corpus_id=corpus_a.id,
            kind="identity_ambiguity",
            description="test handle gap",
            detected_by="test",
            created_at=NOW,
        )
        session.add(gap)
        await session.flush()

        gt = GapTarget(
            gap_id=gap.id,
            corpus_id=corpus_a.id,
            target_type="handle",
            target_id=h.id,
        )
        session.add(gt)
        await session.flush()

    async def test_gap_target_rich_continuity_targets_ok(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        doc = _make_doc_work(corpus_a.id)
        session.add(doc)
        await session.flush()

        expr = _make_expression(corpus_a.id, doc.id)
        session.add(expr)
        await session.flush()

        span = _make_span(corpus_a.id, expr.id)
        session.add(span)
        await session.flush()

        chunk = Chunk(
            id=uuid.uuid4(),
            expression_id=expr.id,
            corpus_id=corpus_a.id,
            text="chunk text",
            start_span_id=span.id,
            end_span_id=span.id,
            token_count=2,
        )
        activity = Activity(
            id=uuid.uuid4(),
            corpus_id=corpus_a.id,
            event_type="query",
            entity_type="query",
            entity_id=None,
            details={"question": "q"},
            actor="test",
            created_at=NOW,
        )
        changeset = Changeset(
            id=uuid.uuid4(),
            corpus_id=corpus_a.id,
            actor="test",
            actor_type="human",
            description="test",
            status="proposed",
            risk_level="low",
            created_at=NOW,
        )
        session.add_all([chunk, activity, changeset])
        await session.flush()

        gap = Gap(
            id=uuid.uuid4(),
            corpus_id=corpus_a.id,
            kind="missing_evidence",
            description="rich target gap",
            detected_by="test",
            created_at=NOW,
        )
        session.add(gap)
        await session.flush()

        targets = [
            ("document", doc.id),
            ("span", span.id),
            ("chunk", chunk.id),
            ("activity", activity.id),
            ("changeset", changeset.id),
        ]
        for target_type, target_id in targets:
            session.add(GapTarget(
                gap_id=gap.id,
                corpus_id=corpus_a.id,
                target_type=target_type,
                target_id=target_id,
            ))
        await session.flush()

    async def test_gap_target_nonexistent_rejected(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        gap = Gap(
            id=uuid.uuid4(),
            corpus_id=corpus_a.id,
            kind="missing_evidence",
            description="test gap bad target",
            detected_by="test",
            created_at=NOW,
        )
        session.add(gap)
        await session.flush()

        gt = GapTarget(
            gap_id=gap.id,
            corpus_id=corpus_a.id,
            target_type="proposition",
            target_id=uuid.uuid4(),
        )
        session.add(gt)
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_gap_target_wrong_corpus_rejected(
        self, session: AsyncSession, corpus_a: Corpus, corpus_b: Corpus
    ) -> None:
        """Target exists in corpus_b but gap is in corpus_a."""
        h = _make_handle(corpus_b.id, name="gap_wrong_corpus_h")
        session.add(h)
        await session.flush()

        gap = Gap(
            id=uuid.uuid4(),
            corpus_id=corpus_a.id,
            kind="missing_evidence",
            description="cross corpus gap",
            detected_by="test",
            created_at=NOW,
        )
        session.add(gap)
        await session.flush()

        gt = GapTarget(
            gap_id=gap.id,
            corpus_id=corpus_a.id,
            target_type="handle",
            target_id=h.id,
        )
        session.add(gt)
        with pytest.raises(IntegrityError):
            await session.flush()


# ============================================================
# Supersession edge constraints
# ============================================================


class TestSupersessionEdge:
    async def test_supersession_ok(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="sup_h")
        session.add(h)
        await session.flush()

        p1 = _make_proposition(corpus_a.id, h.id, semantic_key="sup:old")
        p2 = _make_proposition(corpus_a.id, h.id, semantic_key="sup:new")
        session.add_all([p1, p2])
        await session.flush()

        edge = SupersessionEdge(
            corpus_id=corpus_a.id,
            old_proposition_id=p1.id,
            new_proposition_id=p2.id,
            supersession_type="amendment",
            effective_at=NOW,
            created_at=NOW,
        )
        session.add(edge)
        await session.flush()
        assert edge.id is not None

    async def test_self_supersession_rejected(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        h = _make_handle(corpus_a.id, name="sup_self")
        session.add(h)
        await session.flush()

        p = _make_proposition(corpus_a.id, h.id, semantic_key="sup:self")
        session.add(p)
        await session.flush()

        edge = SupersessionEdge(
            corpus_id=corpus_a.id,
            old_proposition_id=p.id,
            new_proposition_id=p.id,
            supersession_type="retraction",
            effective_at=NOW,
            created_at=NOW,
        )
        session.add(edge)
        with pytest.raises(IntegrityError):
            await session.flush()
