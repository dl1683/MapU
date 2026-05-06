"""Integration tests that seed golden fixtures through repositories and validate truth computation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.models.attestation import Attestation, AttestationSituation
from mapu.models.authority import SourcePolicyEval
from mapu.models.context import Situation
from mapu.models.corpus import Corpus
from mapu.models.entity import Handle
from mapu.models.evidence import DocumentExpression, DocumentWork, TextSpan
from mapu.models.lineage import SupersessionEdge
from mapu.models.proposition import Proposition
from mapu.repos.attestation import AttestationRepo
from mapu.repos.lineage import SupersessionEdgeRepo
from mapu.truth.policy import (
    EvidenceRecord,
    TruthPolicyConfig,
    TruthPolicyV1,
)
from mapu.types import Stance
from tests.fixtures.golden_examples import ALL_EXAMPLES, GoldenExample

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


class SeededExample:
    """Holds the DB entities created from a GoldenExample."""

    def __init__(self) -> None:
        self.corpus_id: uuid.UUID = uuid.UUID(int=0)
        self.handles: list[Handle] = []
        self.propositions: list[Proposition] = []
        self.situations: list[Situation] = []
        self.attestations: list[Attestation] = []
        self.supersession_edges: list[SupersessionEdge] = []


async def seed_golden_example(
    session: AsyncSession,
    corpus: Corpus,
    example: GoldenExample,
) -> SeededExample:
    """Seed a golden example through ORM models (not raw SQL)."""
    seeded = SeededExample()
    seeded.corpus_id = corpus.id

    doc = DocumentWork(
        id=uuid.uuid4(),
        corpus_id=corpus.id,
        mime_type="text/plain",
        source_uri=f"golden://{example.code}",
        ingested_at=NOW,
    )
    session.add(doc)
    await session.flush()

    expr = DocumentExpression(
        id=uuid.uuid4(),
        document_id=doc.id,
        corpus_id=corpus.id,
        parser_version="golden_v1",
        created_at=NOW,
    )
    session.add(expr)
    await session.flush()

    span = TextSpan(
        id=uuid.uuid4(),
        expression_id=expr.id,
        corpus_id=corpus.id,
        text=example.description,
        start_char=0,
        end_char=len(example.description),
    )
    session.add(span)
    await session.flush()

    for hf in example.handles:
        h = Handle(
            id=hf.id,
            corpus_id=corpus.id,
            canonical_name=hf.canonical_name,
            kind=hf.kind,
            created_at=NOW,
        )
        session.add(h)
        seeded.handles.append(h)
    await session.flush()

    for pf in example.propositions:
        subject_handle = seeded.handles[0] if seeded.handles else None
        p = Proposition(
            id=pf.id,
            corpus_id=corpus.id,
            frame_type=pf.frame_type,
            subject_handle_id=subject_handle.id if subject_handle else uuid.uuid4(),
            predicate=pf.predicate,
            object_handle_id=pf.object.id if pf.object else None,
            value=pf.value,
            polarity=pf.polarity,
            modality=pf.modality,
            normalized_text=pf.normalized_text,
            qualifiers=pf.qualifiers,
            semantic_key=pf.semantic_key,
            system_created=NOW,
        )
        session.add(p)
        seeded.propositions.append(p)
    await session.flush()

    for sf in example.situations:
        s = Situation(
            id=sf.id,
            corpus_id=corpus.id,
            kind=sf.kind,
            name=sf.name,
            created_at=NOW,
        )
        session.add(s)
        seeded.situations.append(s)
    await session.flush()

    for af in example.attestations:
        prop = seeded.propositions[af.proposition_idx]

        spe = SourcePolicyEval(
            id=uuid.uuid4(),
            document_id=doc.id,
            corpus_id=corpus.id,
            authority_score=af.authority_score,
            document_type=af.document_type,
            publication_context=af.publication_context,
            attestation_type=af.attestation_type,
            independence_group=af.independence_group,
            evaluated_at=NOW,
        )
        session.add(spe)
        await session.flush()

        att = Attestation(
            id=af.id,
            span_id=span.id,
            proposition_id=prop.id,
            corpus_id=corpus.id,
            source_policy_eval_id=spe.id,
            stance=af.stance,
            extraction_method=af.extraction_method,
            extraction_confidence=af.extraction_confidence,
            attestation_strength=af.attestation_strength,
            status=af.status,
            system_created=NOW,
        )
        session.add(att)
        seeded.attestations.append(att)
    await session.flush()

    situation_for_att = seeded.situations[0] if seeded.situations else None
    for i, att in enumerate(seeded.attestations):
        af = example.attestations[i]
        sit = situation_for_att
        if len(seeded.situations) > 1 and len(example.expected_truth) > 0:
            for et in example.expected_truth:
                if et.proposition_idx == af.proposition_idx:
                    sit = seeded.situations[et.situation_idx]
                    break

        if sit:
            att_sit = AttestationSituation(
                id=uuid.uuid4(),
                attestation_id=att.id,
                situation_id=sit.id,
                corpus_id=corpus.id,
                assignment_confidence=1.0,
                assignment_basis="golden_fixture",
                created_at=NOW,
            )
            session.add(att_sit)
    await session.flush()

    for sf in example.supersessions:
        old_prop = seeded.propositions[sf.old_proposition_idx]
        new_prop = seeded.propositions[sf.new_proposition_idx]
        edge = SupersessionEdge(
            corpus_id=corpus.id,
            old_proposition_id=old_prop.id,
            new_proposition_id=new_prop.id,
            supersession_type=sf.supersession_type,
            effective_at=datetime.fromisoformat(sf.effective_at.replace("Z", "+00:00")),
            created_at=NOW,
        )
        session.add(edge)
        seeded.supersession_edges.append(edge)
    await session.flush()

    return seeded


class DbTruthEvidenceProvider:
    """TruthEvidenceProvider backed by real DB queries through repos."""

    def __init__(self, session: AsyncSession, corpus_id: uuid.UUID) -> None:
        self._att_repo = AttestationRepo(session, corpus_id)
        self._sup_repo = SupersessionEdgeRepo(session, corpus_id)
        self._session = session
        self._corpus_id = corpus_id

    async def accepted_attestations(
        self, proposition_id: uuid.UUID, situation_id: uuid.UUID
    ) -> list[EvidenceRecord]:
        atts = await self._att_repo.accepted_for_truth(proposition_id, situation_id)
        records = []
        for att in atts:
            spe = await self._session.get(SourcePolicyEval, att.source_policy_eval_id)
            records.append(
                EvidenceRecord(
                    attestation_id=att.id,
                    stance=Stance(att.stance),
                    extraction_confidence=att.extraction_confidence,
                    attestation_strength=att.attestation_strength,
                    authority_score=spe.authority_score if spe else 0.0,
                    attestation_type=spe.attestation_type if spe else None,
                    document_type=spe.document_type if spe else None,
                    publication_context=spe.publication_context if spe else None,
                    independence_group=spe.independence_group if spe else None,
                )
            )
        return records

    async def is_retracted(self, proposition_id: uuid.UUID) -> bool:
        return await self._sup_repo.is_retracted(proposition_id)

    async def is_superseded(self, proposition_id: uuid.UUID) -> bool:
        return await self._sup_repo.is_superseded(proposition_id)


SIMPLE_EXAMPLES = [
    ex for ex in ALL_EXAMPLES
    if not ex.supersessions and len(ex.situations) <= 1
]

SUPERSESSION_EXAMPLES = [
    ex for ex in ALL_EXAMPLES if ex.supersessions
]

MULTI_SITUATION_EXAMPLES = [
    ex for ex in ALL_EXAMPLES
    if len(ex.situations) > 1 and not ex.supersessions
]


class TestGoldenSimple:
    """Test golden examples without supersession or multi-situation complexity."""

    @pytest.mark.parametrize("example", SIMPLE_EXAMPLES, ids=[e.code for e in SIMPLE_EXAMPLES])
    async def test_truth_computation(
        self, session: AsyncSession, corpus_a: Corpus, example: GoldenExample
    ) -> None:
        seeded = await seed_golden_example(session, corpus_a, example)
        provider = DbTruthEvidenceProvider(session, corpus_a.id)
        policy = TruthPolicyV1(TruthPolicyConfig())

        for et in example.expected_truth:
            prop = seeded.propositions[et.proposition_idx]
            sit = seeded.situations[et.situation_idx]
            result = await policy.compute(prop.id, sit.id, provider)
            assert result.status.value == et.expected_status, (
                f"{example.code}: prop[{et.proposition_idx}] expected "
                f"{et.expected_status}, got {result.status.value} (reason: {result.reason})"
            )


class TestGoldenSupersession:
    """Test golden examples that involve supersession/retraction edges."""

    @pytest.mark.parametrize(
        "example", SUPERSESSION_EXAMPLES, ids=[e.code for e in SUPERSESSION_EXAMPLES]
    )
    async def test_truth_with_supersession(
        self, session: AsyncSession, corpus_a: Corpus, example: GoldenExample
    ) -> None:
        seeded = await seed_golden_example(session, corpus_a, example)
        provider = DbTruthEvidenceProvider(session, corpus_a.id)
        policy = TruthPolicyV1(TruthPolicyConfig())

        for et in example.expected_truth:
            prop = seeded.propositions[et.proposition_idx]
            sit = seeded.situations[et.situation_idx]
            result = await policy.compute(prop.id, sit.id, provider)
            assert result.status.value == et.expected_status, (
                f"{example.code}: prop[{et.proposition_idx}] expected "
                f"{et.expected_status}, got {result.status.value} (reason: {result.reason})"
            )


class TestGoldenMultiSituation:
    """Test golden examples with multiple situations (F2, F3)."""

    @pytest.mark.parametrize(
        "example", MULTI_SITUATION_EXAMPLES, ids=[e.code for e in MULTI_SITUATION_EXAMPLES]
    )
    async def test_truth_per_situation(
        self, session: AsyncSession, corpus_a: Corpus, example: GoldenExample
    ) -> None:
        seeded = await seed_golden_example(session, corpus_a, example)
        provider = DbTruthEvidenceProvider(session, corpus_a.id)
        policy = TruthPolicyV1(TruthPolicyConfig())

        for et in example.expected_truth:
            prop = seeded.propositions[et.proposition_idx]
            sit = seeded.situations[et.situation_idx]
            result = await policy.compute(prop.id, sit.id, provider)
            assert result.status.value == et.expected_status, (
                f"{example.code}: prop[{et.proposition_idx}] sit[{et.situation_idx}] expected "
                f"{et.expected_status}, got {result.status.value} (reason: {result.reason})"
            )
