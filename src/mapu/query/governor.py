"""Cascade governor: routes queries to the cheapest sufficient tier."""

from __future__ import annotations

import re

from mapu.query.types import (
    IntentClassifier,
    QueryIntent,
    QueryPlan,
    QueryRequest,
    Tier,
)

_DIRECT_INTENTS: frozenset[QueryIntent] = frozenset({
    QueryIntent.IDENTITY,
})

_STRUCTURED_INTENTS: frozenset[QueryIntent] = frozenset({
    QueryIntent.LIST,
    QueryIntent.TEMPORAL,
    QueryIntent.TEMPORAL_DIFF,
    QueryIntent.MEASUREMENT,
})

_SYNTHESIS_INTENTS: frozenset[QueryIntent] = frozenset({
    QueryIntent.RELATIONSHIP,
    QueryIntent.GAP,
})

_INVESTIGATION_INTENTS: frozenset[QueryIntent] = frozenset({
    QueryIntent.INVESTIGATION,
    QueryIntent.CROSS_DOC,
})


class CascadeGovernor:
    """Decides which tier to route a query to based on intent classification."""

    def __init__(
        self,
        intent_classifier: IntentClassifier,
    ) -> None:
        self._classifier = intent_classifier

    async def plan(self, request: QueryRequest) -> QueryPlan:
        intent, confidence = await self._classifier.classify(request.question)
        tier = self._select_tier(intent, confidence)

        entities = _extract_query_entities(request.question)
        predicates = _extract_query_predicates(request.question)

        escalation_reason: str | None = None
        if tier == Tier.INVESTIGATION:
            escalation_reason = (
                f"Intent '{intent.value}' requires multi-document reasoning"
            )

        return QueryPlan(
            intent=intent,
            selected_tier=tier,
            entities_extracted=tuple(entities),
            predicates_extracted=tuple(predicates),
            escalation_reason=escalation_reason,
        )

    def _select_tier(self, intent: QueryIntent, confidence: float) -> Tier:
        if intent in _INVESTIGATION_INTENTS:
            return Tier.INVESTIGATION
        if intent in _DIRECT_INTENTS and confidence >= 0.7:
            return Tier.DIRECT
        if intent in _STRUCTURED_INTENTS and confidence >= 0.6:
            return Tier.STRUCTURED
        if intent in _SYNTHESIS_INTENTS:
            return Tier.SYNTHESIS
        if confidence < 0.5:
            return Tier.SYNTHESIS
        return Tier.STRUCTURED


_QUOTED_RE = re.compile(r'"([^"]+)"')
_CAPITALIZED_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
)
_ACRONYM_RE = re.compile(r"\b([A-Z]{2,})\b")
_NOUN_PHRASE_RE = re.compile(
    r"(?:what is (?:a |an |the )?|who is (?:a |an |the )?|define |tell me about (?:the )?)"
    r"(.+?)(?:\?|$)",
    re.IGNORECASE,
)
_PREDICATE_RE = re.compile(
    r"\b(own|control|manage|employ|relate|connect|pay|owe|define|obligat|terminat|vest|acquir)\w*\b",
    re.IGNORECASE,
)

_ENTITY_SKIP = frozenset({
    "What", "Who", "Where", "When", "How", "Which",
    "Does", "Did", "Is", "Are", "The", "Can",
    "Define", "Tell", "List", "Show", "Describe",
    "Explain", "Find", "Give", "Identify",
})


def _extract_query_entities(question: str) -> list[str]:
    """Extract likely entity references from a query (lightweight heuristic)."""
    entities: list[str] = []
    entities.extend(_QUOTED_RE.findall(question))

    for cap in _CAPITALIZED_RE.findall(question):
        if cap not in _ENTITY_SKIP and cap not in entities:
            entities.append(cap)

    for acr in _ACRONYM_RE.findall(question):
        if acr not in entities:
            entities.append(acr)

    if not entities:
        noun_phrase = _NOUN_PHRASE_RE.search(question)
        if noun_phrase:
            target = noun_phrase.group(1).strip().rstrip("?. ")
            if target:
                entities.append(target)

    return entities


def _extract_query_predicates(question: str) -> list[str]:
    """Extract likely predicate keywords from a query."""
    verbs = _PREDICATE_RE.findall(question)
    return list(set(v.lower() for v in verbs))
