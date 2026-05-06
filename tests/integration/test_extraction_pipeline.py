"""Integration test: ingest spans -> extract -> ground -> verify DB state."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.extraction.abstention import AbstentionGate
from mapu.extraction.grounding import CandidateGrounder
from mapu.extraction.merge import CandidateMergeEngine
from mapu.extraction.rules import (
    AmendmentExtractor,
    CrossReferenceExtractor,
    DateExtractor,
    DefinedTermExtractor,
)
from mapu.extraction.service import ExtractionService
from mapu.models.attestation import Attestation
from mapu.models.authority import SourcePolicyEval
from mapu.models.corpus import Corpus
from mapu.models.entity import Handle
from mapu.models.evidence import DocumentExpression, DocumentWork, TextSpan
from mapu.models.proposition import Proposition

pytestmark = pytest.mark.integration


async def _seed_document(
    session: AsyncSession,
    corpus: Corpus,
    spans_text: list[str],
) -> tuple[uuid.UUID, uuid.UUID]:
    doc = DocumentWork(
        id=uuid.uuid4(),
        corpus_id=corpus.id,
        mime_type="text/plain",
        ingested_at=datetime.now(UTC),
    )
    session.add(doc)
    await session.flush()

    expr = DocumentExpression(
        id=uuid.uuid4(),
        document_id=doc.id,
        corpus_id=corpus.id,
        parser_version="test_v1",
        created_at=datetime.now(UTC),
    )
    session.add(expr)
    await session.flush()

    offset = 0
    for text in spans_text:
        span = TextSpan(
            id=uuid.uuid4(),
            expression_id=expr.id,
            corpus_id=corpus.id,
            node_id=None,
            text=text,
            start_char=offset,
            end_char=offset + len(text),
        )
        session.add(span)
        offset += len(text)

    await session.flush()

    spe = SourcePolicyEval(
        id=uuid.uuid4(),
        document_id=doc.id,
        corpus_id=corpus.id,
        policy_version="v1",
        evaluator="rule_based",
        document_type="contract",
        authority_score=0.8,
        evaluated_at=datetime.now(UTC),
    )
    session.add(spe)
    await session.flush()

    return expr.id, spe.id


class TestExtractionPipeline:
    async def test_defined_term_end_to_end(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        expr_id, spe_id = await _seed_document(
            session,
            corpus_a,
            ['"Affiliate" means any entity that controls or is controlled by a Party.'],
        )

        grounder = CandidateGrounder(session=session, corpus_id=corpus_a.id)
        service = ExtractionService(
            session=session,
            corpus_id=corpus_a.id,
            extractors=[DefinedTermExtractor()],
            merge_engine=CandidateMergeEngine(),
            abstention_gate=AbstentionGate(auto_accept_min=0.85, candidate_min=0.3),
            grounder=grounder,
        )

        result = await service.extract_expression(
            expression_id=expr_id,
            source_policy_eval_id=spe_id,
        )

        assert result.spans_processed == 1
        assert result.candidates_produced == 1
        assert result.accepted == 1
        assert len(result.materialized) == 1

        prop_row = await session.get(Proposition, result.materialized[0].proposition_id)
        assert prop_row is not None
        assert prop_row.frame_type == "definition"
        assert prop_row.predicate == "means"

        handle_row = await session.get(Handle, result.materialized[0].handle_ids[0])
        assert handle_row is not None
        assert handle_row.canonical_name == "Affiliate"
        assert handle_row.kind == "defined_term"

        att_row = await session.get(Attestation, result.materialized[0].attestation_id)
        assert att_row is not None
        assert att_row.status == "accepted"
        assert att_row.extraction_method == "rule_defined_term"

    async def test_all_extractors_combined(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        expr_id, spe_id = await _seed_document(
            session,
            corpus_a,
            [
                '"Closing Date" means the date on which the closing occurs.',
                "Pursuant to Section 4.1 of this Agreement, filed on 2024-01-15.",
                "Section 7.2(a) is hereby amended and restated in its entirety.",
            ],
        )

        grounder = CandidateGrounder(session=session, corpus_id=corpus_a.id)
        service = ExtractionService(
            session=session,
            corpus_id=corpus_a.id,
            extractors=[
                DateExtractor(),
                CrossReferenceExtractor(),
                DefinedTermExtractor(),
                AmendmentExtractor(),
            ],
            merge_engine=CandidateMergeEngine(),
            abstention_gate=AbstentionGate(auto_accept_min=0.85, candidate_min=0.3),
            grounder=grounder,
        )

        result = await service.extract_expression(
            expression_id=expr_id,
            source_policy_eval_id=spe_id,
        )

        assert result.spans_processed == 3
        assert result.candidates_produced >= 2
        assert result.accepted >= 2

        prop_count = await session.scalar(
            select(func.count(Proposition.id)).where(
                Proposition.corpus_id == corpus_a.id
            )
        )
        assert prop_count is not None
        assert prop_count >= 2

        handle_count = await session.scalar(
            select(func.count(Handle.id)).where(
                Handle.corpus_id == corpus_a.id
            )
        )
        assert handle_count is not None
        assert handle_count >= 2

    async def test_idempotent_extraction(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        expr_id, spe_id = await _seed_document(
            session,
            corpus_a,
            ['"Material Adverse Effect" means any event materially adverse to the Company.'],
        )

        grounder = CandidateGrounder(session=session, corpus_id=corpus_a.id)
        service = ExtractionService(
            session=session,
            corpus_id=corpus_a.id,
            extractors=[DefinedTermExtractor()],
            merge_engine=CandidateMergeEngine(),
            abstention_gate=AbstentionGate(auto_accept_min=0.85, candidate_min=0.3),
            grounder=grounder,
        )

        r1 = await service.extract_expression(
            expression_id=expr_id, source_policy_eval_id=spe_id,
        )
        r2 = await service.extract_expression(
            expression_id=expr_id, source_policy_eval_id=spe_id,
        )

        assert r1.materialized[0].proposition_id == r2.materialized[0].proposition_id
        assert not r2.materialized[0].proposition_created

        att_count = await session.scalar(
            select(func.count(Attestation.id)).where(
                Attestation.proposition_id == r1.materialized[0].proposition_id
            )
        )
        assert att_count == 2

    async def test_low_confidence_rejected(
        self, session: AsyncSession, corpus_a: Corpus
    ) -> None:
        expr_id, spe_id = await _seed_document(
            session,
            corpus_a,
            ["This is a normal clause with no extractable content."],
        )

        grounder = CandidateGrounder(session=session, corpus_id=corpus_a.id)
        service = ExtractionService(
            session=session,
            corpus_id=corpus_a.id,
            extractors=[DefinedTermExtractor(), DateExtractor()],
            merge_engine=CandidateMergeEngine(),
            abstention_gate=AbstentionGate(auto_accept_min=0.85, candidate_min=0.3),
            grounder=grounder,
        )

        result = await service.extract_expression(
            expression_id=expr_id, source_policy_eval_id=spe_id,
        )

        assert result.spans_processed == 1
        assert result.candidates_produced == 0
        assert result.accepted == 0
        assert len(result.materialized) == 0

    async def test_corpus_isolation(
        self, session: AsyncSession, corpus_a: Corpus, corpus_b: Corpus
    ) -> None:
        expr_a, spe_a = await _seed_document(
            session,
            corpus_a,
            ['"Party" means each signatory to this Agreement.'],
        )
        expr_b, spe_b = await _seed_document(
            session,
            corpus_b,
            ['"Party" means each signatory to this Agreement.'],
        )

        for corpus, expr_id, spe_id in [
            (corpus_a, expr_a, spe_a),
            (corpus_b, expr_b, spe_b),
        ]:
            grounder = CandidateGrounder(session=session, corpus_id=corpus.id)
            service = ExtractionService(
                session=session,
                corpus_id=corpus.id,
                extractors=[DefinedTermExtractor()],
                merge_engine=CandidateMergeEngine(),
                abstention_gate=AbstentionGate(),
                grounder=grounder,
            )
            await service.extract_expression(
                expression_id=expr_id, source_policy_eval_id=spe_id,
            )

        handles_a = (await session.execute(
            select(Handle).where(Handle.corpus_id == corpus_a.id)
        )).scalars().all()
        handles_b = (await session.execute(
            select(Handle).where(Handle.corpus_id == corpus_b.id)
        )).scalars().all()

        assert len(handles_a) == 1
        assert len(handles_b) == 1
        assert handles_a[0].id != handles_b[0].id

        props_a = (await session.execute(
            select(Proposition).where(Proposition.corpus_id == corpus_a.id)
        )).scalars().all()
        props_b = (await session.execute(
            select(Proposition).where(Proposition.corpus_id == corpus_b.id)
        )).scalars().all()

        assert len(props_a) == 1
        assert len(props_b) == 1
        assert props_a[0].id != props_b[0].id
