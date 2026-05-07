"""ML model extractors: GLiNER, REBEL, SetFit, and SRL shell.

Models are lazily loaded on first use via LazyModelRuntime.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from mapu.extraction.types import (
    EntityMention,
    ExtractionContext,
    ExtractionSignal,
    ExtractorOutput,
    PropositionFrameCandidate,
)
from mapu.types import AttestationStrength, FrameType, Stance

_DEFAULT_ENTITY_TYPES: tuple[str, ...] = (
    "person",
    "organization",
    "location",
    "date",
    "legal_concept",
    "defined_term",
    "document_type",
    "jurisdiction",
    "monetary_amount",
    "percentage",
    "duration",
)

_VALID_FRAME_LABELS: frozenset[str] = frozenset(ft.value for ft in FrameType)

_REBEL_TRIPLET_RE = re.compile(
    r"<triplet>\s*(.*?)\s*<subj>\s*(.*?)\s*<obj>\s*(.*?)\s*(?=<triplet>|$)"
)

_RELATION_TO_FRAME_TYPE: dict[str, FrameType] = {
    "instance of": FrameType.CLASSIFICATION,
    "subclass of": FrameType.CLASSIFICATION,
    "part of": FrameType.RELATIONSHIP,
    "has part": FrameType.RELATIONSHIP,
    "located in": FrameType.RELATIONSHIP,
    "member of": FrameType.RELATIONSHIP,
    "owned by": FrameType.RELATIONSHIP,
    "parent organization": FrameType.RELATIONSHIP,
    "subsidiary": FrameType.RELATIONSHIP,
    "founded by": FrameType.EVENT,
    "inception": FrameType.EVENT,
    "occupation": FrameType.CLASSIFICATION,
    "creator": FrameType.RELATIONSHIP,
    "manufacturer": FrameType.RELATIONSHIP,
    "applies to jurisdiction": FrameType.CONSTRAINT,
    "replaces": FrameType.STATUS,
}


class LazyModelRuntime:
    """Process-lifetime model cache. Keyed by (backend, model_id, device)."""

    def __init__(self, max_concurrent_inference: int = 2) -> None:
        self._cache: dict[tuple[str, str, str], Any] = {}
        self._locks: dict[tuple[str, str, str], asyncio.Lock] = {}
        self._inference_sem = asyncio.Semaphore(max_concurrent_inference)

    async def get_or_load(
        self,
        backend: str,
        model_id: str,
        device: str,
        loader: Any,
    ) -> Any:
        key = (backend, model_id, device)
        if key in self._cache:
            return self._cache[key]
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        async with self._locks[key]:
            if key in self._cache:
                return self._cache[key]
            model = await asyncio.to_thread(loader)
            self._cache[key] = model
            return model

    async def run_inference(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run inference function under concurrency limit."""
        async with self._inference_sem:
            return await asyncio.to_thread(fn, *args, **kwargs)


_GLOBAL_RUNTIME = LazyModelRuntime()


class GLiNERExtractor:
    """Zero-shot entity extractor using GLiNER models."""

    def __init__(
        self,
        model_id: str = "urchade/gliner_small-v2.1",
        entity_types: tuple[str, ...] = _DEFAULT_ENTITY_TYPES,
        threshold: float = 0.5,
        calibration_factor: float = 0.75,
        device: str = "cpu",
        runtime: LazyModelRuntime | None = None,
    ) -> None:
        self._model_id = model_id
        self._entity_types = list(entity_types)
        self._threshold = threshold
        self._calibration_factor = calibration_factor
        self._device = device
        self._runtime = runtime or _GLOBAL_RUNTIME

    @property
    def name(self) -> str:
        return "gliner"

    async def _get_model(self) -> Any:
        def _load() -> Any:
            from gliner import GLiNER  # type: ignore[import-untyped]
            return GLiNER.from_pretrained(self._model_id, map_location=self._device)
        return await self._runtime.get_or_load(
            "gliner", self._model_id, self._device, _load,
        )

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        if not ctx.text.strip():
            return ExtractorOutput()

        model = await self._get_model()
        raw_entities: list[dict[str, Any]] = await self._runtime.run_inference(
            model.predict_entities,
            ctx.text,
            self._entity_types,
            threshold=self._threshold,
        )

        entities: list[EntityMention] = []
        signals: list[ExtractionSignal] = []

        for ent in raw_entities:
            raw_score = float(ent.get("score", 0.0))
            calibrated = raw_score * self._calibration_factor
            start = int(ent.get("start", 0))
            end = int(ent.get("end", 0))
            text = str(ent.get("text", ctx.text[start:end]))
            label = str(ent.get("label", "unknown")).lower()

            mention = EntityMention(
                text=text,
                kind=label,
                start_char=ctx.start_char + start,
                end_char=ctx.start_char + end,
                confidence=calibrated,
                source=self.name,
            )
            entities.append(mention)
            signals.append(ExtractionSignal(
                signal_type="entity",
                data={
                    "text": text,
                    "kind": label,
                    "raw_score": raw_score,
                    "calibrated_score": calibrated,
                    "model_id": self._model_id,
                },
                start_char=ctx.start_char + start,
                end_char=ctx.start_char + end,
                source=self.name,
            ))

        return ExtractorOutput(entities=tuple(entities), signals=tuple(signals))


