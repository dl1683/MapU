"""LLM-backed semantic proposition extractor.

Provider-agnostic: works with any LLMProvider (OpenAI, Anthropic, local).
The LLM proposes structured frames; the deterministic pipeline governs quality.
"""

from __future__ import annotations

import json
from typing import Any

from mapu.extraction.types import (
    EntityMention,
    ExtractionContext,
    ExtractionSignal,
    ExtractorOutput,
    PropositionFrameCandidate,
)
from mapu.providers.llms import LLMProvider, LLMRequest
from mapu.types import AttestationStrength, FrameType, Stance

_VALID_FRAME_TYPES = ", ".join(f.value for f in FrameType)
_VALID_STANCES = ", ".join(s.value for s in Stance)
_VALID_STRENGTHS = ", ".join(a.value for a in AttestationStrength)

_SYSTEM_PROMPT = f"""\
You are a precise information extraction system. Given a text span, extract \
structured propositions — factual claims, obligations, definitions, \
measurements, relationships, events, constraints, and other assertable \
statements.

Output JSON with this exact schema:
{{
  "propositions": [
    {{
      "subject_text": "exact text from span",
      "subject_kind": "entity type (e.g. person, organization, drug, function, party)",
      "predicate": "verb or relation (e.g. deliver, requires, reported_revenue, inhibits)",
      "object_text": "exact text from span or null",
      "object_kind": "entity type or null",
      "value": {{}},
      "polarity": true,
      "modality": "obligation | permission | possibility | null",
      "normalized_text": "concise canonical form of the proposition",
      "frame_type": "one of: {_VALID_FRAME_TYPES}",
      "stance": "one of: {_VALID_STANCES}",
      "attestation_strength": "one of: {_VALID_STRENGTHS}",
      "confidence": 0.0
    }}
  ]
}}

Rules:
- Focus on the PRIMARY propositions — the main claims, obligations, findings, \
and relationships. Do NOT extract trivial, redundant, or overly granular sub-claims.
- Aim for 1-5 propositions per text span. Fewer is better if the text is simple.
- If two propositions say essentially the same thing, keep only the more complete one.
- subject_text and object_text MUST be exact substrings of the input text.
- predicate should be a short verb or relation phrase in snake_case.
- normalized_text is a concise human-readable summary of the proposition.
- confidence: 0.0-1.0. Only include propositions with confidence >= 0.5.
- Do NOT hallucinate information not present in the text.
- If the text contains no extractable propositions, return {{"propositions": []}}.
- For obligations/requirements, use frame_type "obligation" and modality "obligation".
- For definitions ("X means Y"), use frame_type "definition" and predicate "means".
- For deprecations, use frame_type "deprecation" and predicate "deprecated".
- For measurements/metrics, include numeric values in the value field.
- value field can contain arbitrary key-value pairs for structured data \
(amounts, percentages, thresholds, dates, versions, etc.).\
"""


def _find_exact_span(text: str, target: str) -> tuple[int, int]:
    idx = text.find(target)
    if idx >= 0:
        return (idx, idx + len(target))
    idx = text.lower().find(target.lower())
    if idx >= 0:
        return (idx, idx + len(target))
    return (0, len(target))


def _build_user_prompt(ctx: ExtractionContext) -> str:
    parts = [f"TEXT:\n{ctx.text}"]
    if ctx.prior_entities:
        ent_list = [f"- {e.text} ({e.kind})" for e in ctx.prior_entities]
        parts.append("KNOWN ENTITIES:\n" + "\n".join(ent_list))
    return "\n\n".join(parts)


