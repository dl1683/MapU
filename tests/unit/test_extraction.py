"""Unit tests for extraction pipeline: rules, merge, abstention."""

from __future__ import annotations

import uuid

import pytest

from mapu.extraction.abstention import AbstentionDecision, AbstentionGate
from mapu.extraction.merge import CandidateMergeEngine
from mapu.extraction.rules import (
    AmendmentExtractor,
    CrossReferenceExtractor,
    DateExtractor,
    DefinedTermExtractor,
)
from mapu.extraction.types import (
    EntityMention,
    ExtractionContext,
    ExtractorOutput,
    PropositionFrameCandidate,
)
from mapu.types import AttestationStrength, FrameType, Stance


def _make_ctx(text: str) -> ExtractionContext:
    return ExtractionContext(
        corpus_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        expression_id=uuid.uuid4(),
        span_id=uuid.uuid4(),
        node_id=None,
        text=text,
        start_char=0,
        end_char=len(text),
    )


def _make_frame(
    *,
    confidence: float = 0.9,
    subject_text: str = "Test",
    predicate: str = "test_pred",
    frame_type: FrameType = FrameType.DEFINITION,
) -> PropositionFrameCandidate:
    return PropositionFrameCandidate(
        span_id=uuid.uuid4(),
        frame_type=frame_type,
        subject=EntityMention(
            text=subject_text,
            kind="test",
            start_char=0,
            end_char=4,
            confidence=1.0,
            source="test",
        ),
        predicate=predicate,
        object=None,
        value=None,
        polarity=True,
        modality=None,
        valid_range=None,
        normalized_text=f"{subject_text} {predicate}",
        qualifiers={},
        stance=Stance.ASSERTS,
        attestation_strength=AttestationStrength.DIRECT_STATEMENT,
        extraction_method="test",
        extraction_confidence=confidence,
    )