class SetFitExtractor:
    """Classifies text spans by proposition frame type using SetFit."""

    def __init__(
        self,
        model_id: str = "sentence-transformers/paraphrase-MiniLM-L3-v2",
        trained_model_path: str | None = None,
        confidence_threshold: float = 0.5,
        device: str = "cpu",
        runtime: LazyModelRuntime | None = None,
    ) -> None:
        self._model_id = model_id
        self._trained_path = trained_model_path
        self._confidence_threshold = confidence_threshold
        self._device = device
        self._runtime = runtime or _GLOBAL_RUNTIME

    @property
    def name(self) -> str:
        return "setfit"

    async def _get_model(self) -> Any:
        path = self._trained_path or self._model_id
        device = self._device
        def _load() -> Any:
            from setfit import SetFitModel  # type: ignore[import-untyped]
            model = SetFitModel.from_pretrained(path)
            model.to(device)
            return model
        return await self._runtime.get_or_load(
            "setfit", path, self._device, _load,
        )

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        if not ctx.text.strip():
            return ExtractorOutput()

        model = await self._get_model()
        predicted_label, confidence = await self._classify(model, ctx.text)
        if predicted_label is None:
            return ExtractorOutput()
        if predicted_label not in _VALID_FRAME_LABELS:
            return ExtractorOutput()
        if confidence < self._confidence_threshold:
            return ExtractorOutput()

        return ExtractorOutput(
            signals=(
                ExtractionSignal(
                    signal_type="frame_classification",
                    data={
                        "predicted_frame_type": predicted_label,
                        "confidence": confidence,
                        "model_id": self._trained_path or self._model_id,
                    },
                    start_char=ctx.start_char,
                    end_char=ctx.end_char,
                    source=self.name,
                ),
            ),
        )

    async def _classify(
        self, model: Any, text: str,
    ) -> tuple[str | None, float]:
        try:
            probs = await self._runtime.run_inference(model.predict_proba, [text])
            if hasattr(probs, '__getitem__') and hasattr(model, 'labels'):
                prob_list = probs[0].tolist() if hasattr(probs[0], 'tolist') else list(probs[0])
                labels = list(model.labels)
                if len(labels) == len(prob_list):
                    best_idx = prob_list.index(max(prob_list))
                    return labels[best_idx], float(prob_list[best_idx])
        except Exception:
            pass
        try:
            predictions = await self._runtime.run_inference(model.predict, [text])
            if hasattr(predictions, '__len__') and len(predictions) > 0:
                return str(predictions[0]), 0.5
        except Exception:
            pass
        return None, 0.0


def parse_rebel_output(generated_text: str) -> list[dict[str, str]]:
    """Parse REBEL seq2seq output into triplet dicts.

    REBEL format: <triplet> SUBJECT <subj> OBJECT <obj> RELATION
    """
    triplets: list[dict[str, str]] = []
    for match in _REBEL_TRIPLET_RE.finditer(generated_text):
        head = match.group(1).strip()
        tail = match.group(2).strip()
        relation = match.group(3).strip()
        if head and relation and tail:
            triplets.append({"head": head, "relation": relation, "tail": tail})
    return triplets