def _parse_response(
    raw: dict[str, Any],
    ctx: ExtractionContext,
    min_confidence: float,
) -> tuple[list[PropositionFrameCandidate], list[ExtractionSignal]]:
    frames: list[PropositionFrameCandidate] = []
    signals: list[ExtractionSignal] = []

    propositions = raw.get("propositions", [])
    if not isinstance(propositions, list):
        return frames, signals

    for prop in propositions:
        if not isinstance(prop, dict):
            continue

        confidence = float(prop.get("confidence", 0.0))
        if confidence < min_confidence:
            continue

        subject_text = str(prop.get("subject_text", ""))
        if not subject_text:
            continue

        subj_span = _find_exact_span(ctx.text, subject_text)
        subject = EntityMention(
            text=subject_text,
            kind=str(prop.get("subject_kind", "entity")),
            start_char=ctx.start_char + subj_span[0],
            end_char=ctx.start_char + subj_span[1],
            confidence=confidence,
            source="llm",
        )

        obj = None
        object_text = prop.get("object_text")
        if object_text:
            object_text = str(object_text)
            obj_span = _find_exact_span(ctx.text, object_text)
            obj = EntityMention(
                text=object_text,
                kind=str(prop.get("object_kind", "entity")),
                start_char=ctx.start_char + obj_span[0],
                end_char=ctx.start_char + obj_span[1],
                confidence=confidence,
                source="llm",
            )

        predicate = str(prop.get("predicate", "states"))
        normalized = str(prop.get("normalized_text", f"{subject_text} {predicate}"))
        raw_frame_type = str(prop.get("frame_type", "relationship"))
        raw_stance = str(prop.get("stance", "asserts"))
        raw_strength = str(prop.get("attestation_strength", "direct_statement"))

        try:
            frame_type = FrameType(raw_frame_type)
        except ValueError:
            frame_type = FrameType.RELATIONSHIP

        try:
            stance = Stance(raw_stance)
        except ValueError:
            stance = Stance.ASSERTS

        try:
            strength = AttestationStrength(raw_strength)
        except ValueError:
            strength = AttestationStrength.INFERENCE

        value = prop.get("value")
        if isinstance(value, dict) and not value:
            value = None

        modality = prop.get("modality")
        if modality == "null" or modality is None:
            modality = None

        frames.append(PropositionFrameCandidate(
            span_id=ctx.span_id,
            frame_type=frame_type,
            subject=subject,
            predicate=predicate,
            object=obj,
            value=value,
            polarity=bool(prop.get("polarity", True)),
            modality=modality,
            valid_range=None,
            normalized_text=normalized,
            qualifiers=prop.get("qualifiers") or {},
            stance=stance,
            attestation_strength=strength,
            extraction_method="llm",
            extraction_confidence=confidence,
        ))

        signals.append(ExtractionSignal(
            signal_type="llm_proposition",
            data={
                "predicate": predicate,
                "subject": subject_text,
                "confidence": confidence,
                "frame_type": raw_frame_type,
            },
            start_char=subject.start_char,
            end_char=obj.end_char if obj else subject.end_char,
            source="llm",
        ))

    return frames, signals


class LLMExtractor:
    """Semantic proposition extractor using any LLMProvider."""

    def __init__(
        self,
        provider: LLMProvider,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        min_confidence: float = 0.5,
    ) -> None:
        self._provider = provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._min_confidence = min_confidence

    @property
    def name(self) -> str:
        return "llm"

    async def extract(self, ctx: ExtractionContext) -> ExtractorOutput:
        if not ctx.text.strip():
            return ExtractorOutput()

        request = LLMRequest(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_build_user_prompt(ctx),
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

        try:
            raw = await self._provider.complete_json(request)
        except Exception:
            return ExtractorOutput(
                signals=(ExtractionSignal(
                    signal_type="llm_error",
                    data={"error": "LLM call failed"},
                    source="llm",
                ),),
            )

        if not isinstance(raw, dict):
            return ExtractorOutput()

        # Handle case where response is wrapped in {"answer": "..."}
        if "answer" in raw and "propositions" not in raw:
            try:
                raw = json.loads(str(raw["answer"]))
            except (json.JSONDecodeError, TypeError):
                return ExtractorOutput()

        frames, signals = _parse_response(raw, ctx, self._min_confidence)
        return ExtractorOutput(
            frames=tuple(frames),
            signals=tuple(signals),
        )
