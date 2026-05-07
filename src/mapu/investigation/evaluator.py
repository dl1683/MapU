"""Investigation evaluator: coverage, termination, replan decisions."""

from __future__ import annotations

import uuid

from mapu.investigation.types import InvestigationState, TerminationReason


class InvestigationEvaluator:
    def should_terminate(self, state: InvestigationState) -> TerminationReason | None:
        if state.budget_exhausted():
            return TerminationReason.BUDGET_EXHAUSTED

        if state.coverage >= state.budget.target_coverage:
            return TerminationReason.COVERAGE_MET

        if self._diminishing_returns(state):
            return TerminationReason.DIMINISHING_RETURNS

        if self._circular_retrieval(state):
            return TerminationReason.CIRCULAR_RETRIEVAL

        return None

    def update_coverage(
        self,
        state: InvestigationState,
        query_entities: tuple[str, ...],
        query_predicates: tuple[str, ...],
    ) -> None:
        if not query_entities and not query_predicates:
            return

        found_entities: set[str] = set()
        found_predicates: set[str] = set()
        for obs in state.observations:
            found_entities.update(e.lower() for e in obs.new_entities_discovered)
            has_results = bool(obs.evidence or obs.proposition_ids_found)
            if has_results:
                found_entities.update(e.lower() for e in obs.action.entities)
                found_predicates.update(p.lower() for p in obs.action.predicates)

        if query_entities:
            state.has_entity_targets = True
            matched = sum(
                1 for e in query_entities if e.lower() in found_entities
            )
            state.known_entity_coverage = matched / len(query_entities)

        if query_predicates:
            state.has_predicate_targets = True
            matched = sum(
                1 for p in query_predicates if p.lower() in found_predicates
            )
            state.known_predicate_coverage = matched / len(query_predicates)

    def _diminishing_returns(self, state: InvestigationState) -> bool:
        if len(state.observations) < 2:
            return False

        recent = state.observations[-2:]
        total_known = len(state.seen_proposition_ids)
        if total_known == 0:
            return False

        for obs in recent:
            new_ratio = len(obs.proposition_ids_found) / max(total_known, 1)
            if new_ratio >= state.budget.min_new_info_per_step:
                return False

        return True

    def _circular_retrieval(self, state: InvestigationState) -> bool:
        if len(state.observations) < 3:
            return False

        recent_ids: list[set[uuid.UUID]] = []
        for obs in state.observations[-3:]:
            recent_ids.append(set(obs.proposition_ids_found))

        if all(len(ids) == 0 for ids in recent_ids):
            return True

        if len(recent_ids) >= 2:
            overlap = recent_ids[-1] & recent_ids[-2]
            union = recent_ids[-1] | recent_ids[-2]
            if union and len(overlap) / len(union) > 0.8:
                return True

        return False