class TestDateExtractor:
    @pytest.fixture
    def extractor(self) -> DateExtractor:
        return DateExtractor()

    async def test_iso_date(self, extractor: DateExtractor) -> None:
        ctx = _make_ctx("The effective date is 2024-01-15.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].signal_type == "date"
        assert result.signals[0].data["raw_text"] == "2024-01-15"

    async def test_month_day_year(self, extractor: DateExtractor) -> None:
        ctx = _make_ctx("Filed on January 15, 2024 with the court.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert "2024" in result.signals[0].data["raw_text"]

    async def test_slash_date(self, extractor: DateExtractor) -> None:
        ctx = _make_ctx("Due by 1/15/2024.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1

    async def test_no_dates(self, extractor: DateExtractor) -> None:
        ctx = _make_ctx("No dates here.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 0

    async def test_no_propositions(self, extractor: DateExtractor) -> None:
        ctx = _make_ctx("Filed on 2024-01-15.")
        result = await extractor.extract(ctx)
        assert len(result.frames) == 0


class TestCrossReferenceExtractor:
    @pytest.fixture
    def extractor(self) -> CrossReferenceExtractor:
        return CrossReferenceExtractor()

    async def test_section_reference(
        self, extractor: CrossReferenceExtractor
    ) -> None:
        ctx = _make_ctx("As set forth in Section 3.2(a) of this Agreement.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].data["section_id"] == "3.2(a)"

    async def test_article_reference(
        self, extractor: CrossReferenceExtractor
    ) -> None:
        ctx = _make_ctx("Pursuant to Article 7 of the Treaty.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1

    async def test_no_references(
        self, extractor: CrossReferenceExtractor
    ) -> None:
        ctx = _make_ctx("No references here.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 0


class TestDefinedTermExtractor:
    @pytest.fixture
    def extractor(self) -> DefinedTermExtractor:
        return DefinedTermExtractor()

    async def test_quoted_definition(
        self, extractor: DefinedTermExtractor
    ) -> None:
        ctx = _make_ctx(
            '"Affiliate" means any entity that controls or is controlled by a Party.'
        )
        result = await extractor.extract(ctx)
        assert len(result.frames) == 1
        frame = result.frames[0]
        assert frame.frame_type == FrameType.DEFINITION
        assert frame.subject.text == "Affiliate"
        assert frame.subject.kind == "defined_term"
        assert frame.predicate == "means"
        assert frame.extraction_confidence == 0.95

    async def test_shall_mean(self, extractor: DefinedTermExtractor) -> None:
        ctx = _make_ctx('"Closing Date" shall mean the date of the closing.')
        result = await extractor.extract(ctx)
        assert len(result.frames) == 1
        assert result.frames[0].subject.text == "Closing Date"

    async def test_definition_value_excludes_term(
        self, extractor: DefinedTermExtractor
    ) -> None:
        ctx = _make_ctx(
            '"Closing Date" means the date on which the closing occurs.'
        )
        result = await extractor.extract(ctx)
        assert len(result.frames) == 1
        definition = result.frames[0].value
        assert definition is not None
        assert '"Closing Date"' not in definition["definition"]
        assert "means" not in definition["definition"]

    async def test_no_definitions(
        self, extractor: DefinedTermExtractor
    ) -> None:
        ctx = _make_ctx("This section has no defined terms.")
        result = await extractor.extract(ctx)
        assert len(result.frames) == 0


class TestAmendmentExtractor:
    @pytest.fixture
    def extractor(self) -> AmendmentExtractor:
        return AmendmentExtractor()

    async def test_hereby_amended(
        self, extractor: AmendmentExtractor
    ) -> None:
        ctx = _make_ctx(
            "Section 7.2(a) is hereby amended and restated in its entirety."
        )
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].signal_type == "amendment"
        assert "amended and restated" in result.signals[0].data["action"]

    async def test_overlapping_patterns_dedup(
        self, extractor: AmendmentExtractor
    ) -> None:
        ctx = _make_ctx(
            "Section 3.1 is hereby amended and restated in its entirety "
            "and Section 5.2 shall be deleted."
        )
        result = await extractor.extract(ctx)
        assert len(result.signals) == 2
        assert len(result.frames) == 2
        actions = {s.data["action"] for s in result.signals}
        assert "amended and restated in its entirety" in actions
        refs = {f.subject.text for f in result.frames}
        assert "Section 3.1" in refs
        assert "Section 5.2" in refs

    async def test_amendment_with_reference(
        self, extractor: AmendmentExtractor
    ) -> None:
        ctx = _make_ctx("Section 4.1 is hereby amended to read as follows.")
        result = await extractor.extract(ctx)
        assert len(result.frames) >= 1
        assert result.frames[0].subject.text == "Section 4.1"

    async def test_no_amendments(
        self, extractor: AmendmentExtractor
    ) -> None:
        ctx = _make_ctx("This is a normal clause.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 0

    async def test_cross_sentence_ref_not_attached(
        self, extractor: AmendmentExtractor
    ) -> None:
        ctx = _make_ctx(
            "Pursuant to Section 2.1 of this Agreement. "
            "The foregoing clause is hereby amended."
        )
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].data["target_reference"] is None
        assert len(result.frames) == 0

    async def test_amendment_targets_first_ref_not_nearest(
        self, extractor: AmendmentExtractor
    ) -> None:
        ctx = _make_ctx(
            "Section 2.1, as referenced in Section 9.1, is hereby amended."
        )
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].data["target_reference"] == "Section 2.1"
        assert len(result.frames) == 1
        assert result.frames[0].subject.text == "Section 2.1"

    async def test_section_number_at_sentence_end_not_attached(
        self, extractor: AmendmentExtractor
    ) -> None:
        ctx = _make_ctx(
            "Pursuant to Section 2.1. The foregoing clause is hereby amended."
        )
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].data["target_reference"] is None
        assert len(result.frames) == 0


class TestCandidateMergeEngine:
    def test_no_duplicates(self) -> None:
        engine = CandidateMergeEngine()
        frame1 = _make_frame(subject_text="Alpha", predicate="p1")
        frame2 = _make_frame(subject_text="Beta", predicate="p2")
        result = engine.merge([
            ExtractorOutput(frames=(frame1,)),
            ExtractorOutput(frames=(frame2,)),
        ])
        assert len(result.frames) == 2
        assert result.duplicates_removed == 0

    def test_exact_duplicates_removed(self) -> None:
        engine = CandidateMergeEngine()
        frame = _make_frame(subject_text="Gamma", predicate="p1")
        result = engine.merge([
            ExtractorOutput(frames=(frame,)),
            ExtractorOutput(frames=(frame,)),
        ])
        assert len(result.frames) == 1
        assert result.duplicates_removed == 1

    def test_signals_combined(self) -> None:
        engine = CandidateMergeEngine()
        from mapu.extraction.types import ExtractionSignal

        s1 = ExtractionSignal(signal_type="date", source="rule_date")
        s2 = ExtractionSignal(signal_type="cross_reference", source="rule_xref")
        result = engine.merge([
            ExtractorOutput(signals=(s1,)),
            ExtractorOutput(signals=(s2,)),
        ])
        assert len(result.signals) == 2

    def test_different_polarity_not_deduped(self) -> None:
        engine = CandidateMergeEngine()
        frame_pos = _make_frame(subject_text="Delta", predicate="p1")
        frame_neg = PropositionFrameCandidate(
            span_id=frame_pos.span_id,
            frame_type=frame_pos.frame_type,
            subject=frame_pos.subject,
            predicate=frame_pos.predicate,
            object=None,
            value=None,
            polarity=False,
            modality=None,
            valid_range=None,
            normalized_text="Delta p1 negated",
            qualifiers={},
            stance=Stance.DENIES,
            attestation_strength=AttestationStrength.DIRECT_STATEMENT,
            extraction_method="test",
            extraction_confidence=0.9,
        )
        result = engine.merge([
            ExtractorOutput(frames=(frame_pos,)),
            ExtractorOutput(frames=(frame_neg,)),
        ])
        assert len(result.frames) == 2


    def test_same_text_different_kind_not_deduped(self) -> None:
        engine = CandidateMergeEngine()
        frame_person = PropositionFrameCandidate(
            span_id=uuid.uuid4(),
            frame_type=FrameType.RELATIONSHIP,
            subject=EntityMention(
                text="Mercury", kind="person",
                start_char=0, end_char=7, confidence=1.0, source="test",
            ),
            predicate="located_in",
            object=None,
            value=None,
            polarity=True,
            modality=None,
            valid_range=None,
            normalized_text="Mercury located_in",
            qualifiers={},
            stance=Stance.ASSERTS,
            attestation_strength=AttestationStrength.DIRECT_STATEMENT,
            extraction_method="test",
            extraction_confidence=0.9,
        )
        frame_planet = PropositionFrameCandidate(
            span_id=frame_person.span_id,
            frame_type=FrameType.RELATIONSHIP,
            subject=EntityMention(
                text="Mercury", kind="planet",
                start_char=0, end_char=7, confidence=1.0, source="test",
            ),
            predicate="located_in",
            object=None,
            value=None,
            polarity=True,
            modality=None,
            valid_range=None,
            normalized_text="Mercury located_in",
            qualifiers={},
            stance=Stance.ASSERTS,
            attestation_strength=AttestationStrength.DIRECT_STATEMENT,
            extraction_method="test",
            extraction_confidence=0.9,
        )
        result = engine.merge([
            ExtractorOutput(frames=(frame_person,)),
            ExtractorOutput(frames=(frame_planet,)),
        ])
        assert len(result.frames) == 2
        assert result.duplicates_removed == 0

    def test_duplicate_keeps_highest_confidence(self) -> None:
        engine = CandidateMergeEngine()
        frame_low = _make_frame(
            subject_text="Corp", predicate="pay", confidence=0.5,
        )
        frame_high = _make_frame(
            subject_text="Corp", predicate="pay", confidence=0.95,
        )
        result = engine.merge([
            ExtractorOutput(frames=(frame_low,)),
            ExtractorOutput(frames=(frame_high,)),
        ])
        assert len(result.frames) == 1
        assert result.duplicates_removed == 1
        assert result.frames[0].extraction_confidence == 0.95

    def test_different_qualifiers_not_deduped(self) -> None:
        engine = CandidateMergeEngine()
        frame_a = _make_frame(subject_text="Corp", predicate="pay")
        frame_b = PropositionFrameCandidate(
            span_id=frame_a.span_id,
            frame_type=frame_a.frame_type,
            subject=frame_a.subject,
            predicate=frame_a.predicate,
            object=None,
            value=None,
            polarity=True,
            modality=None,
            valid_range=None,
            normalized_text="Corp pay",
            qualifiers={"condition": "if_approved"},
            stance=Stance.ASSERTS,
            attestation_strength=AttestationStrength.DIRECT_STATEMENT,
            extraction_method="test",
            extraction_confidence=0.9,
        )
        result = engine.merge([
            ExtractorOutput(frames=(frame_a,)),
            ExtractorOutput(frames=(frame_b,)),
        ])
        assert len(result.frames) == 2
        assert result.duplicates_removed == 0


class TestAbstentionGate:
    def test_auto_accept(self) -> None:
        gate = AbstentionGate(auto_accept_min=0.85, candidate_min=0.3)
        frame = _make_frame(confidence=0.95)
        results = gate.evaluate((frame,))
        assert results[0].decision == AbstentionDecision.ACCEPTED

    def test_candidate(self) -> None:
        gate = AbstentionGate(auto_accept_min=0.85, candidate_min=0.3)
        frame = _make_frame(confidence=0.5)
        results = gate.evaluate((frame,))
        assert results[0].decision == AbstentionDecision.CANDIDATE

    def test_rejected(self) -> None:
        gate = AbstentionGate(auto_accept_min=0.85, candidate_min=0.3)
        frame = _make_frame(confidence=0.1)
        results = gate.evaluate((frame,))
        assert results[0].decision == AbstentionDecision.REJECTED

    def test_boundary_accept(self) -> None:
        gate = AbstentionGate(auto_accept_min=0.85, candidate_min=0.3)
        frame = _make_frame(confidence=0.85)
        results = gate.evaluate((frame,))
        assert results[0].decision == AbstentionDecision.ACCEPTED

    def test_boundary_candidate(self) -> None:
        gate = AbstentionGate(auto_accept_min=0.85, candidate_min=0.3)
        frame = _make_frame(confidence=0.3)
        results = gate.evaluate((frame,))
        assert results[0].decision == AbstentionDecision.CANDIDATE

    def test_invalid_thresholds(self) -> None:
        with pytest.raises(ValueError, match="Invalid thresholds"):
            AbstentionGate(auto_accept_min=0.3, candidate_min=0.85)

    def test_empty_input(self) -> None:
        gate = AbstentionGate()
        results = gate.evaluate(())
        assert results == []

    def test_out_of_range_confidence_rejected(self) -> None:
        gate = AbstentionGate()
        frame = _make_frame(confidence=1.5)
        with pytest.raises(ValueError, match="extraction_confidence"):
            gate.evaluate((frame,))

    def test_negative_confidence_rejected(self) -> None:
        gate = AbstentionGate()
        frame = _make_frame(confidence=-0.1)
        with pytest.raises(ValueError, match="extraction_confidence"):
            gate.evaluate((frame,))


class TestCrossRefLetterIDs:
    """Cross-reference pattern should match letter-based IDs (Exhibit A, Schedule B)."""

    @pytest.fixture
    def extractor(self) -> CrossReferenceExtractor:
        return CrossReferenceExtractor()

    async def test_exhibit_letter(self, extractor: CrossReferenceExtractor) -> None:
        ctx = _make_ctx("See Exhibit A for the schedule of payments.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].data["section_id"] == "A"

    async def test_schedule_letter(self, extractor: CrossReferenceExtractor) -> None:
        ctx = _make_ctx("As set forth in Schedule B of this Agreement.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].data["section_id"] == "B"

    async def test_appendix_letter_with_number(
        self, extractor: CrossReferenceExtractor
    ) -> None:
        ctx = _make_ctx("Refer to Appendix C-2 for definitions.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].data["section_id"] == "C-2"

    async def test_numeric_still_works(self, extractor: CrossReferenceExtractor) -> None:
        ctx = _make_ctx("Pursuant to Section 3.2(a) of the Agreement.")
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        assert result.signals[0].data["section_id"] == "3.2(a)"


class TestAmendmentConjunctionLimitation:
    """Documents known limitation: conjunction targets use nearest-preceding heuristic.

    'Section 1.1 and Section 2.2 is hereby amended' targets Section 2.2 (nearest),
    not Section 1.1 (first). Conjunction awareness requires syntactic parsing (Phase 4+).
    """

    @pytest.fixture
    def extractor(self) -> AmendmentExtractor:
        return AmendmentExtractor()

    async def test_conjunction_targets_nearest(
        self, extractor: AmendmentExtractor
    ) -> None:
        ctx = _make_ctx(
            "Section 1.1 and Section 2.2 is hereby amended."
        )
        result = await extractor.extract(ctx)
        assert len(result.signals) == 1
        # Known limitation: targets nearest (Section 2.2), not first (Section 1.1)
        assert result.signals[0].data["target_reference"] == "Section 2.2"
