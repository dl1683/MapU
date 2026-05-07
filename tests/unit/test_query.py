"""Unit tests for query engine: intent classification, governor, synthesis, service."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock

import pytest

from mapu.query.governor import (
    CascadeGovernor,
    _extract_query_entities,
    _extract_query_predicates,
)
from mapu.query.intent import HeuristicIntentClassifier
from mapu.query.service import QueryService
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
    async def test_measurement_keyword(self) -> None:
        c = HeuristicIntentClassifier()
        intent, _ = await c.classify("What is the termination fee?")
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
    async def test_cross_doc_routes_to_investigation(self) -> None:
        classifier = HeuristicIntentClassifier()
        governor = CascadeGovernor(classifier)
        request = _make_request(
            "Does the amendment affect the original agreement?"
        )
        plan = await governor.plan(request)
        assert plan.intent == QueryIntent.CROSS_DOC
        assert plan.selected_tier == Tier.INVESTIGATION
        assert plan.escalation_reason is not None

    @pytest.mark.asyncio
    async def test_measurement_routes_to_structured(self) -> None:
        classifier = HeuristicIntentClassifier()
        governor = CascadeGovernor(classifier)
        request = _make_request("How much is the termination fee?")
        plan = await governor.plan(request)
        assert plan.intent == QueryIntent.MEASUREMENT
        assert plan.selected_tier == Tier.STRUCTURED

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

    def test_acronym_entities(self) -> None:
        entities = _extract_query_entities("What does AWS do?")
        assert "AWS" in entities

    def test_acronym_in_phrase(self) -> None:
        entities = _extract_query_entities("Tell me about the SEC filing for ACME LLC")
        assert "SEC" in entities
        assert "LLC" in entities

    def test_identity_noun_phrase(self) -> None:
        entities = _extract_query_entities("What is a covenant?")
        assert "covenant" in entities

    def test_define_noun_phrase(self) -> None:
        entities = _extract_query_entities("Define borrower")
        assert "borrower" in entities


class TestPredicateExtraction:
    def test_verb_inflected_forms(self) -> None:
        predicates = _extract_query_predicates("Who controlled this entity?")
        assert "controlled" in predicates

    def test_verb_ing_form(self) -> None:
        predicates = _extract_query_predicates("Who is managing the project?")
        assert "managing" in predicates

    def test_no_predicates(self) -> None:
        predicates = _extract_query_predicates("Hello world")
        assert len(predicates) == 0

    def test_nouns_not_captured(self) -> None:
        predicates = _extract_query_predicates("What are all the covenants?")
        assert len(predicates) == 0

    def test_plural_nouns_es_not_captured(self) -> None:
        predicates = _extract_query_predicates("List all services and classes")
        assert "services" not in predicates
        assert "classes" not in predicates


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
        assert "no matching" in result.lower()

    @pytest.mark.asyncio
    async def test_generic_template_truncation(self) -> None:
        synth = TemplateSynthesizer()
        hits = [_make_hit(text=f"Prop {i}") for i in range(15)]
        result = await synth.synthesize("test", hits, QueryIntent.GAP)
        assert "15 relevant" in result
        assert "5 more" in result


class TestQueryService:
    """Tests for the QueryService facade — tier routing, escalation, synthesis."""

    def _make_service(
        self,
        direct_hits: Sequence[PropositionHit] = (),
        structured_hits: Sequence[PropositionHit] = (),
    ) -> QueryService:
        session = AsyncMock()
        classifier = HeuristicIntentClassifier()
        svc = QueryService(session=session, intent_classifier=classifier)
        svc._direct = MagicMock()
        svc._direct.execute = AsyncMock(return_value=list(direct_hits))
        svc._structured = MagicMock()
        svc._structured.execute = AsyncMock(return_value=list(structured_hits))
        return svc

    @pytest.mark.asyncio
    async def test_identity_uses_direct_tier(self) -> None:
        hits = [_make_hit(text="Acme is a corp", subject="Acme")]
        svc = self._make_service(direct_hits=hits)
        result = await svc.query(_make_request("Who is Acme?"))
        assert result.tier_used == Tier.DIRECT
        assert len(result.hits) == 1
        svc._direct.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_uses_structured_tier(self) -> None:
        hits = [_make_hit(text="Covenant A"), _make_hit(text="Covenant B")]
        svc = self._make_service(structured_hits=hits)
        result = await svc.query(_make_request("What are all the covenants?"))
        assert result.tier_used == Tier.STRUCTURED
        assert len(result.hits) == 2
        svc._structured.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_direct_escalates_to_structured_on_empty(self) -> None:
        hits = [_make_hit(text="Found via structured")]
        svc = self._make_service(direct_hits=[], structured_hits=hits)
        result = await svc.query(_make_request("Who is Acme Corp?"))
        assert result.tier_used == Tier.STRUCTURED
        assert len(result.hits) == 1
        svc._direct.execute.assert_awaited_once()
        svc._structured.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_escalation_past_structured(self) -> None:
        svc = self._make_service(structured_hits=[])
        result = await svc.query(_make_request("What are all the covenants?"))
        assert result.tier_used == Tier.STRUCTURED
        assert len(result.hits) == 0
        assert result.synthesis is None

    @pytest.mark.asyncio
    async def test_investigation_without_llm_falls_back_to_structured(self) -> None:
        svc = self._make_service()
        result = await svc.query(_make_request("Why did the price drop?"))
        assert result.tier_used == Tier.STRUCTURED
        assert result.metadata.get("llm_fallback") == "structured_query"

    @pytest.mark.asyncio
    async def test_synthesis_returned_for_hits(self) -> None:
        hits = [_make_hit(text="Acme is a corporation", subject="Acme")]
        svc = self._make_service(direct_hits=hits)
        result = await svc.query(_make_request("Who is Acme?"))
        assert result.synthesis is not None
        assert "Acme" in result.synthesis

    @pytest.mark.asyncio
    async def test_no_synthesis_for_empty_hits(self) -> None:
        svc = self._make_service(direct_hits=[])
        svc._structured.execute = AsyncMock(return_value=[])
        result = await svc.query(_make_request("Who is Nobody?"))
        assert result.synthesis is None

    @pytest.mark.asyncio
    async def test_synthesis_tier_uses_structured_executor(self) -> None:
        hits = [_make_hit(text="X controls Y", subject="X")]
        svc = self._make_service(structured_hits=hits)
        result = await svc.query(_make_request("How does X relate to Y?"))
        assert result.tier_used == Tier.SYNTHESIS
        assert len(result.hits) == 1
        svc._structured.execute.assert_awaited_once()
        assert result.synthesis is not None
        assert "X controls Y" in result.synthesis

    @pytest.mark.asyncio
    async def test_synthesis_tier_prefers_llm_when_available(self) -> None:
        hits = [_make_hit(text="X controls Y", subject="X")]
        svc = self._make_service(structured_hits=hits)
        llm_synth = AsyncMock(return_value="LLM synthesis result")
        svc._llm_synth = MagicMock()
        svc._llm_synth.synthesize = llm_synth
        result = await svc.query(_make_request("How does X relate to Y?"))
        assert result.tier_used == Tier.SYNTHESIS
        llm_synth.assert_awaited_once()
        assert result.synthesis == "LLM synthesis result"

    @pytest.mark.asyncio
    async def test_metadata_contains_entities(self) -> None:
        hits = [_make_hit(text="Acme fact", subject="Acme")]
        svc = self._make_service(direct_hits=hits)
        result = await svc.query(_make_request('Who is "Acme Corp"?'))
        assert "Acme Corp" in result.metadata.get("entities", ())


class TestQueryRequestAsOf:
    def test_as_of_defaults_to_none(self) -> None:
        req = QueryRequest(corpus_id=uuid.uuid4(), question="test")
        assert req.as_of is None

    def test_as_of_accepts_datetime(self) -> None:
        from datetime import UTC, datetime

        dt = datetime(2025, 1, 1, tzinfo=UTC)
        req = QueryRequest(corpus_id=uuid.uuid4(), question="test", as_of=dt)
        assert req.as_of == dt


class TestProviderRegistry:
    def test_register_and_lookup(self) -> None:
        from mapu.providers.llms import (
            OpenAICompatibleLLMProvider,
            _PROVIDER_FACTORIES,
            register_llm_provider,
        )

        register_llm_provider("custom", OpenAICompatibleLLMProvider, "custom-model-1")
        assert "custom" in _PROVIDER_FACTORIES
        del _PROVIDER_FACTORIES["custom"]


class TestEmbeddingProviderRegistry:
    def test_register_and_lookup(self) -> None:
        from mapu.providers.embeddings import (
            _PROVIDER_FACTORIES as EMB_FACTORIES,
            register_embedding_provider,
        )

        register_embedding_provider("test-emb", lambda **kw: None)
        assert "test-emb" in EMB_FACTORIES
        del EMB_FACTORIES["test-emb"]

    def test_builtins_registered(self) -> None:
        from mapu.providers.embeddings import _PROVIDER_FACTORIES as EMB_FACTORIES

        assert "local" in EMB_FACTORIES
        assert "sentence-transformers" in EMB_FACTORIES
