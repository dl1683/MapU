"""Unit tests for LLM-backed semantic proposition extractor."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from mapu.extraction.llm import LLMExtractor, _find_exact_span
from mapu.extraction.types import EntityMention, ExtractionContext
from mapu.providers.llms import LLMRequest


def _make_ctx(text: str, start_char: int = 0) -> ExtractionContext:
    return ExtractionContext(
        corpus_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        expression_id=uuid.uuid4(),
        span_id=uuid.uuid4(),
        node_id=None,
        text=text,
        start_char=start_char,
        end_char=start_char + len(text),
    )


def _mock_provider(response: dict[str, Any]) -> AsyncMock:
    provider = AsyncMock()
    provider.complete_json = AsyncMock(return_value=response)
    return provider


class TestLLMExtractorBasic:
    def test_name(self) -> None:
        provider = _mock_provider({})
        ext = LLMExtractor(provider=provider)
        assert ext.name == "llm"

    async def test_empty_text(self) -> None:
        provider = _mock_provider({})
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0
        assert len(result.signals) == 0
        provider.complete_json.assert_not_called()

    async def test_whitespace_text(self) -> None:
        provider = _mock_provider({})
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("   \n\t  ")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0
        provider.complete_json.assert_not_called()


class TestLLMExtractorExtraction:
    async def test_single_proposition(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "Seller",
                "subject_kind": "party",
                "predicate": "deliver",
                "object_text": "financial statements",
                "object_kind": "document",
                "value": None,
                "polarity": True,
                "modality": "obligation",
                "normalized_text": "Seller shall deliver financial statements",
                "frame_type": "obligation",
                "stance": "asserts",
                "attestation_strength": "direct_statement",
                "confidence": 0.92,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx(
            "The Seller shall deliver audited financial statements within 90 days."
        )
        result = await ext.extract(ctx)

        assert len(result.frames) == 1
        frame = result.frames[0]
        assert frame.subject.text == "Seller"
        assert frame.subject.kind == "party"
        assert frame.predicate == "deliver"
        assert frame.object is not None
        assert frame.object.text == "financial statements"
        assert frame.modality == "obligation"
        assert frame.extraction_method == "llm"
        assert frame.extraction_confidence == pytest.approx(0.92)
        assert frame.span_id == ctx.span_id

    async def test_multiple_propositions(self) -> None:
        response = {
            "propositions": [
                {
                    "subject_text": "TechCorp",
                    "subject_kind": "organization",
                    "predicate": "reported_revenue",
                    "object_text": None,
                    "object_kind": None,
                    "value": {"amount": 2.3, "unit": "billion", "currency": "USD"},
                    "polarity": True,
                    "modality": None,
                    "normalized_text": "TechCorp reported revenue of $2.3 billion",
                    "frame_type": "measurement",
                    "stance": "reports",
                    "attestation_strength": "direct_statement",
                    "confidence": 0.88,
                },
                {
                    "subject_text": "TechCorp",
                    "subject_kind": "organization",
                    "predicate": "operating_margin",
                    "object_text": None,
                    "object_kind": None,
                    "value": {"percentage": 28.5},
                    "polarity": True,
                    "modality": None,
                    "normalized_text": "TechCorp operating margin expanded to 28.5%",
                    "frame_type": "measurement",
                    "stance": "reports",
                    "attestation_strength": "direct_statement",
                    "confidence": 0.85,
                },
            ],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx(
            "TechCorp reported revenue of $2.3 billion. "
            "Operating margin expanded to 28.5%."
        )
        result = await ext.extract(ctx)

        assert len(result.frames) == 2
        assert result.frames[0].value == {"amount": 2.3, "unit": "billion", "currency": "USD"}
        assert result.frames[1].value == {"percentage": 28.5}

    async def test_no_object_proposition(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "make_payment",
                "subject_kind": "function",
                "predicate": "deprecated",
                "object_text": None,
                "object_kind": None,
                "value": {"version": "v3.0"},
                "polarity": True,
                "modality": None,
                "normalized_text": "make_payment deprecated in v3.0",
                "frame_type": "deprecation",
                "stance": "asserts",
                "attestation_strength": "direct_statement",
                "confidence": 0.95,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("make_payment is deprecated in v3.0.")
        result = await ext.extract(ctx)

        assert len(result.frames) == 1
        assert result.frames[0].object is None
        assert result.frames[0].frame_type == "deprecation"

    async def test_prior_entities_included_in_prompt(self) -> None:
        response = {"propositions": []}
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)

        ctx = ExtractionContext(
            corpus_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            expression_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            node_id=None,
            text="Alice works at Acme.",
            start_char=0,
            end_char=20,
            prior_entities=(
                EntityMention(
                    text="Alice", kind="person",
                    start_char=0, end_char=5,
                    confidence=0.9, source="gliner",
                ),
            ),
        )
        await ext.extract(ctx)

        call_args = provider.complete_json.call_args[0][0]
        assert isinstance(call_args, LLMRequest)
        assert "Alice (person)" in call_args.user_prompt


class TestConfidenceFiltering:
    async def test_below_threshold_filtered(self) -> None:
        response = {
            "propositions": [
                {
                    "subject_text": "X",
                    "subject_kind": "entity",
                    "predicate": "does",
                    "normalized_text": "X does Y",
                    "frame_type": "relationship",
                    "stance": "asserts",
                    "attestation_strength": "inference",
                    "confidence": 0.3,
                },
                {
                    "subject_text": "A",
                    "subject_kind": "entity",
                    "predicate": "is",
                    "normalized_text": "A is B",
                    "frame_type": "classification",
                    "stance": "asserts",
                    "attestation_strength": "direct_statement",
                    "confidence": 0.8,
                },
            ],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider, min_confidence=0.5)
        ctx = _make_ctx("X does Y. A is B.")
        result = await ext.extract(ctx)

        assert len(result.frames) == 1
        assert result.frames[0].subject.text == "A"

    async def test_custom_min_confidence(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "X",
                "subject_kind": "entity",
                "predicate": "does",
                "normalized_text": "X does Y",
                "frame_type": "relationship",
                "stance": "asserts",
                "attestation_strength": "inference",
                "confidence": 0.3,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider, min_confidence=0.2)
        ctx = _make_ctx("X does Y.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 1


class TestErrorHandling:
    async def test_llm_call_failure(self) -> None:
        provider = AsyncMock()
        provider.complete_json = AsyncMock(side_effect=RuntimeError("API error"))
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("Some text here.")
        result = await ext.extract(ctx)

        assert len(result.frames) == 0
        assert len(result.signals) == 1
        assert result.signals[0].signal_type == "llm_error"

    async def test_invalid_response_format(self) -> None:
        provider = _mock_provider({"not_propositions": True})
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("Some text.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0

    async def test_non_list_propositions(self) -> None:
        provider = _mock_provider({"propositions": "invalid"})
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("Some text.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0

    async def test_non_dict_proposition_entry(self) -> None:
        provider = _mock_provider({"propositions": ["not a dict", 42]})
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("Some text.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0

    async def test_hallucinated_subject_rejected(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "NonExistentEntity",
                "subject_kind": "entity",
                "predicate": "does",
                "normalized_text": "NonExistentEntity does something",
                "frame_type": "relationship",
                "confidence": 0.9,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("The actual text has nothing matching.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0

    async def test_invalid_confidence_skipped(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "X",
                "subject_kind": "entity",
                "predicate": "does",
                "normalized_text": "X does",
                "frame_type": "relationship",
                "confidence": "not_a_number",
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("X does Y.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0

    async def test_non_dict_qualifiers_handled(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "X",
                "subject_kind": "entity",
                "predicate": "does",
                "normalized_text": "X does Y",
                "frame_type": "relationship",
                "confidence": 0.9,
                "qualifiers": "invalid_string",
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("X does Y.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 1
        assert result.frames[0].qualifiers == {}

    async def test_missing_subject_text(self) -> None:
        response = {
            "propositions": [{
                "predicate": "does",
                "normalized_text": "does something",
                "frame_type": "relationship",
                "confidence": 0.9,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("Some text.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0

    async def test_wrapped_answer_response(self) -> None:
        import json

        inner = json.dumps({
            "propositions": [{
                "subject_text": "X",
                "subject_kind": "entity",
                "predicate": "is",
                "normalized_text": "X is Y",
                "frame_type": "classification",
                "stance": "asserts",
                "attestation_strength": "direct_statement",
                "confidence": 0.9,
            }],
        })
        provider = _mock_provider({"answer": inner})
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("X is Y.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 1

    async def test_wrapped_answer_unparseable(self) -> None:
        provider = _mock_provider({"answer": "not json at all"})
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("X is Y.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0


class TestEnumValidation:
    async def test_invalid_frame_type_defaults(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "X",
                "subject_kind": "entity",
                "predicate": "does",
                "normalized_text": "X does Y",
                "frame_type": "nonexistent_type",
                "stance": "asserts",
                "attestation_strength": "direct_statement",
                "confidence": 0.9,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("X does Y.")
        result = await ext.extract(ctx)
        assert result.frames[0].frame_type == "relationship"

    async def test_invalid_stance_defaults(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "X",
                "subject_kind": "entity",
                "predicate": "does",
                "normalized_text": "X does Y",
                "frame_type": "relationship",
                "stance": "bogus_stance",
                "attestation_strength": "direct_statement",
                "confidence": 0.9,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("X does Y.")
        result = await ext.extract(ctx)
        assert result.frames[0].stance == "asserts"

    async def test_invalid_attestation_defaults(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "X",
                "subject_kind": "entity",
                "predicate": "does",
                "normalized_text": "X does Y",
                "frame_type": "relationship",
                "stance": "asserts",
                "attestation_strength": "made_up",
                "confidence": 0.9,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("X does Y.")
        result = await ext.extract(ctx)
        assert result.frames[0].attestation_strength == "inference"


class TestOffsetCalculation:
    async def test_subject_offset_with_start_char(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "Seller",
                "subject_kind": "party",
                "predicate": "deliver",
                "normalized_text": "Seller deliver",
                "frame_type": "obligation",
                "stance": "asserts",
                "attestation_strength": "direct_statement",
                "confidence": 0.9,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("The Seller shall deliver.", start_char=200)
        result = await ext.extract(ctx)

        frame = result.frames[0]
        assert frame.subject.start_char == 204  # "The " = 4 chars + 200
        assert frame.subject.end_char == 210

    async def test_object_offset_with_start_char(self) -> None:
        response = {
            "propositions": [{
                "subject_text": "Alice",
                "subject_kind": "person",
                "predicate": "works_at",
                "object_text": "Acme",
                "object_kind": "organization",
                "normalized_text": "Alice works at Acme",
                "frame_type": "relationship",
                "stance": "asserts",
                "attestation_strength": "direct_statement",
                "confidence": 0.9,
            }],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("Alice works at Acme Corp.", start_char=50)
        result = await ext.extract(ctx)

        assert result.frames[0].object is not None
        assert result.frames[0].object.start_char == 65  # 15 + 50


class TestFindExactSpan:
    def test_exact_match(self) -> None:
        assert _find_exact_span("Hello World", "World") == (6, 11)

    def test_case_insensitive_fallback(self) -> None:
        assert _find_exact_span("Hello World", "world") == (6, 11)

    def test_not_found_returns_none(self) -> None:
        assert _find_exact_span("Hello World", "Missing") is None


class TestSignalOutput:
    async def test_signal_per_proposition(self) -> None:
        response = {
            "propositions": [
                {
                    "subject_text": "A",
                    "subject_kind": "entity",
                    "predicate": "is",
                    "normalized_text": "A is B",
                    "frame_type": "classification",
                    "stance": "asserts",
                    "attestation_strength": "direct_statement",
                    "confidence": 0.9,
                },
                {
                    "subject_text": "C",
                    "subject_kind": "entity",
                    "predicate": "does",
                    "normalized_text": "C does D",
                    "frame_type": "relationship",
                    "stance": "asserts",
                    "attestation_strength": "inference",
                    "confidence": 0.7,
                },
            ],
        }
        provider = _mock_provider(response)
        ext = LLMExtractor(provider=provider)
        ctx = _make_ctx("A is B. C does D.")
        result = await ext.extract(ctx)

        assert len(result.signals) == 2
        assert all(s.signal_type == "llm_proposition" for s in result.signals)
        assert result.signals[0].data["predicate"] == "is"
        assert result.signals[1].data["predicate"] == "does"
