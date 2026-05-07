"""Query intent classification: heuristic baseline with SetFit upgrade path."""

from __future__ import annotations

import logging
import re
from typing import Any

from mapu.query.types import QueryIntent

logger = logging.getLogger(__name__)

_IDENTITY_PATTERNS = (
    re.compile(r"^(who|what)\s+is\b", re.IGNORECASE),
    re.compile(r"^define\b", re.IGNORECASE),
    re.compile(r"^tell me about\b", re.IGNORECASE),
)

_LIST_PATTERNS = (
    re.compile(r"^(what are all|list|show me every|show all|enumerate)\b", re.IGNORECASE),
    re.compile(r"\ball the\b.*\?$", re.IGNORECASE),
)

_TEMPORAL_PATTERNS = (
    re.compile(r"^when\b", re.IGNORECASE),
    re.compile(r"\bat time\b|\bas of\b|\bin (\d{4}|january|february|march)", re.IGNORECASE),
    re.compile(r"what was true", re.IGNORECASE),
)

_TEMPORAL_DIFF_PATTERNS = (
    re.compile(r"\bchange[ds]?\b.*\bbetween\b", re.IGNORECASE),
    re.compile(r"\bdiffer|compare|before and after\b", re.IGNORECASE),
    re.compile(r"how (did|does|has).*change", re.IGNORECASE),
)

_MEASUREMENT_PATTERNS = (
    re.compile(r"^(how much|how many|what is the value)\b", re.IGNORECASE),
    re.compile(r"\bpercentage\b|\b\$\d|\bamount\b|\btotal\b", re.IGNORECASE),
    re.compile(r"\b(fee|price|cost|rate|salary|revenue|payment)\b", re.IGNORECASE),
)

_GAP_PATTERNS = (
    re.compile(r"what('s| is) missing", re.IGNORECASE),
    re.compile(r"what don.?t we know", re.IGNORECASE),
    re.compile(r"evidence.*(lack|missing|gap)", re.IGNORECASE),
)

_CROSS_DOC_PATTERNS = (
    re.compile(r"\bin document\b.*\baffect\b|\bacross\b.*\bdocument", re.IGNORECASE),
    re.compile(r"(amendment|addendum).*\b(original|base)\b", re.IGNORECASE),
)

_INVESTIGATION_PATTERNS = (
    re.compile(r"^why\b", re.IGNORECASE),
    re.compile(r"^what caused\b", re.IGNORECASE),
    re.compile(r"\bconsistent\b.*\bacross\b", re.IGNORECASE),
)

_RELATIONSHIP_PATTERNS = (
    re.compile(r"how does.*relate", re.IGNORECASE),
    re.compile(r"(what is the|what's the) (connection|relationship|link)", re.IGNORECASE),
)


class HeuristicIntentClassifier:
    """Rule-based intent classifier. Serves as baseline until SetFit is trained."""

    @property
    def name(self) -> str:
        return "heuristic"

    async def classify(self, question: str) -> tuple[QueryIntent, float]:
        q = question.strip()
        if not q:
            return QueryIntent.IDENTITY, 0.1

        for pattern in _TEMPORAL_DIFF_PATTERNS:
            if pattern.search(q):
                return QueryIntent.TEMPORAL_DIFF, 0.85

        for pattern in _CROSS_DOC_PATTERNS:
            if pattern.search(q):
                return QueryIntent.CROSS_DOC, 0.80

        for pattern in _INVESTIGATION_PATTERNS:
            if pattern.search(q):
                return QueryIntent.INVESTIGATION, 0.75

        for pattern in _GAP_PATTERNS:
            if pattern.search(q):
                return QueryIntent.GAP, 0.85

        for pattern in _LIST_PATTERNS:
            if pattern.search(q):
                return QueryIntent.LIST, 0.85

        for pattern in _MEASUREMENT_PATTERNS:
            if pattern.search(q):
                return QueryIntent.MEASUREMENT, 0.80

        for pattern in _TEMPORAL_PATTERNS:
            if pattern.search(q):
                return QueryIntent.TEMPORAL, 0.80

        for pattern in _RELATIONSHIP_PATTERNS:
            if pattern.search(q):
                return QueryIntent.RELATIONSHIP, 0.80

        for pattern in _IDENTITY_PATTERNS:
            if pattern.search(q):
                return QueryIntent.IDENTITY, 0.85

        return QueryIntent.IDENTITY, 0.3


class SetFitIntentClassifier:
    """SetFit-backed intent classifier. Uses LazyModelRuntime for model loading."""

    def __init__(
        self,
        model_path: str,
        runtime: Any | None = None,
        confidence_threshold: float = 0.4,
    ) -> None:
        self._model_path = model_path
        self._runtime = runtime
        self._threshold = confidence_threshold
        self._fallback = HeuristicIntentClassifier()

    @property
    def name(self) -> str:
        return "setfit_intent"

    async def classify(self, question: str) -> tuple[QueryIntent, float]:
        if self._runtime is None:
            return await self._fallback.classify(question)

        try:
            model = await self._runtime.get_or_load(
                "setfit_intent", self._model_path, "cpu", self._load_model,
            )
            probs = await self._runtime.run_inference(model.predict_proba, [question])
            if hasattr(probs, "__getitem__") and hasattr(model, "labels"):
                prob_list = probs[0].tolist() if hasattr(probs[0], "tolist") else list(probs[0])
                labels = list(model.labels)
                if len(labels) == len(prob_list):
                    best_idx = prob_list.index(max(prob_list))
                    label = labels[best_idx]
                    confidence = float(prob_list[best_idx])
                    if confidence >= self._threshold:
                        try:
                            return QueryIntent(label), confidence
                        except ValueError:
                            pass
        except Exception:
            logger.warning(
                "ML intent classification failed, using heuristic fallback",
                exc_info=True,
            )

        return await self._fallback.classify(question)

    def _load_model(self) -> Any:
        from setfit import SetFitModel  # noqa: PLC0415
        return SetFitModel.from_pretrained(self._model_path)
