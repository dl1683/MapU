"""ML model extractors: GLiNER, GLiNER-Relex, SetFit, and SRL shell.

Models are lazily loaded on first use via LazyModelRuntime.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import types
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
    "amends": FrameType.STATUS,
    "supersedes": FrameType.STATUS,
    "requires": FrameType.OBLIGATION,
    "shall deliver": FrameType.OBLIGATION,
    "must provide": FrameType.OBLIGATION,
    "prohibits": FrameType.CONSTRAINT,
    "depends on": FrameType.DEPENDENCY,
    "uses": FrameType.DEPENDENCY,
    "reports": FrameType.MEASUREMENT,
    "increases": FrameType.MEASUREMENT,
    "decreases": FrameType.MEASUREMENT,
    "causes": FrameType.RELATIONSHIP,
    "inhibits": FrameType.RELATIONSHIP,
    "treats": FrameType.RELATIONSHIP,
}

_DEFAULT_RELATION_LABELS: tuple[str, ...] = (
    "affiliated with",
    "agrees to",
    "amends",
    "applies to",
    "causes",
    "contains",
    "depends on",
    "decreases",
    "founded by",
    "increases",
    "inhibits",
    "located in",
    "member of",
    "must provide",
    "owned by",
    "parent organization",
    "part of",
    "prohibits",
    "reports",
    "replaces",
    "requires",
    "shall deliver",
    "subsidiary",
    "supersedes",
    "treats",
    "uses",
    "works for",
)

_OBLIGATION_MODAL_RE = ("shall ", "must ", "may ")


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
            # GLiNER imports pull in transformers/datasets/pyarrow. On Windows
            # with Python 3.13, importing this stack from a worker thread can
            # trigger native access-violation crashes, so keep that import on
            # the main thread.
            if os.name == "nt" and backend in {"gliner", "gliner_relex"}:
                model = loader()
            else:
                model = await asyncio.to_thread(loader)
            self._cache[key] = model
            return model

    async def run_inference(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run inference function under concurrency limit."""
        async with self._inference_sem:
            return await asyncio.to_thread(fn, *args, **kwargs)


_GLOBAL_RUNTIME = LazyModelRuntime()


def _install_gliner_training_stub() -> None:
    """Avoid importing GLiNER training stack during inference-only usage.

    GLiNER's top-level model module imports `gliner.training` eagerly. On our
    Windows + Python 3.13 setup this cascades into `transformers.trainer ->
    datasets -> pyarrow` and can crash the process natively. In MapU we only
    need inference, so a tiny stub is sufficient.
    """
    if "gliner.training" in sys.modules:
        return

    class _StubTrainer:  # pragma: no cover - simple import shim
        pass

    class _StubTrainingArguments:  # pragma: no cover - simple import shim
        pass

    training_mod = types.ModuleType("gliner.training")
    training_mod.Trainer = _StubTrainer
    training_mod.TrainingArguments = _StubTrainingArguments
    trainer_mod = types.ModuleType("gliner.training.trainer")
    trainer_mod.Trainer = _StubTrainer
    trainer_mod.TrainingArguments = _StubTrainingArguments

    sys.modules["gliner.training"] = training_mod
    sys.modules["gliner.training.trainer"] = trainer_mod

    # Transformers may import sklearn helpers opportunistically. Force-disable
    # that probe so we avoid importing heavy sklearn/pandas/pyarrow stacks
    # during GLiNER inference startup on Windows.
    try:
        import_utils = importlib.import_module("transformers.utils.import_utils")
        if hasattr(import_utils, "_sklearn_available"):
            import_utils._sklearn_available = False  # type: ignore[attr-defined]
    except Exception:
        pass


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
            _install_gliner_training_stub()
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


