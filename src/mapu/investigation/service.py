"""Investigation service: orchestration loop for multi-document reasoning."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.investigation.evaluator import InvestigationEvaluator
from mapu.investigation.executor import InvestigationExecutor
from mapu.investigation.planner import LLMInvestigationPlanner
from mapu.investigation.types import (
    InvestigationBudget,
    InvestigationEvidence,
    InvestigationResult,
    InvestigationState,
    TerminationReason,
)
from mapu.providers.llms import LLMProvider, LLMRequest
from mapu.query.types import PropositionHit

SYNTHESIS_SYSTEM_PROMPT = """\
You are a knowledge synthesis engine. Given a question and evidence from \
a knowledge graph, produce a precise answer with inline citations.

Rules:
- Cite evidence by referencing source spans when available.
- Flag any gaps or contradictions explicitly.
- Report confidence level (high/medium/low) for each claim.
- Do not speculate beyond what the evidence supports.
"""


class InvestigationService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LLMProvider,
        budget: InvestigationBudget | None = None,
    ) -> None:
        self._session = session
        self._llm = llm
        self._planner = LLMInvestigationPlanner(llm)
        self._executor = InvestigationExecutor(session)
        self._evaluator = InvestigationEvaluator()
        self._budget = budget or InvestigationBudget()

    async def investigate(
        self,
        question: str,
        corpus_id: uuid.UUID,
        initial_entities: tuple[str, ...] = (),
        initial_predicates: tuple[str, ...] = (),
        initial_hits: tuple[PropositionHit, ...] = (),
    ) -> InvestigationResult:
        state = InvestigationState(budget=self._budget)

        for hit in initial_hits:
            state.seen_proposition_ids.add(hit.proposition_id)

        termination: TerminationReason | None = None

        while termination is None:
            plan = await self._planner.plan(
                question, state, initial_entities, initial_predicates,
            )

            if not plan.actions:
                termination = TerminationReason.PLANNER_STOP
                break

            for action in plan.actions:
                obs = await self._executor.execute_action(
                    action, corpus_id, state,
                )
                state.observations.append(obs)

                self._evaluator.update_coverage(
                    state, initial_entities, initial_predicates,
                )

                termination = self._evaluator.should_terminate(state)
                if termination is not None:
                    break

        evidence = self._collect_evidence(state, initial_hits)
        gaps = self._identify_gaps(
            state, initial_entities, initial_predicates,
        )

        answer = await self._synthesize(question, evidence, gaps, state)

        return InvestigationResult(
            answer=answer,
            evidence=evidence,
            gaps=gaps,
            findings=(),
            metadata=self._build_metadata(state, termination),
            termination_reason=termination or TerminationReason.PLANNER_STOP,
        )

    def _collect_evidence(
        self,
        state: InvestigationState,
        initial_hits: tuple[PropositionHit, ...],
    ) -> tuple[InvestigationEvidence, ...]:
        evidence: list[InvestigationEvidence] = []
        seen: set[uuid.UUID] = set()

        for hit in initial_hits:
            if hit.proposition_id not in seen:
                seen.add(hit.proposition_id)
                evidence.append(InvestigationEvidence(
                    proposition_id=hit.proposition_id,
                    normalized_text=hit.normalized_text,
                    source_span=hit.source_span_text,
                    authority_score=hit.authority_score,
                ))

        for obs in state.observations:
            for pid in obs.proposition_ids_found:
                if pid not in seen:
                    seen.add(pid)
                    evidence.append(InvestigationEvidence(
                        proposition_id=pid,
                        normalized_text="",
                        source_span=None,
                        authority_score=None,
                    ))

        return tuple(evidence)

    def _identify_gaps(
        self,
        state: InvestigationState,
        entities: tuple[str, ...],
        predicates: tuple[str, ...],
    ) -> tuple[str, ...]:
        gaps: list[str] = []

        found_entities: set[str] = set()
        for obs in state.observations:
            found_entities.update(e.lower() for e in obs.new_entities_discovered)
            found_entities.update(e.lower() for e in obs.action.entities)

        for e in entities:
            if e.lower() not in found_entities:
                gaps.append(f"No evidence found for entity: {e}")

        found_predicates: set[str] = set()
        for obs in state.observations:
            found_predicates.update(p.lower() for p in obs.action.predicates)

        for p in predicates:
            if p.lower() not in found_predicates:
                gaps.append(f"No evidence found for predicate: {p}")

        return tuple(gaps)

    async def _synthesize(
        self,
        question: str,
        evidence: tuple[InvestigationEvidence, ...],
        gaps: tuple[str, ...],
        state: InvestigationState,
    ) -> str:
        if not evidence:
            return "No evidence found to answer this question."

        evidence_text = "\n".join(
            f"- {e.normalized_text}" + (
                f" (source: {e.source_span})" if e.source_span else ""
            )
            for e in evidence
            if e.normalized_text
        )

        gap_text = "\n".join(f"- {g}" for g in gaps) if gaps else "None"

        user_prompt = (
            f"Question: {question}\n\n"
            f"Evidence:\n{evidence_text}\n\n"
            f"Gaps:\n{gap_text}\n\n"
            f"Synthesize an answer."
        )

        request = LLMRequest(
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2048,
            temperature=0.1,
        )
        raw = await self._llm.complete_json(request)
        state.llm_calls_used += 1
        return str(raw.get("answer", raw))

    def _build_metadata(
        self,
        state: InvestigationState,
        termination: TerminationReason | None,
    ) -> dict[str, Any]:
        return {
            "actions_executed": state.actions_executed,
            "llm_calls_used": state.llm_calls_used,
            "documents_read": state.documents_read,
            "propositions_found": len(state.seen_proposition_ids),
            "coverage": state.coverage,
            "termination_reason": (
                termination.value if termination else "unknown"
            ),
            "steps": len(state.observations),
        }
