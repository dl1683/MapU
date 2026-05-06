"""Unit tests for ExtractionService orchestration (pure, no DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from mapu.extraction.abstention import AbstentionGate
from mapu.extraction.grounding import CandidateGrounder, MaterializedExtraction
from mapu.extraction.merge import CandidateMergeEngine
from mapu.extraction.rules import DefinedTermExtractor
from mapu.extraction.service import ExtractionService
from mapu.extraction.types import ExtractionContext, ExtractorOutput


def _make_mock_session(
    spans: list[MagicMock] | None = None,
    document_id: uuid.UUID | None = None,
) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    if spans is not None or document_id is not None:
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = document_id or uuid.uuid4()

        span_result = MagicMock()
        span_result.scalars.return_value.all.return_value = spans or []

        session.execute = AsyncMock(side_effect=[doc_result, span_result])

    return session


def _make_span(
    text: str,
    *,
    expression_id: uuid.UUID | None = None,
    corpus_id: uuid.UUID | None = None,
) -> MagicMock:
    span = MagicMock()
    span.id = uuid.uuid4()
    span.expression_id = expression_id or uuid.uuid4()
    span.corpus_id = corpus_id or uuid.uuid4()
    span.node_id = None
    span.text = text
    span.start_char = 0
    span.end_char = len(text)
    return span


class TestExtractionService:
    @pytest.fixture
    def corpus_id(self) -> uuid.UUID:
        return uuid.uuid4()

    async def test_extract_defined_term(self, corpus_id: uuid.UUID) -> None:
        expression_id = uuid.uuid4()
        span = _make_span(
            '"Affiliate" means any entity controlled by a Party.',
            expression_id=expression_id,
            corpus_id=corpus_id,
        )

        session = _make_mock_session(spans=[span])

        mock_grounder = AsyncMock(spec=CandidateGrounder)
        mock_grounder.materialize = AsyncMock(return_value=MaterializedExtraction(
            proposition_id=uuid.uuid4(),
            attestation_id=uuid.uuid4(),
            proposition_created=True,
            handle_ids=[uuid.uuid4()],
        ))

        service = ExtractionService(
            session=session,
            corpus_id=corpus_id,
            extractors=[DefinedTermExtractor()],
            merge_engine=CandidateMergeEngine(),
            abstention_gate=AbstentionGate(auto_accept_min=0.85, candidate_min=0.3),
            grounder=mock_grounder,
        )

        result = await service.extract_expression(
            expression_id=expression_id,
            source_policy_eval_id=uuid.uuid4(),
        )

        assert result.spans_processed == 1
        assert result.candidates_produced == 1
        assert result.accepted == 1
        assert len(result.materialized) == 1
        mock_grounder.materialize.assert_called_once()

    async def test_no_extraction_on_empty_spans(
        self, corpus_id: uuid.UUID
    ) -> None:
        session = _make_mock_session(spans=[])
        mock_grounder = AsyncMock(spec=CandidateGrounder)

        service = ExtractionService(
            session=session,
            corpus_id=corpus_id,
            extractors=[DefinedTermExtractor()],
            merge_engine=CandidateMergeEngine(),
            abstention_gate=AbstentionGate(),
            grounder=mock_grounder,
        )

        result = await service.extract_expression(
            expression_id=uuid.uuid4(),
            source_policy_eval_id=uuid.uuid4(),
        )

        assert result.spans_processed == 0
        assert result.candidates_produced == 0
        mock_grounder.materialize.assert_not_called()

    async def test_rejected_candidates_not_materialized(
        self, corpus_id: uuid.UUID
    ) -> None:
        expression_id = uuid.uuid4()
        span = _make_span(
            "No defined terms here, just some text.",
            expression_id=expression_id,
            corpus_id=corpus_id,
        )

        session = _make_mock_session(spans=[span])
        mock_grounder = AsyncMock(spec=CandidateGrounder)

        class LowConfExtractor:
            @property
            def name(self) -> str:
                return "low_conf"

            async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
                from mapu.extraction.types import EntityMention, PropositionFrameCandidate
                from mapu.types import AttestationStrength, FrameType, Stance

                frame = PropositionFrameCandidate(
                    span_id=ctx.span_id,
                    frame_type=FrameType.FINDING,
                    subject=EntityMention(
                        text="some", kind="test",
                        start_char=0, end_char=4,
                        confidence=0.1, source="test",
                    ),
                    predicate="test",
                    object=None,
                    value=None,
                    polarity=True,
                    modality=None,
                    valid_range=None,
                    normalized_text="low confidence",
                    qualifiers={},
                    stance=Stance.REPORTS,
                    attestation_strength=AttestationStrength.INFERENCE,
                    extraction_method="low_conf",
                    extraction_confidence=0.1,
                )
                return ExtractorOutput(frames=(frame,))

        service = ExtractionService(
            session=session,
            corpus_id=corpus_id,
            extractors=[LowConfExtractor()],
            merge_engine=CandidateMergeEngine(),
            abstention_gate=AbstentionGate(auto_accept_min=0.85, candidate_min=0.3),
            grounder=mock_grounder,
        )

        result = await service.extract_expression(
            expression_id=expression_id,
            source_policy_eval_id=uuid.uuid4(),
        )

        assert result.candidates_produced == 1
        assert result.rejected == 1
        assert result.accepted == 0
        mock_grounder.materialize.assert_not_called()
