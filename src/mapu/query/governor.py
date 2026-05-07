"""Cascade governor: routes queries to the cheapest sufficient tier."""

from __future__ import annotations

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
    QueryIntent.CROSS_DOC,
})

_INVESTIGATION_INTENTS: frozenset[QueryIntent] = frozenset({
    QueryIntent.INVESTIGATION,
})


class CascadeGovernor:
    """Decides which tier to route a query to based on intent classification."""

    def __init__(
        self,
        intent_classifier: IntentClassifier,
        coverage_threshold: float = 0.8,
    ) -> None:
        self._classifier = intent_classifier
        self._coverage_threshold = coverage_threshold

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


def _extract_query_entities(question: str) -> list[str]:
    """Extract likely entity references from a query (lightweight heuristic)."""
    import re

    entities: list[str] = []
    quoted = re.findall(r'"([^"]+)"', question)
    entities.extend(quoted)

    capitalized = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", question)
    skip = {"What", "Who", "Where", "When", "How", "Which", "Does", "Did", "Is", "Are"}
    for cap in capitalized:
        if cap not in skip and cap not in entities:
            entities.append(cap)

    return entities


def _extract_query_predicates(question: str) -> list[str]:
    """Extract likely predicate keywords from a query."""
    import re

    verbs = re.findall(
        r"\b(own|control|manage|employ|relate|connect|pay|owe|define|obligat|terminat|vest|acquir)\w*\b",
        question,
        re.IGNORECASE,
    )
    return list(set(v.lower() for v in verbs))
