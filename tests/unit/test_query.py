"""Unit tests for query engine: intent classification, governor, synthesis."""

from __future__ import annotations

import uuid

import pytest

from mapu.query.governor import (
    CascadeGovernor,
    _extract_query_entities,
    _extract_query_predicates,
)
from mapu.query.intent import HeuristicIntentClassifier
from mapu.query.synthesis import TemplateSynthesizer
from mapu.query.types import (
    PropositionHit,
    QueryIntent,
    QueryRequest,
    Tier,
)


def _make_request(question: str) -> QueryRequest:
    return QueryRequest(
        corpus_id=uuid.uuid4(),
        question=question,
    )


def _make_hit(
    *,
    text: str = "Test proposition",
    subject: str = "Entity",
    kind: str = "org",
    confidence: float = 0.9,
    frame_type: str = "definition",
    predicate: str = "defines",
) -> PropositionHit:
    return PropositionHit(
        proposition_id=uuid.uuid4(),
        normalized_text=text,
        frame_type=frame_type,
        predicate=predicate,
        subject_name=subject,
        subject_kind=kind,
        object_name=None,
        object_kind=None,
        truth_status=None,
        extraction_confidence=confidence,
        authority_score=None,
        source_span_text=None,
        relevance_score=0.85,
    )


class TestHeuristicIntentClassifier:
    @pytest.mark.asyncio
    async def test_identity_who_is(self) -> None:
        c = HeuristicIntentClassifier()
        intent, conf = await c.classify("Who is Acme Corporation?")
        assert intent == QueryIntent.IDENTITY
        assert conf >= 0.8

    @pytest.mark.asyncio
    async def test_identity_what_is(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("What is a covenant?")
        assert intent == QueryIntent.IDENTITY

    @pytest.mark.asyncio
    async def test_identity_define(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("Define borrower")
        assert intent == QueryIntent.IDENTITY

    @pytest.mark.asyncio
    async def test_list_what_are_all(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("What are all the covenants?")
        assert intent == QueryIntent.LIST

    @pytest.mark.asyncio
    async def test_list_enumerate(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("List the obligations")
        assert intent == QueryIntent.LIST

    @pytest.mark.asyncio
    async def test_temporal_when(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("When did the merger occur?")
        assert intent == QueryIntent.TEMPORAL

    @pytest.mark.asyncio
    async def test_temporal_diff_change(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("How did the termination clause change?")
        assert intent == QueryIntent.TEMPORAL_DIFF

    @pytest.mark.asyncio
    async def test_temporal_diff_between(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify(
            "What changed between the original agreement and the amendment?"
        )
        assert intent == QueryIntent.TEMPORAL_DIFF

    @pytest.mark.asyncio
    async def test_measurement(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("How much is the termination fee?")
        assert intent == QueryIntent.MEASUREMENT

    @pytest.mark.asyncio
    async def test_gap_detection(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("What's missing from our analysis?")
        assert intent == QueryIntent.GAP

    @pytest.mark.asyncio
    async def test_investigation_why(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("Why did the price drop?")
        assert intent == QueryIntent.INVESTIGATION

    @pytest.mark.asyncio
    async def test_relationship(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("How does X relate to Y?")
        assert intent == QueryIntent.RELATIONSHIP

    @pytest.mark.asyncio
    async def test_cross_doc(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify(
            "Does the amendment affect the original agreement?"
        )
        assert intent == QueryIntent.CROSS_DOC

    @pytest.mark.asyncio
    async def test_fallback_identity(self) -> None:
        c = HeuristicIntentClassifier()
        intent, conf = await c.classify("random gibberish query")
        assert intent == QueryIntent.IDENTITY
        assert conf < 0.5

    @pytest.mark.asyncio
    async def test_empty_string(self) -> None:
        c = HeuristicIntentClassifier()
        intent, conf = await c.classify("")
        assert conf < 0.2


class TestCascadeGovernor:
    @pytest.mark.asyncio
    async def test_identity_routes_to_direct(self) -> None:
        classifier = HeuristicIntentClassifier()
        governor = CascadeGovernor(classifier)
        request = _make_request("Who is Acme Corporation?")
        plan = await governor.plan(request)
        assert plan.intent == QueryIntent.IDENTITY
        assert plan.selected_tier == Tier.DIRECT

    @pytest.mark.asyncio
    async def test_list_routes_to_structured(self) -> None:
        classifier = HeuristicIntentClassifier()
        governor = CascadeGovernor(classifier)
        request = _make_request("What are all the covenants?")
        plan = await governor.plan(request)
        assert plan.intent == QueryIntent.LIST
        assert plan.selected_tier == Tier.STRUCTURED

    @pytest.mark.asyncio
    async def test_investigation_routes_to_investigation(self) -> None:
        classifier = HeuristicIntentClassifier()
        governor = CascadeGovernor(classifier)
        request = _make_request("Why did the price drop?")
        plan = await governor.plan(request)
        assert plan.intent == QueryIntent.INVESTIGATION
        assert plan.selected_tier == Tier.INVESTIGATION
        assert plan.escalation_reason is not None

    @pytest.mark.asyncio
    async def test_relationship_routes_to_synthesis(self) -> None:
        classifier = HeuristicIntentClassifier()
        governor = CascadeGovernor(classifier)
        request = _make_request("How does X relate to Y?")
        plan = await governor.plan(request)
        assert plan.selected_tier == Tier.SYNTHESIS

    @pytest.mark.asyncio
    async def test_low_confidence_routes_to_synthesis(self) -> None:
        classifier = HeuristicIntentClassifier()
        governor = CascadeGovernor(classifier)
        request = _make_request("some ambiguous query here")
        plan = await governor.plan(request)
        assert plan.selected_tier == Tier.SYNTHESIS

    @pytest.mark.asyncio
    async def test_entities_extracted_from_query(self) -> None:
        classifier = HeuristicIntentClassifier()
        governor = CascadeGovernor(classifier)
        request = _make_request('Who is "Acme Corp"?')
        plan = await governor.plan(request)
        assert "Acme Corp" in plan.entities_extracted


class TestEntityExtraction:
    def test_quoted_entities(self) -> None:
        entities = _extract_query_entities('What about "Alpha Corp" and "Beta LLC"?')
        assert "Alpha Corp" in entities
        assert "Beta LLC" in entities

    def test_capitalized_entities(self) -> None:
        entities = _extract_query_entities("What does Acme Corporation do?")
        assert "Acme Corporation" in entities

    def test_skip_question_words(self) -> None:
        entities = _extract_query_entities("What is the value?")
        assert "What" not in entities


class TestPredicateExtraction:
    def test_common_predicates(self) -> None:
        predicates = _extract_query_predicates("Who controls this entity?")
        assert "control" in predicates or "controls" in predicates

    def test_no_predicates(self) -> None:
        predicates = _extract_query_predicates("Hello world")
        assert len(predicates) == 0


class TestTemplateSynthesizer:
    @pytest.mark.asyncio
    async def test_identity_template(self) -> None:
        synth = TemplateSynthesizer()
        hits = [_make_hit(text="Acme is a corporation", subject="Acme")]
        result = await synth.synthesize("Who is Acme?", hits, QueryIntent.IDENTITY)
        assert "Acme" in result
        assert "corporation" in result

    @pytest.mark.asyncio
    async def test_list_template(self) -> None:
        synth = TemplateSynthesizer()
        hits = [
            _make_hit(text="Covenant A"),
            _make_hit(text="Covenant B"),
        ]
        result = await synth.synthesize("What are all covenants?", hits, QueryIntent.LIST)
        assert "2 results" in result
        assert "Covenant A" in result

    @pytest.mark.asyncio
    async def test_empty_hits(self) -> None:
        synth = TemplateSynthesizer()
        result = await synth.synthesize("Who?", [], QueryIntent.IDENTITY)
        assert "No matching" in result

    @pytest.mark.asyncio
    async def test_generic_template_truncation(self) -> None:
        synth = TemplateSynthesizer()
        hits = [_make_hit(text=f"Prop {i}") for i in range(15)]
        result = await synth.synthesize("test", hits, QueryIntent.GAP)
        assert "15 relevant" in result
        assert "5 more" in result