class GLiNERRelexExtractor:
    """Joint zero-shot entity and relation extraction using GLiNER-Relex."""

    def __init__(
        self,
        model_id: str = "knowledgator/gliner-relex-base-v1.0",
        entity_types: tuple[str, ...] = (*_DEFAULT_ENTITY_TYPES, "other"),
        relation_labels: tuple[str, ...] = _DEFAULT_RELATION_LABELS,
        entity_threshold: float = 0.4,
        relation_threshold: float = 0.7,
        calibration_factor: float = 0.75,
        device: str = "cpu",
        runtime: LazyModelRuntime | None = None,
    ) -> None:
        self._model_id = model_id
        self._entity_types = list(entity_types)
        self._relation_labels = list(relation_labels)
        self._entity_threshold = entity_threshold
        self._relation_threshold = relation_threshold
        self._calibration_factor = calibration_factor
        self._device = device
        self._runtime = runtime or _GLOBAL_RUNTIME

    @property
    def name(self) -> str:
        return "gliner_relex"

    async def _get_model(self) -> Any:
        def _load() -> Any:
            _install_gliner_training_stub()
            from gliner import GLiNER  # type: ignore[import-untyped]
            return GLiNER.from_pretrained(self._model_id, map_location=self._device)
        return await self._runtime.get_or_load(
            "gliner_relex", self._model_id, self._device, _load,
        )

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        if not ctx.text.strip():
            return ExtractorOutput()

        model = await self._get_model()
        raw = await self._runtime.run_inference(
            model.inference,
            texts=[ctx.text],
            labels=self._entity_types,
            relations=self._relation_labels,
            threshold=self._entity_threshold,
            relation_threshold=self._relation_threshold,
            return_relations=True,
            flat_ner=False,
        )
        raw_entities, raw_relations = _unpack_relex_output(raw)

        entity_index = _build_entity_index(ctx)
        for ent in raw_entities:
            text = str(ent.get("text", ""))
            label = str(ent.get("label") or ent.get("type") or "entity").lower()
            if text:
                entity_index[text] = label

        entities: list[EntityMention] = []
        for ent in raw_entities:
            text = str(ent.get("text", ""))
            if not text:
                continue
            start, end = _entity_span(ctx.text, ent, text)
            if start == end:
                continue
            score = float(ent.get("score", 0.0)) * self._calibration_factor
            entities.append(EntityMention(
                text=text,
                kind=str(ent.get("label") or ent.get("type") or "entity").lower(),
                start_char=ctx.start_char + start,
                end_char=ctx.start_char + end,
                confidence=score,
                source=self.name,
            ))

        frames: list[PropositionFrameCandidate] = []
        signals: list[ExtractionSignal] = []

        for relation_obj in raw_relations:
            head_obj = relation_obj.get("head", {})
            tail_obj = relation_obj.get("tail", {})
            if not isinstance(head_obj, dict) or not isinstance(tail_obj, dict):
                continue

            head = str(head_obj.get("text", ""))
            tail = str(tail_obj.get("text", ""))
            relation = str(relation_obj.get("relation", ""))
            if not head or not tail or not relation:
                continue
            relation_norm = _normalize_relation_label(relation, head, tail, ctx.text)

            subject_span = _entity_span(ctx.text, head_obj, head)
            object_span = _entity_span(ctx.text, tail_obj, tail)

            if subject_span[0] == subject_span[1] or object_span[0] == object_span[1]:
                continue

            raw_confidence = float(relation_obj.get("score", 0.0))
            calibrated = raw_confidence * self._calibration_factor

            subject = EntityMention(
                text=head,
                kind=str(head_obj.get("type") or entity_index.get(head, "entity")).lower(),
                start_char=ctx.start_char + subject_span[0],
                end_char=ctx.start_char + subject_span[1],
                confidence=calibrated,
                source=self.name,
            )
            obj = EntityMention(
                text=tail,
                kind=str(tail_obj.get("type") or entity_index.get(tail, "entity")).lower(),
                start_char=ctx.start_char + object_span[0],
                end_char=ctx.start_char + object_span[1],
                confidence=calibrated,
                source=self.name,
            )

            frame_type = _RELATION_TO_FRAME_TYPE.get(
                relation_norm, FrameType.RELATIONSHIP,
            )
            if _reject_malformed_obligation_object(relation_norm, obj):
                continue
            frames.append(PropositionFrameCandidate(
                span_id=ctx.span_id,
                frame_type=frame_type,
                subject=subject,
                predicate=relation_norm.replace(" ", "_"),
                object=obj,
                value=None,
                polarity=True,
                modality=_infer_modality(relation_norm),
                valid_range=None,
                normalized_text=f"{head} {relation_norm} {tail}",
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
                    "relation": relation_norm,
                    "tail": tail,
                    "raw_confidence": raw_confidence,
                    "calibrated_confidence": calibrated,
                    "model_id": self._model_id,
                },
                start_char=ctx.start_char + sig_start,
                end_char=ctx.start_char + sig_end,
                source=self.name,
            ))

        return ExtractorOutput(
            entities=tuple(entities),
            frames=tuple(frames),
            signals=tuple(signals),
        )


def _unpack_relex_output(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize GLiNER-Relex return shapes to first-text entities and relations."""
    if not isinstance(raw, tuple) or len(raw) != 2:
        return [], []
    entities, relations = raw
    if not isinstance(entities, list) or not isinstance(relations, list):
        return [], []
    first_entities = entities[0] if entities and isinstance(entities[0], list) else entities
    first_relations = relations[0] if relations and isinstance(relations[0], list) else relations
    return (
        [e for e in first_entities if isinstance(e, dict)],
        [r for r in first_relations if isinstance(r, dict)],
    )


def _entity_span(text: str, entity: dict[str, Any], fallback_text: str) -> tuple[int, int]:
    start = entity.get("start")
    end = entity.get("end")
    if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int):
        if 0 <= start < end <= len(text):
            return start, end
    return _find_span(text, fallback_text)


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


def _normalize_relation_label(relation: str, head: str, tail: str, full_text: str) -> str:
    r = " ".join(relation.lower().split())
    text = full_text.lower()
    # Force modality-aware normalization when the source sentence expresses it.
    if f"{head.lower()} shall " in text and tail.lower() in text:
        return "shall deliver"
    if f"{head.lower()} must " in text and tail.lower() in text:
        return "must provide"
    if f"{head.lower()} may " in text and tail.lower() in text:
        return "may request"
    if any(r.startswith(m.strip()) for m in _OBLIGATION_MODAL_RE):
        return r
    if r == "reports":
        # Avoid misclassifying contractual delivery statements as measurement reports.
        if "shall" in text or "must" in text or "obligation" in text:
            return "shall deliver"
    return r


def _infer_modality(relation_norm: str) -> str | None:
    if relation_norm.startswith("shall ") or relation_norm.startswith("must "):
        return "obligation"
    if relation_norm.startswith("may "):
        return "permission"
    return None


def _reject_malformed_obligation_object(relation_norm: str, obj: EntityMention) -> bool:
    if not relation_norm.startswith(("shall ", "must ", "requires")):
        return False
    obj_text = obj.text.lower()
    obj_kind = (obj.kind or "").lower()
    # Contractual obligations usually target deliverables/artifacts/events, not counterparty entities.
    # Keep organization objects only when there is explicit recipient phrasing in the object itself.
    if obj_kind in {"organization", "person"}:
        if any(tok in obj_text for tok in ("report", "statement", "notice", "document", "payment", "deliverable")):
            return False
        if any(tok in obj_text for tok in (" to ", "for ", "within ", "by ")):
            return False
        return True
    return False
