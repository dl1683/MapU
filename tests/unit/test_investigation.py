"""Unit tests for the investigation engine."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from mapu.investigation.evaluator import InvestigationEvaluator
from mapu.investigation.planner import LLMInvestigationPlanner, _parse_plan
from mapu.investigation.types import (
    ActionKind,
    InvestigationBudget,
    InvestigationState,
    Observation,
    TerminationReason,
)


class TestParsePlan:
    def test_parses_valid_plan(self) -> None:
        raw = {
            "reasoning": "Need to find X",
            "actions": [
                {
                    "kind": "structured_query",
                    "query": "find X",
                    "entities": ["X"],
                    "predicates": ["controls"],
                    "reason": "Look up X",
                },
            ],
        }
        plan = _parse_plan(raw)
        assert plan.reasoning == "Need to find X"
        assert len(plan.actions) == 1
        assert plan.actions[0].kind == ActionKind.STRUCTURED_QUERY
        assert plan.actions[0].entities == ("X",)

    def test_handles_unknown_kind(self) -> None:
        raw = {
            "actions": [{"kind": "unknown_kind", "query": "test"}],
        }
        plan = _parse_plan(raw)
        assert plan.actions[0].kind == ActionKind.STRUCTURED_QUERY

    def test_handles_empty_actions(self) -> None:
        raw = {"actions": []}
        plan = _parse_plan(raw)
        assert len(plan.actions) == 0

    def test_handles_missing_fields(self) -> None:
        raw = {"actions": [{"query": "test"}]}
        plan = _parse_plan(raw)
        assert plan.actions[0].kind == ActionKind.STRUCTURED_QUERY
        assert plan.actions[0].entities == ()


class TestLLMInvestigationPlanner:
    @pytest.mark.asyncio
    async def test_plan_calls_llm(self) -> None:
        llm = MagicMock()
        llm.complete_json = AsyncMock(return_value={
            "reasoning": "plan",
            "actions": [
                {"kind": "entity_lookup", "query": "find CEO", "entities": ["CEO"]},
            ],
        })

        planner = LLMInvestigationPlanner(llm)
        state = InvestigationState(budget=InvestigationBudget())
        plan = await planner.plan("Who is the CEO?", state)

        assert len(plan.actions) == 1
        assert state.llm_calls_used == 1
        llm.complete_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_plan_handles_malformed_response(self) -> None:
        llm = MagicMock()
        llm.complete_json = AsyncMock(return_value={})

        planner = LLMInvestigationPlanner(llm)
        state = InvestigationState(budget=InvestigationBudget())
        plan = await planner.plan("test", state)

        assert len(plan.actions) == 0


class TestInvestigationEvaluator:
    def test_budget_exhausted_by_actions(self) -> None:
        evaluator = InvestigationEvaluator()
        state = InvestigationState(
            budget=InvestigationBudget(max_actions=5),
            actions_executed=5,
        )
        assert evaluator.should_terminate(state) == TerminationReason.BUDGET_EXHAUSTED

    def test_budget_exhausted_by_llm_calls(self) -> None:
        evaluator = InvestigationEvaluator()
        state = InvestigationState(
            budget=InvestigationBudget(max_llm_calls=3),
            llm_calls_used=3,
        )
        assert evaluator.should_terminate(state) == TerminationReason.BUDGET_EXHAUSTED

    def test_coverage_met(self) -> None:
        evaluator = InvestigationEvaluator()
        state = InvestigationState(
            budget=InvestigationBudget(target_coverage=0.9),
            known_entity_coverage=0.95,
            known_predicate_coverage=0.95,
            has_entity_targets=True,
            has_predicate_targets=True,
        )
        assert evaluator.should_terminate(state) == TerminationReason.COVERAGE_MET

    def test_no_termination_early(self) -> None:
        evaluator = InvestigationEvaluator()
        state = InvestigationState(budget=InvestigationBudget())
        assert evaluator.should_terminate(state) is None

    def test_diminishing_returns(self) -> None:
        evaluator = InvestigationEvaluator()
        p1, p2 = uuid.uuid4(), uuid.uuid4()
        state = InvestigationState(
            budget=InvestigationBudget(min_new_info_per_step=0.05),
            seen_proposition_ids={p1, p2, uuid.uuid4(), uuid.uuid4()},
            observations=[
                Observation(
                    action=MagicMock(),
                    proposition_ids_found=(),
                ),
                Observation(
                    action=MagicMock(),
                    proposition_ids_found=(),
                ),
            ],
        )
        assert evaluator.should_terminate(state) == TerminationReason.DIMINISHING_RETURNS

    def test_circular_retrieval_three_empty_steps(self) -> None:
        evaluator = InvestigationEvaluator()
        state = InvestigationState(
            budget=InvestigationBudget(),
            observations=[
                Observation(action=MagicMock(), proposition_ids_found=()),
                Observation(action=MagicMock(), proposition_ids_found=()),
                Observation(action=MagicMock(), proposition_ids_found=()),
            ],
        )
        assert evaluator.should_terminate(state) == TerminationReason.CIRCULAR_RETRIEVAL

    def test_update_coverage_with_entities(self) -> None:
        evaluator = InvestigationEvaluator()
        state = InvestigationState(budget=InvestigationBudget())
        action = MagicMock()
        action.entities = ("CEO",)
        action.predicates = ()
        state.observations = [
            Observation(
                action=action,
                proposition_ids_found=(uuid.uuid4(),),
                new_entities_discovered=("CEO",),
            ),
        ]
        evaluator.update_coverage(state, ("CEO", "CFO"), ("controls",))
        assert state.known_entity_coverage == 0.5

    def test_update_coverage_with_predicates(self) -> None:
        evaluator = InvestigationEvaluator()
        state = InvestigationState(budget=InvestigationBudget())
        action = MagicMock()
        action.entities = ()
        action.predicates = ("controls",)
        state.observations = [
            Observation(
                action=action,
                proposition_ids_found=(uuid.uuid4(),),
                new_entities_discovered=(),
            ),
        ]
        evaluator.update_coverage(state, (), ("controls", "manages"))
        assert state.known_predicate_coverage == 0.5

    def test_update_coverage_ignores_empty_results(self) -> None:
        evaluator = InvestigationEvaluator()
        state = InvestigationState(budget=InvestigationBudget())
        action = MagicMock()
        action.entities = ("CEO",)
        action.predicates = ("controls",)
        state.observations = [
            Observation(action=action, new_entities_discovered=()),
        ]
        evaluator.update_coverage(state, ("CEO",), ("controls",))
        assert state.known_entity_coverage == 0.0
        assert state.known_predicate_coverage == 0.0


class TestInvestigationState:
    def test_coverage_zero_when_empty(self) -> None:
        state = InvestigationState(budget=InvestigationBudget())
        assert state.coverage == 0.0

    def test_coverage_average(self) -> None:
        state = InvestigationState(
            budget=InvestigationBudget(),
            known_entity_coverage=0.8,
            known_predicate_coverage=0.6,
            has_entity_targets=True,
            has_predicate_targets=True,
        )
        assert state.coverage == pytest.approx(0.7)

    def test_coverage_single_dimension(self) -> None:
        state = InvestigationState(
            budget=InvestigationBudget(),
            known_entity_coverage=0.8,
            has_entity_targets=True,
        )
        assert state.coverage == pytest.approx(0.8)

    def test_budget_exhausted_false(self) -> None:
        state = InvestigationState(budget=InvestigationBudget())
        assert state.budget_exhausted() is False

    def test_budget_exhausted_true(self) -> None:
        state = InvestigationState(
            budget=InvestigationBudget(max_actions=5),
            actions_executed=5,
        )
        assert state.budget_exhausted() is True
