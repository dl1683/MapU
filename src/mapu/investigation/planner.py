"""LLM-backed investigation planner."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mapu.investigation.types import (
    ActionKind,
    InvestigationAction,
    InvestigationPlan,
    InvestigationState,
)
from mapu.providers.llms import LLMProvider, LLMRequest

PLANNING_SYSTEM_PROMPT = """\
You are an investigation planner for a knowledge graph system.
Given a question, known evidence, and identified gaps, produce a plan
of search actions to gather the missing evidence.

Respond with valid JSON matching this schema:
{
  "reasoning": "brief explanation of the plan",
  "actions": [
    {
      "kind": "structured_query | embedding_search | entity_lookup | ...",
      "query": "the search query text",
      "entities": ["entity1", "entity2"],
      "predicates": ["predicate1"],
      "reason": "why this action helps"
    }
  ]
}

Rules:
- Produce 1-5 actions per plan.
- Each action should target a specific information gap.
- Prefer structured_query and entity_lookup for known entities.
- Use embedding_search for fuzzy or conceptual queries.
- Use chunk_retrieval when you need surrounding context from a document.
- Use temporal_diff when comparing states across time.
- Use gap_check to verify known gaps are still unresolved.
"""


def _format_user_prompt(
    question: str,
    state: InvestigationState,
    known_entities: tuple[str, ...],
    known_predicates: tuple[str, ...],
) -> str:
    parts = [f"Question: {question}"]

    if known_entities:
        parts.append(f"Known entities: {', '.join(known_entities)}")
    if known_predicates:
        parts.append(f"Known predicates: {', '.join(known_predicates)}")

    if state.observations:
        parts.append(f"Steps completed: {state.actions_executed}")
        parts.append(f"Propositions found: {len(state.seen_proposition_ids)}")
        parts.append(f"Coverage: {state.coverage:.0%}")
        last_obs = state.observations[-1]
        parts.append(
            f"Last action found {len(last_obs.proposition_ids_found)} propositions"
        )

    parts.append(
        f"Budget remaining: {state.budget.max_actions - state.actions_executed} actions, "
        f"{state.budget.max_llm_calls - state.llm_calls_used} LLM calls"
    )

    return "\n".join(parts)


def _parse_plan(raw: Mapping[str, Any]) -> InvestigationPlan:
    actions: list[InvestigationAction] = []
    raw_actions = raw.get("actions") or []
    for action_data in raw_actions:
        if not isinstance(action_data, Mapping):
            continue

        kind_str = action_data.get("kind", "structured_query")
        try:
            kind = ActionKind(kind_str)
        except ValueError:
            kind = ActionKind.STRUCTURED_QUERY

        raw_entities = action_data.get("entities") or ()
        raw_predicates = action_data.get("predicates") or ()
        if isinstance(raw_entities, str):
            raw_entities = [raw_entities]
        if isinstance(raw_predicates, str):
            raw_predicates = [raw_predicates]
        entities = tuple(e for e in raw_entities if isinstance(e, str))
        predicates = tuple(p for p in raw_predicates if isinstance(p, str))

        actions.append(InvestigationAction(
            kind=kind,
            query=str(action_data.get("query", "")),
            entities=entities,
            predicates=predicates,
            reason=str(action_data.get("reason", "")),
        ))

    return InvestigationPlan(
        actions=tuple(actions),
        reasoning=str(raw.get("reasoning", "")),
    )


class LLMInvestigationPlanner:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def plan(
        self,
        question: str,
        state: InvestigationState,
        known_entities: tuple[str, ...] = (),
        known_predicates: tuple[str, ...] = (),
    ) -> InvestigationPlan:
        user_prompt = _format_user_prompt(
            question, state, known_entities, known_predicates,
        )
        request = LLMRequest(
            system_prompt=PLANNING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1024,
            temperature=0.1,
        )
        raw = await self._llm.complete_json(request)
        state.llm_calls_used += 1
        return _parse_plan(raw)
