"""Unit tests for ML model extractors: GLiNER, REBEL, SetFit, SRL."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from mapu.extraction.ml import (
    GLiNERExtractor,
    LazyModelRuntime,
    REBELExtractor,
    SetFitExtractor,
    SRLExtractor,
    parse_rebel_output,
)
from mapu.extraction.types import ExtractionContext, ExtractionSignal


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


class TestGLiNERExtractor:
    def test_name(self) -> None:
        ext = GLiNERExtractor()
        assert ext.name == "gliner"

    async def test_empty_text(self) -> None:
        ext = GLiNERExtractor()
        ctx = _make_ctx("")
        result = await ext.extract(ctx)
        assert len(result.signals) == 0
        assert len(result.entities) == 0

    async def test_extract_produces_entities_and_signals(self) -> None:
        runtime = LazyModelRuntime()
        mock_model = MagicMock()
        mock_model.predict_entities.return_value = [
            {"text": "Acme Corp", "label": "organization", "start": 0, "end": 9, "score": 0.92},
            {"text": "New York", "label": "location", "start": 25, "end": 33, "score": 0.88},
        ]
        runtime._cache[("gliner", "urchade/gliner_small-v2.1", "cpu")] = mock_model

        ext = GLiNERExtractor(calibration_factor=0.75, runtime=runtime)
        ctx = _make_ctx("Acme Corp is headquartered in New York.")
        result = await ext.extract(ctx)

        assert len(result.entities) == 2
        assert len(result.signals) == 2
        assert result.entities[0].text == "Acme Corp"
        assert result.entities[0].kind == "organization"
        assert result.entities[0].confidence == pytest.approx(0.92 * 0.75, abs=0.01)
        assert result.signals[0].signal_type == "entity"

    async def test_calibration_applied(self) -> None:
        runtime = LazyModelRuntime()
        mock_model = MagicMock()
        mock_model.predict_entities.return_value = [
            {"text": "X", "label": "person", "start": 0, "end": 1, "score": 1.0},
        ]
        runtime._cache[("gliner", "urchade/gliner_small-v2.1", "cpu")] = mock_model

        ext = GLiNERExtractor(calibration_factor=0.5, runtime=runtime)
        ctx = _make_ctx("X did something.")
        result = await ext.extract(ctx)
        assert result.entities[0].confidence == pytest.approx(0.5)

    async def test_offset_adjustment(self) -> None:
        runtime = LazyModelRuntime()
        mock_model = MagicMock()
        mock_model.predict_entities.return_value = [
            {"text": "Alice", "label": "person", "start": 0, "end": 5, "score": 0.9},
        ]
        runtime._cache[("gliner", "urchade/gliner_small-v2.1", "cpu")] = mock_model

        ext = GLiNERExtractor(runtime=runtime)
        ctx = ExtractionContext(
            corpus_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            expression_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            node_id=None,
            text="Alice went home.",
            start_char=100,
            end_char=116,
        )
        result = await ext.extract(ctx)
        assert result.entities[0].start_char == 100
        assert result.entities[0].end_char == 105


class TestREBELOutputParsing:
    def test_parse_single_triplet(self) -> None:
        text = "<triplet> Barack Obama <subj> United States <obj> president of"
        triplets = parse_rebel_output(text)
        assert len(triplets) == 1
        assert triplets[0]["head"] == "Barack Obama"
        assert triplets[0]["relation"] == "president of"
        assert triplets[0]["tail"] == "United States"

    def test_parse_multiple_triplets(self) -> None:
        text = (
            "<triplet> Paris <subj> France <obj> capital of "
            "<triplet> France <subj> Europe <obj> located in"
        )
        triplets = parse_rebel_output(text)
        assert len(triplets) == 2

    def test_parse_empty(self) -> None:
        assert parse_rebel_output("") == []

    def test_parse_no_triplets(self) -> None:
        assert parse_rebel_output("just some text") == []


class TestREBELExtractor:
    def test_name(self) -> None:
        ext = REBELExtractor()
        assert ext.name == "rebel"

    async def test_empty_text(self) -> None:
        ext = REBELExtractor()
        ctx = _make_ctx("")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0

    async def test_extract_produces_frames(self) -> None:
        runtime = LazyModelRuntime()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [
            {"generated_text": "<triplet> Acme Corp <subj> New York <obj> headquartered in"},
        ]
        runtime._cache[("rebel", "Babelscape/rebel-large", "-1")] = mock_pipe

        ext = REBELExtractor(calibration_factor=0.65, runtime=runtime)
        ctx = _make_ctx("Acme Corp is headquartered in New York.")
        result = await ext.extract(ctx)

        assert len(result.frames) == 1
        assert result.frames[0].subject.text == "Acme Corp"
        assert result.frames[0].object is not None
        assert result.frames[0].object.text == "New York"
        assert result.frames[0].predicate == "headquartered_in"
        assert result.frames[0].extraction_method == "rebel"

    async def test_relation_signal_emitted(self) -> None:
        runtime = LazyModelRuntime()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [
            {"generated_text": "<triplet> X <subj> Y <obj> works for"},
        ]
        runtime._cache[("rebel", "Babelscape/rebel-large", "-1")] = mock_pipe

        ext = REBELExtractor(runtime=runtime)
        ctx = _make_ctx("X works for Y.")
        result = await ext.extract(ctx)

        assert len(result.signals) == 1
        assert result.signals[0].signal_type == "relation"
        assert result.signals[0].data["head"] == "X"

    async def test_entity_index_from_prior_entities(self) -> None:
        from mapu.extraction.types import EntityMention

        runtime = LazyModelRuntime()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [
            {"generated_text": "<triplet> Alice <subj> Acme <obj> works for"},
        ]
        runtime._cache[("rebel", "Babelscape/rebel-large", "-1")] = mock_pipe

        ext = REBELExtractor(runtime=runtime)
        ctx = ExtractionContext(
            corpus_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            expression_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            node_id=None,
            text="Alice works for Acme.",
            start_char=0,
            end_char=21,
            prior_entities=(
                EntityMention(
                    text="Alice", kind="person",
                    start_char=0, end_char=5, confidence=0.9, source="gliner",
                ),
            ),
        )
        result = await ext.extract(ctx)
        assert result.frames[0].subject.kind == "person"

    async def test_entity_index_from_prior_signals(self) -> None:
        runtime = LazyModelRuntime()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [
            {"generated_text": "<triplet> Bob <subj> Paris <obj> lives in"},
        ]
        runtime._cache[("rebel", "Babelscape/rebel-large", "-1")] = mock_pipe

        ext = REBELExtractor(runtime=runtime)
        ctx = ExtractionContext(
            corpus_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            expression_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            node_id=None,
            text="Bob lives in Paris.",
            start_char=0,
            end_char=19,
            prior_signals=(
                ExtractionSignal(
                    signal_type="entity",
                    data={"text": "Bob", "kind": "person"},
                    source="gliner",
                ),
            ),
        )
        result = await ext.extract(ctx)
        assert result.frames[0].subject.kind == "person"

    async def test_ungrounded_entities_skipped(self) -> None:
        runtime = LazyModelRuntime()
        mock_pipe = MagicMock()
        gen = "<triplet> FooBarNotInText <subj> BazQuxNotInText <obj> some relation"
        mock_pipe.return_value = [{"generated_text": gen}]
        runtime._cache[("rebel", "Babelscape/rebel-large", "-1")] = mock_pipe

        ext = REBELExtractor(runtime=runtime)
        ctx = _make_ctx("Something completely different here.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0
        assert len(result.signals) == 0

    async def test_partially_ungrounded_skipped(self) -> None:
        runtime = LazyModelRuntime()
        mock_pipe = MagicMock()
        gen = "<triplet> Alice <subj> NonexistentEntity <obj> works for"
        mock_pipe.return_value = [{"generated_text": gen}]
        runtime._cache[("rebel", "Babelscape/rebel-large", "-1")] = mock_pipe

        ext = REBELExtractor(runtime=runtime)
        ctx = _make_ctx("Alice works at a company.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0
        assert len(result.signals) == 0

    async def test_signal_offsets_ordered(self) -> None:
        runtime = LazyModelRuntime()
        mock_pipe = MagicMock()
        mock_pipe.return_value = [
            {"generated_text": "<triplet> York <subj> New <obj> located in"},
        ]
        runtime._cache[("rebel", "Babelscape/rebel-large", "-1")] = mock_pipe

        ext = REBELExtractor(runtime=runtime)
        ctx = _make_ctx("New York is a city.")
        result = await ext.extract(ctx)
        if result.signals:
            assert result.signals[0].start_char <= result.signals[0].end_char


class TestSetFitExtractor:
    def test_name(self) -> None:
        ext = SetFitExtractor()
        assert ext.name == "setfit"

    async def test_empty_text(self) -> None:
        ext = SetFitExtractor()
        ctx = _make_ctx("")
        result = await ext.extract(ctx)
        assert len(result.signals) == 0

    async def test_classification_produces_signal(self) -> None:
        runtime = LazyModelRuntime()
        mock_model = MagicMock()
        mock_model.predict.return_value = ["obligation"]
        mock_model.predict_proba.return_value = MagicMock(
            __getitem__=lambda self, i: MagicMock(
                tolist=lambda: [0.1, 0.8, 0.1]
            ),
        )
        mock_model.labels = ["definition", "obligation", "finding"]
        cache_key = ("setfit", "sentence-transformers/paraphrase-MiniLM-L3-v2", "cpu")
        runtime._cache[cache_key] = mock_model

        ext = SetFitExtractor(confidence_threshold=0.5, runtime=runtime)
        ctx = _make_ctx("The Seller shall deliver goods within 30 days.")
        result = await ext.extract(ctx)

        assert len(result.signals) == 1
        assert result.signals[0].signal_type == "frame_classification"
        assert result.signals[0].data["predicted_frame_type"] == "obligation"

    async def test_low_confidence_filtered(self) -> None:
        runtime = LazyModelRuntime()
        mock_model = MagicMock()
        mock_model.predict.return_value = ["obligation"]
        mock_model.predict_proba.side_effect = AttributeError()
        cache_key = ("setfit", "sentence-transformers/paraphrase-MiniLM-L3-v2", "cpu")
        runtime._cache[cache_key] = mock_model

        ext = SetFitExtractor(confidence_threshold=0.9, runtime=runtime)
        ctx = _make_ctx("Some ambiguous text.")
        result = await ext.extract(ctx)
        assert len(result.signals) == 0

    async def test_invalid_label_filtered(self) -> None:
        runtime = LazyModelRuntime()
        mock_model = MagicMock()
        mock_model.predict.return_value = ["not_a_real_frame_type"]
        mock_model.predict_proba.side_effect = AttributeError()
        cache_key = ("setfit", "sentence-transformers/paraphrase-MiniLM-L3-v2", "cpu")
        runtime._cache[cache_key] = mock_model

        ext = SetFitExtractor(confidence_threshold=0.1, runtime=runtime)
        ctx = _make_ctx("Something or other.")
        result = await ext.extract(ctx)
        assert len(result.signals) == 0


class TestSRLExtractor:
    def test_name(self) -> None:
        ext = SRLExtractor()
        assert ext.name == "srl"

    async def test_disabled_by_default(self) -> None:
        ext = SRLExtractor()
        ctx = _make_ctx("The company must deliver products.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0
        assert len(result.signals) == 0

    async def test_explicitly_disabled(self) -> None:
        ext = SRLExtractor(enabled=False)
        ctx = _make_ctx("Any text here.")
        result = await ext.extract(ctx)
        assert len(result.frames) == 0


class TestLazyModelRuntime:
    async def test_caches_model(self) -> None:
        runtime = LazyModelRuntime()
        call_count = 0

        def loader() -> str:
            nonlocal call_count
            call_count += 1
            return "model_instance"

        m1 = await runtime.get_or_load("test", "model_a", "cpu", loader)
        m2 = await runtime.get_or_load("test", "model_a", "cpu", loader)
        assert m1 == "model_instance"
        assert m1 is m2
        assert call_count == 1

    async def test_different_keys_load_separately(self) -> None:
        runtime = LazyModelRuntime()
        m1 = await runtime.get_or_load("test", "a", "cpu", lambda: "model_a")
        m2 = await runtime.get_or_load("test", "b", "cpu", lambda: "model_b")
        assert m1 == "model_a"
        assert m2 == "model_b"