class REBELExtractor:
    """Relation extraction using REBEL (seq2seq triplet generation).

    Note: Babelscape/rebel-large is CC-BY-NC-SA-4.0. This extractor is
    optional and should not be a hard default for commercial deployments.
    """

    def __init__(
        self,
        model_id: str = "Babelscape/rebel-large",
        calibration_factor: float = 0.65,
        max_length: int = 256,
        device: int = -1,
        runtime: LazyModelRuntime | None = None,
    ) -> None:
        self._model_id = model_id
        self._calibration_factor = calibration_factor
        self._max_length = max_length
        self._device = device
        self._runtime = runtime or _GLOBAL_RUNTIME

    @property
    def name(self) -> str:
        return "rebel"

    async def _get_pipeline(self) -> Any:
        dev = self._device
        def _load() -> Any:
            from transformers import pipeline
            return pipeline(
                "text2text-generation",
                model=self._model_id,
                device=dev,
                max_length=self._max_length,
            )
        device_key = str(self._device)
        return await self._runtime.get_or_load(
            "rebel", self._model_id, device_key, _load,
        )

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        if not ctx.text.strip():
            return ExtractorOutput()

        pipe = await self._get_pipeline()
        outputs: list[dict[str, Any]] = await self._runtime.run_inference(
            pipe, ctx.text, return_text=True, return_tensors=False,
        )
        generated = outputs[0].get("generated_text", "") if outputs else ""
        raw_triplets = parse_rebel_output(generated)

        entity_index = _build_entity_index(ctx)
        frames: list[PropositionFrameCandidate] = []
        signals: list[ExtractionSignal] = []

        for triplet in raw_triplets:
            head = triplet["head"]
            relation = triplet["relation"]
            tail = triplet["tail"]

            subject_span = _find_span(ctx.text, head)
            object_span = _find_span(ctx.text, tail)

            if subject_span == (0, 0) or object_span == (0, 0):
                continue

            raw_confidence = 0.8 if (head in entity_index or tail in entity_index) else 0.7
            calibrated = raw_confidence * self._calibration_factor

            subject = EntityMention(
                text=head,
                kind=entity_index.get(head, "entity"),
                start_char=ctx.start_char + subject_span[0],
                end_char=ctx.start_char + subject_span[1],
                confidence=calibrated,
                source=self.name,
            )
            obj = EntityMention(
                text=tail,
                kind=entity_index.get(tail, "entity"),
                start_char=ctx.start_char + object_span[0],
                end_char=ctx.start_char + object_span[1],
                confidence=calibrated,
                source=self.name,
            )

            frame_type = _RELATION_TO_FRAME_TYPE.get(
                relation.lower(), FrameType.RELATIONSHIP,
            )
            frames.append(PropositionFrameCandidate(
                span_id=ctx.span_id,
                frame_type=frame_type,
                subject=subject,
                predicate=relation.lower().replace(" ", "_"),
                object=obj,
                value=None,
                polarity=True,
                modality=None,
                valid_range=None,
                normalized_text=f"{head} {relation} {tail}",
                qualifiers={},
                stance=Stance.ASSERTS,
                attestation_strength=AttestationStrength.INFERENCE,
                extraction_method=self.name,
                extraction_confidence=calibrated,
            ))
            sig_start = min(subject_span[0], object_span[0])
            sig_end = max(subject_span[1], object_span[1])
            signals.append(ExtractionSignal(
                signal_type="relation",
                data={
                    "head": head,
                    "relation": relation,
                    "tail": tail,
                    "raw_confidence": raw_confidence,
                    "calibrated_confidence": calibrated,
                },
                start_char=ctx.start_char + sig_start,
                end_char=ctx.start_char + sig_end,
                source=self.name,
            ))

        return ExtractorOutput(frames=tuple(frames), signals=tuple(signals))


class SRLExtractor:
    """Semantic role labeling shell — disabled by default.

    Maintained HuggingFace SRL models compatible with Python 3.12+ are not
    yet available. This adapter implements the Extractor protocol as a no-op
    for testing and pipeline wiring.
    """

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    @property
    def name(self) -> str:
        return "srl"

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        if not self._enabled:
            return ExtractorOutput()
        return ExtractorOutput()


def _build_entity_index(ctx: ExtractionContext) -> dict[str, str]:
    """Build text→kind index from prior entities and base parse."""
    index: dict[str, str] = {}
    for ent in ctx.prior_entities:
        index[ent.text] = ent.kind
    for signal in ctx.prior_signals:
        if signal.signal_type == "entity":
            text = signal.data.get("text", "")
            kind = signal.data.get("kind", "unknown")
            if text:
                index[text] = kind
    if ctx.base_parse is not None:
        for ent in ctx.base_parse.entities:
            index[ent.text] = ent.kind
    return index


def _find_span(text: str, target: str) -> tuple[int, int]:
    """Find character span of target in text (case-insensitive)."""
    idx = text.lower().find(target.lower())
    if idx >= 0:
        return (idx, idx + len(target))
    return (0, 0)
