"""Synthesis: template-based (no LLM) and LLM-backed answer generation."""

from __future__ import annotations

from collections.abc import Sequence

from mapu.providers.llms import LLMProvider, LLMRequest
from mapu.query.types import PropositionHit, QueryIntent


class TemplateSynthesizer:
    """Template-based synthesis for Tier 0-1 results. Zero LLM cost."""

    @property
    def name(self) -> str:
        return "template"

    async def synthesize(
        self,
        question: str,
        hits: Sequence[PropositionHit],
        intent: QueryIntent,
    ) -> str:
        if not hits:
            return "Insufficient evidence: no matching propositions found in the knowledge base."

        if intent == QueryIntent.IDENTITY:
            return self._identity_template(hits)
        if intent == QueryIntent.LIST:
            return self._list_template(hits)
        if intent == QueryIntent.TEMPORAL_DIFF:
            return self._temporal_diff_template(hits)
        if intent == QueryIntent.MEASUREMENT:
            return self._measurement_template(hits)
        return self._generic_template(hits)

    def _identity_template(self, hits: Sequence[PropositionHit]) -> str:
        h = hits[0]
        parts = [f"{h.subject_name} ({h.subject_kind}): {h.normalized_text}"]
        meta = _epistemic_meta(h)
        if meta:
            parts.append(f"[{meta}]")
        return " ".join(parts)

    def _list_template(self, hits: Sequence[PropositionHit]) -> str:
        lines = [f"Found {len(hits)} results:"]
        for h in hits:
            meta = _epistemic_meta(h)
            lines.append(f"- {h.normalized_text} [{meta}]")
        return "\n".join(lines)

    def _temporal_diff_template(self, hits: Sequence[PropositionHit]) -> str:
        lines = [f"Identified {len(hits)} related propositions:"]
        for h in hits:
            lines.append(f"- {h.normalized_text} [{h.frame_type}]")
        return "\n".join(lines)

    def _measurement_template(self, hits: Sequence[PropositionHit]) -> str:
        lines = []
        for h in hits:
            meta = _epistemic_meta(h)
            lines.append(f"{h.subject_name}: {h.normalized_text} [{meta}]")
        return "\n".join(lines) if lines else "No measurements found."

    def _generic_template(self, hits: Sequence[PropositionHit]) -> str:
        lines = [f"Found {len(hits)} relevant propositions:"]
        for h in hits[:10]:
            lines.append(f"- {h.normalized_text}")
        if len(hits) > 10:
            lines.append(f"  ... and {len(hits) - 10} more")
        return "\n".join(lines)


class LLMSynthesizer:
    """LLM-backed synthesis for Tier 2. Cheap model by default."""

    def __init__(self, provider: LLMProvider, max_tokens: int = 1024) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "llm"

    async def synthesize(
        self,
        question: str,
        hits: Sequence[PropositionHit],
        intent: QueryIntent,
    ) -> str:
        if not hits:
            return "Insufficient evidence: no matching propositions found in the knowledge base."

        context = self._build_context(hits)
        request = LLMRequest(
            system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt=f"Question: {question}\n\nAvailable evidence:\n{context}",
            max_tokens=self._max_tokens,
            temperature=0.0,
        )
        result = await self._provider.complete_json(request)
        return str(result.get("answer", "Unable to synthesize an answer."))

    def _build_context(self, hits: Sequence[PropositionHit]) -> str:
        lines: list[str] = []
        for i, h in enumerate(hits[:20], 1):
            parts = [f"{i}. {h.normalized_text}"]
            parts.append(f"   Subject: {h.subject_name} ({h.subject_kind})")
            parts.append(f"   Type: {h.frame_type}, Predicate: {h.predicate}")
            parts.append(f"   Confidence: {h.extraction_confidence:.0%}")
            if h.truth_status:
                parts.append(f"   Truth status: {h.truth_status}")
            lines.append("\n".join(parts))
        return "\n\n".join(lines)


def _epistemic_meta(h: PropositionHit) -> str:
    parts: list[str] = []
    parts.append(f"confidence: {h.extraction_confidence:.0%}")
    if h.authority_score is not None:
        parts.append(f"authority: {h.authority_score:.2f}")
    if h.truth_status:
        parts.append(f"truth: {h.truth_status}")
    if h.valid_from or h.valid_to:
        vf = h.valid_from.date().isoformat() if h.valid_from else "..."
        vt = h.valid_to.date().isoformat() if h.valid_to else "..."
        parts.append(f"valid: {vf}/{vt}")
    return ", ".join(parts)


_SYNTHESIS_SYSTEM_PROMPT = (
    "You are a knowledge synthesis engine. Given a question and extracted "
    "propositions from a knowledge base, produce a concise, accurate answer. "
    "Cite proposition numbers in brackets [1], [2] etc. "
    "If the evidence is insufficient, say so explicitly. "
    "Respond with JSON: {\"answer\": \"...\"}"
)
