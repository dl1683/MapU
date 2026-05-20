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
        entities = _extract_query_entities(request.question)
        predicates = _extract_query_predicates(request.question)
        tier = self._select_tier(intent, confidence)

        # Identity questions with explicit entities should not be downgraded to
        # synthesis on classifier uncertainty; direct lookup is still the
        # cheapest/highest-yield first step.
        if intent == QueryIntent.IDENTITY and entities:
            tier = Tier.DIRECT

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
_MIXED_CASE_RE = re.compile(r"\b([A-Za-z]*[a-z][A-Za-z]*[A-Z][A-Za-z0-9]*)\b")
_PROJECT_TOKEN_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)+)\b")
_NOUN_PHRASE_RE = re.compile(
    r"(?:what is (?:a |an |the )?|who is (?:a |an |the )?|define |tell me about (?:the )?)"
    r"(.+?)(?:\?|$)",
    re.IGNORECASE,
)
_PREDICATE_RE = re.compile(
    r"\b([a-z]{3,}(?:ed|ing|ize|ise|ate|ify))\b",
    re.IGNORECASE,
)
_PREDICATE_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(?:should|must|can)?\s*sits?\s+in\s+front\s+of\b",
            re.IGNORECASE,
        ),
        "sits_in_front_of",
    ),
    (re.compile(r"\b(?:own|owns|owner|owned\s+by)\b", re.IGNORECASE), "owned_by"),
    (re.compile(r"\b(?:use|uses|using)\b", re.IGNORECASE), "uses"),
    (re.compile(r"\bdepends\s+on\b", re.IGNORECASE), "depends_on"),
    (re.compile(r"\b(?:store|stores|stored|storing)\b", re.IGNORECASE), "stores"),
    (re.compile(r"\b(?:persist|persists|persisted|persisting)\b", re.IGNORECASE), "persists"),
    (re.compile(r"\b(?:expose|exposes|exposed|exposing)\b", re.IGNORECASE), "exposes"),
    (re.compile(r"\b(?:support|supports|supported|supporting)\b", re.IGNORECASE), "supports"),
    (re.compile(r"\b(?:create|creates|created|creating)\b", re.IGNORECASE), "creates"),
    (re.compile(r"\b(?:return|returns|returned|returning)\b", re.IGNORECASE), "returns"),
    (re.compile(r"\b(?:include|includes|included|including)\b", re.IGNORECASE), "includes"),
    (re.compile(r"\b(?:log|logs|logged|logging)\b", re.IGNORECASE), "logs"),
    (re.compile(r"\b(?:ingest|ingests|ingested|ingesting)\b", re.IGNORECASE), "ingests"),
    (re.compile(r"\b(?:query|queries|queried|querying)\b", re.IGNORECASE), "queries"),
    (re.compile(r"\b(?:answer|answers|answered|answering)\b", re.IGNORECASE), "answers"),
    (re.compile(r"\b(?:require|requires|required|requiring)\b", re.IGNORECASE), "requires"),
)

_PREDICATE_SKIP = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all",
    "can", "had", "her", "was", "one", "our", "out", "has",
    "his", "how", "its", "may", "new", "now", "old", "see",
    "way", "who", "did", "get", "let", "say", "she", "too",
    "use", "about", "after", "also", "any", "been", "between",
    "both", "each", "from", "have", "into", "just", "more",
    "most", "only", "other", "over", "some", "such", "than",
    "that", "them", "then", "there", "these", "they", "this",
    "those", "through", "under", "very", "what", "when",
    "where", "which", "while", "with", "would", "could",
    "should", "does", "will", "were", "being", "their",
    "yes", "once", "since", "before", "because", "hence",
    "called", "named", "based", "described", "listed",
})

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

    for mixed in _MIXED_CASE_RE.findall(question):
        if mixed not in _ENTITY_SKIP and mixed not in entities:
            entities.append(mixed)

    for acr in _ACRONYM_RE.findall(question):
        if acr not in entities:
            entities.append(acr)

    for project_token in _PROJECT_TOKEN_RE.findall(question):
        if project_token not in entities:
            entities.append(project_token)

    if not entities:
        noun_phrase = _NOUN_PHRASE_RE.search(question)
        if noun_phrase:
            target = noun_phrase.group(1).strip().rstrip("?. ")
            if target:
                entities.append(target)

    return entities


def _extract_query_predicates(question: str) -> list[str]:
    """Extract likely predicate keywords from a query."""
    predicates: list[str] = []
    for pattern, predicate in _PREDICATE_PHRASES:
        if pattern.search(question) and predicate not in predicates:
            predicates.append(predicate)

    words = _PREDICATE_RE.findall(question)
    for word in words:
        lowered = word.lower()
        if lowered not in _PREDICATE_SKIP and lowered not in predicates:
            predicates.append(lowered)
    return predicates
