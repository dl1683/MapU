"""Investigation service: orchestration loop for multi-document reasoning."""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.context_learning import build_structured_next_steps, prioritize_next_steps
from mapu.investigation.evaluator import InvestigationEvaluator
from mapu.investigation.executor import InvestigationExecutor
from mapu.investigation.planner import LLMInvestigationPlanner
from mapu.investigation.types import (
    DerivedPropositionDraft,
    InvestigationBudget,
    InvestigationEvidence,
    InvestigationResult,
    InvestigationState,
    TerminationReason,
)
from mapu.models.attestation import Attestation, AttestationSituation
from mapu.models.authority import SourcePolicyEval
from mapu.models.entity import Handle
from mapu.models.lineage import DerivationEdge
from mapu.models.proposition import Proposition, PropositionParticipant
from mapu.providers.embeddings import EmbeddingProvider
from mapu.providers.llms import LLMProvider, LLMRequest
from mapu.query.types import PropositionHit
from mapu.repos.audit import ActivityRepo

if TYPE_CHECKING:
    from mapu.repos.gap import GapRepo

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
        embedding_provider: EmbeddingProvider | None = None,
        activity_repo: ActivityRepo | None = None,
        gap_repo: GapRepo | None = None,
        actor: str = "system",
    ) -> None:
        self._session = session
        self._llm = llm
        self._planner = LLMInvestigationPlanner(llm)
        self._executor = InvestigationExecutor(session, embedding_provider)
        self._evaluator = InvestigationEvaluator()
        self._budget = budget or InvestigationBudget()
        self._activity_repo = activity_repo
        self._gap_repo = gap_repo
        self._actor = actor
        self._logger = logging.getLogger(__name__)

    async def investigate(
        self,
        question: str,
        corpus_id: uuid.UUID,
        initial_entities: tuple[str, ...] = (),
        initial_predicates: tuple[str, ...] = (),
        initial_hits: tuple[PropositionHit, ...] = (),
        situation_id: uuid.UUID | None = None,
    ) -> InvestigationResult:
        state = InvestigationState(budget=self._budget)

        for hit in initial_hits:
            state.seen_proposition_ids.add(hit.proposition_id)

        termination: TerminationReason | None = None

        while termination is None:
            plan = await self._planner.plan(
                question,
                state,
                initial_entities,
                initial_predicates,
            )

            if not plan.actions:
                termination = TerminationReason.PLANNER_STOP
                break

            for action in plan.actions:
                obs = await self._executor.execute_action(
                    action,
                    corpus_id,
                    state,
                )
                state.observations.append(obs)

                self._evaluator.update_coverage(
                    state,
                    initial_entities,
                    initial_predicates,
                )

                termination = self._evaluator.should_terminate(state)
                if termination is not None:
                    break

        evidence = self._collect_evidence(state, initial_hits)
        gaps = self._identify_gaps(
            state,
            initial_entities,
            initial_predicates,
        )
        persisted_gap_ids = await self._persist_gaps(
            question=question,
            corpus_id=corpus_id,
            gaps=gaps,
            termination=termination,
        )
        next_steps = self._build_next_steps(
            question=question,
            state=state,
            gaps=gaps,
            termination=termination,
        )

        answer = await self._synthesize(question, evidence, gaps, state)
        findings = await self._derive_findings(question, evidence, state)

        persisted_ids = await self._persist_findings(findings, corpus_id, situation_id)

        result = InvestigationResult(
            answer=answer,
            evidence=evidence,
            gaps=gaps,
            findings=findings,
            metadata={
                **self._build_metadata(state, termination),
                "persisted_gap_ids": persisted_gap_ids,
            },
            termination_reason=termination or TerminationReason.PLANNER_STOP,
            persisted_proposition_ids=tuple(persisted_ids),
            next_steps=next_steps,
            structured_next_steps=build_structured_next_steps(
                corpus_id,
                next_steps,
                question=question,
                gaps=gaps,
                source="investigation",
            ),
        )

        if self._activity_repo is None:
            return result

        return await self._enrich_and_log(
            question=question,
            result=result,
            evidence_count=len(evidence),
            findings_count=len(findings),
            corpus_id=corpus_id,
        )

    async def _persist_gaps(
        self,
        *,
        question: str,
        corpus_id: uuid.UUID,
        gaps: tuple[str, ...],
        termination: TerminationReason | None,
    ) -> list[str]:
        gap_repo = self._gap_repo
        if gap_repo is None or not hasattr(gap_repo, "record_open_gap"):
            return []

        descriptions = list(gaps)
        if not descriptions and termination in {
            TerminationReason.BUDGET_EXHAUSTED,
            TerminationReason.DIMINISHING_RETURNS,
            TerminationReason.CONTRADICTION_FOUND,
        }:
            descriptions.append(
                f"Investigation stopped before clean coverage for: {question[:240]}"
            )

        persisted: list[str] = []
        for description in descriptions[:8]:
            desc = " ".join(str(description).strip().split())
            if not desc:
                continue
            is_conflict = termination == TerminationReason.CONTRADICTION_FOUND
            try:
                gap = await gap_repo.record_open_gap(
                    kind="investigation_gap",
                    description=desc,
                    detected_by=self._actor,
                    severity=(
                        "critical"
                        if is_conflict or termination == TerminationReason.BUDGET_EXHAUSTED
                        else "moderate"
                    ),
                    uncertainty_reason=(
                        "contradiction_or_supersession" if is_conflict else "missing_evidence"
                    ),
                    evidence_hypothesis={
                        "source": "investigation",
                        "question": question,
                        "termination_reason": (termination.value if termination else "unknown"),
                    },
                    next_action={
                        "action_type": "investigate",
                        "question": desc,
                        "rationale": (
                            "Persisted investigation gap needs targeted follow-up "
                            "before the next resumed session."
                        ),
                        "expected_uncertainty_reduction": 0.65,
                    },
                    expected_resolution=(
                        "Close this gap with source-backed evidence, explicit "
                        "dismissal, or repair/supersession."
                    ),
                    governance_tier="stale" if is_conflict else "provisional",
                    priority_score=5.0 if is_conflict else 3.5,
                )
            except Exception:
                self._logger.exception("Failed to persist investigation gap")
                continue
            persisted.append(str(gap.id))
        return persisted

    async def _enrich_and_log(
        self,
        question: str,
        result: InvestigationResult,
        evidence_count: int,
        findings_count: int,
        corpus_id: uuid.UUID,
    ) -> InvestigationResult:
        ranked = await self._enrich_next_steps_with_history(
            question=question,
            next_steps=result.next_steps,
        )
        next_result = InvestigationResult(
            answer=result.answer,
            evidence=result.evidence,
            gaps=result.gaps,
            findings=result.findings,
            metadata=result.metadata,
            termination_reason=result.termination_reason,
            persisted_proposition_ids=result.persisted_proposition_ids,
            next_steps=ranked,
            structured_next_steps=build_structured_next_steps(
                corpus_id,
                ranked,
                question=question,
                gaps=result.gaps,
                source="investigation",
            ),
        )

        try:
            await self._log_investigation_activity(
                question=question,
                result=next_result,
                evidence_count=evidence_count,
                findings_count=findings_count,
            )
        except Exception:
            self._logger.exception("Failed to persist investigation activity")
        return next_result

    async def _enrich_next_steps_with_history(
        self,
        question: str,
        next_steps: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not next_steps:
            return next_steps
        try:
            activities = await self._activity_repo.list(limit=240)
        except Exception:
            self._logger.exception(
                "Failed to load historical investigation activity for next-step ranking",
            )
            return next_steps

        return await prioritize_next_steps(next_steps, question, activities)

    async def _log_investigation_activity(
        self,
        question: str,
        result: InvestigationResult,
        evidence_count: int,
        findings_count: int,
    ) -> None:
        await self._activity_repo.log(
            event_type="investigation",
            actor=self._actor,
            entity_type="investigation",
            details={
                "question": question,
                "termination_reason": result.termination_reason.value,
                "evidence_count": evidence_count,
                "findings_count": findings_count,
                "next_steps": list(result.next_steps),
                "structured_next_steps": list(result.structured_next_steps),
                "gaps": list(result.gaps),
                "metadata": result.metadata,
            },
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
                evidence.append(
                    InvestigationEvidence(
                        proposition_id=hit.proposition_id,
                        normalized_text=hit.normalized_text,
                        source_span=hit.source_span_text,
                        authority_score=hit.authority_score,
                        document_id=hit.document_id,
                    )
                )

        for obs in state.observations:
            for ev in obs.evidence:
                if ev.proposition_id not in seen:
                    seen.add(ev.proposition_id)
                    evidence.append(ev)

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

        capped_evidence = evidence[:50]
        evidence_lines: list[str] = []
        for e in capped_evidence:
            if not e.normalized_text:
                continue
            line = f"- {e.normalized_text}"
            meta: list[str] = []
            if e.authority_score is not None:
                meta.append(f"authority: {e.authority_score:.2f}")
            if e.source_span:
                meta.append(f"source: {e.source_span[:200]}")
            if meta:
                line += f" ({', '.join(meta)})"
            evidence_lines.append(line)
        evidence_text = "\n".join(evidence_lines)

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

    async def _derive_findings(
        self,
        question: str,
        evidence: tuple[InvestigationEvidence, ...],
        state: InvestigationState,
    ) -> tuple[DerivedPropositionDraft, ...]:
        doc_ids = {e.document_id for e in evidence if e.document_id is not None}
        doc_ids.update(state.seen_document_ids)

        if len(doc_ids) < 2:
            return ()

        if not evidence:
            return ()

        if self._budget.max_llm_calls - state.llm_calls_used < 1:
            return ()

        capped = evidence[:50]
        evidence_text = "\n".join(
            f"[{i}] {e.normalized_text}" for i, e in enumerate(capped) if e.normalized_text
        )

        request = LLMRequest(
            system_prompt=(
                "You are a cross-document reasoning engine. Given evidence "
                "from multiple documents, identify connections that span "
                "documents. Return JSON with a 'findings' array. Each finding "
                "must have: normalized_text, predicate, subject_name, "
                "object_name (nullable), confidence (0-1), and "
                "evidence_indices (list of integers referencing the evidence)."
            ),
            user_prompt=(
                f"Question: {question}\n\nEvidence:\n{evidence_text}\n\n"
                "Identify cross-document connections."
            ),
            max_tokens=1024,
            temperature=0.1,
        )
        raw = await self._llm.complete_json(request)
        state.llm_calls_used += 1

        return _parse_findings(raw, capped)

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
            "termination_reason": (termination.value if termination else "unknown"),
            "steps": len(state.observations),
            "cross_document": state.documents_read >= 2,
            "document_ids": [str(d) for d in state.seen_document_ids],
        }

    def _build_next_steps(
        self,
        question: str,
        state: InvestigationState,
        gaps: tuple[str, ...],
        termination: TerminationReason | None,
    ) -> tuple[str, ...]:
        next_steps: list[str] = []

        for gap in gaps:
            if gap.startswith("No evidence found for entity: "):
                entity = gap.removeprefix("No evidence found for entity: ").strip()
                if entity:
                    next_steps.append(
                        f"Open an entity-focused pass for {entity!r}: "
                        f'query "What is known about {entity}?"',
                    )
            if gap.startswith("No evidence found for predicate: "):
                predicate = gap.removeprefix("No evidence found for predicate: ").strip()
                if predicate:
                    next_steps.append(
                        f"Expand predicate coverage: inspect sources for {predicate!r} "
                        f"relationships around this query.",
                    )

        if not gaps and state.known_entity_coverage >= 0.5 and state.seen_document_ids:
            doc_ids = ", ".join(str(d) for d in list(state.seen_document_ids)[:3])
            next_steps.append(
                f"If you need deeper evidence, load full documents: {doc_ids}",
            )

        if not next_steps:
            next_steps.append(
                f"Resume with a fresh query constrained to the current topic: {question[:120]}",
            )

        if termination in (
            TerminationReason.BUDGET_EXHAUSTED,
            TerminationReason.DIMINISHING_RETURNS,
        ):
            next_steps.append(
                "Coverage stalled before convergence; increase budget and re-run "
                "the investigation with higher action/LLM limits.",
            )

        return tuple(dict.fromkeys(next_steps))

    async def _persist_findings(
        self,
        findings: tuple[DerivedPropositionDraft, ...],
        corpus_id: uuid.UUID,
        situation_id: uuid.UUID | None = None,
    ) -> list[uuid.UUID]:
        from sqlalchemy.exc import IntegrityError

        if not findings:
            return []

        persisted: list[uuid.UUID] = []
        now = datetime.now(UTC)

        for draft in findings:
            if not draft.derivation_basis:
                continue

            subject_handle = await self._resolve_or_create_handle(
                draft.subject_name,
                "entity",
                corpus_id,
            )
            object_handle: Handle | None = None
            if draft.object_name:
                object_handle = await self._resolve_or_create_handle(
                    draft.object_name,
                    "entity",
                    corpus_id,
                )

            semantic_key = _compute_finding_key(
                frame_type=draft.frame_type,
                subject_handle_id=subject_handle.id,
                predicate=draft.predicate,
                object_handle_id=object_handle.id if object_handle else None,
            )

            existing = await self._session.execute(
                select(Proposition).where(
                    Proposition.corpus_id == corpus_id,
                    Proposition.semantic_key == semantic_key,
                ),
            )
            if existing.scalar_one_or_none() is not None:
                continue

            derived_range = await self._compute_derived_valid_range(
                draft.derivation_basis,
                corpus_id,
            )

            prop_id = uuid.uuid4()
            try:
                async with self._session.begin_nested():
                    prop = Proposition(
                        id=prop_id,
                        corpus_id=corpus_id,
                        frame_type=draft.frame_type,
                        subject_handle_id=subject_handle.id,
                        predicate=draft.predicate,
                        object_handle_id=object_handle.id if object_handle else None,
                        value=None,
                        polarity=True,
                        modality=None,
                        valid_range=derived_range,
                        normalized_text=draft.normalized_text,
                        qualifiers={},
                        semantic_key=semantic_key,
                        system_created=now,
                    )
                    self._session.add(prop)
                    self._session.add(
                        PropositionParticipant(
                            id=uuid.uuid4(),
                            proposition_id=prop_id,
                            handle_id=subject_handle.id,
                            corpus_id=corpus_id,
                            role="subject",
                            ordinal=0,
                        )
                    )
                    if object_handle is not None:
                        self._session.add(
                            PropositionParticipant(
                                id=uuid.uuid4(),
                                proposition_id=prop_id,
                                handle_id=object_handle.id,
                                corpus_id=corpus_id,
                                role="object",
                                ordinal=1,
                            )
                        )
                    for basis_id in draft.derivation_basis:
                        self._session.add(
                            DerivationEdge(
                                id=uuid.uuid4(),
                                corpus_id=corpus_id,
                                parent_proposition_id=basis_id,
                                child_proposition_id=prop_id,
                                derivation_type="cross_document",
                                derivation_method="investigation",
                                confidence=draft.confidence,
                                created_at=now,
                            )
                        )
                    spe = SourcePolicyEval(
                        id=uuid.uuid4(),
                        document_id=prop_id,
                        corpus_id=corpus_id,
                        policy_version="v1",
                        evaluator="investigation_derived",
                        document_type="derived_finding",
                        attestation_type="automated",
                        authority_score=draft.confidence * 0.7,
                        evaluated_at=now,
                    )
                    self._session.add(spe)
                    att_id = uuid.uuid4()
                    self._session.add(
                        Attestation(
                            id=att_id,
                            span_id=None,
                            proposition_id=prop_id,
                            corpus_id=corpus_id,
                            source_policy_eval_id=spe.id,
                            stance="derived",
                            extraction_method="investigation",
                            extraction_confidence=draft.confidence,
                            status="accepted",
                            system_created=now,
                        )
                    )
                    await self._session.flush()
                    if situation_id is not None:
                        self._session.add(
                            AttestationSituation(
                                attestation_id=att_id,
                                situation_id=situation_id,
                                corpus_id=corpus_id,
                                assignment_confidence=1.0,
                                assignment_basis="investigation_derived",
                            )
                        )
                        await self._session.flush()
            except IntegrityError:
                continue

            persisted.append(prop_id)

        return persisted

    async def _compute_derived_valid_range(
        self,
        basis_ids: tuple[uuid.UUID, ...],
        corpus_id: uuid.UUID,
    ) -> Range[datetime] | None:
        if not basis_ids:
            return None
        result = await self._session.execute(
            select(Proposition.valid_range).where(
                Proposition.id.in_(list(basis_ids)),
                Proposition.corpus_id == corpus_id,
            ),
        )
        ranges = [r for (r,) in result.all() if r is not None]
        if not ranges:
            return None
        lower = max(
            (r.lower for r in ranges if r.lower is not None),
            default=None,
        )
        upper = min(
            (r.upper for r in ranges if r.upper is not None),
            default=None,
        )
        if lower is not None and upper is not None and lower >= upper:
            return None
        return Range(lower, upper, bounds="[)")

    async def _resolve_or_create_handle(
        self,
        name: str,
        kind: str,
        corpus_id: uuid.UUID,
    ) -> Handle:
        result = await self._session.execute(
            select(Handle).where(
                Handle.corpus_id == corpus_id,
                Handle.canonical_name == name,
                Handle.kind == kind,
                Handle.status == "active",
            ),
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        handle = Handle(
            id=uuid.uuid4(),
            corpus_id=corpus_id,
            canonical_name=name,
            kind=kind,
            aliases=[],
            status="active",
            created_at=datetime.now(UTC),
        )
        self._session.add(handle)
        await self._session.flush()
        return handle


def _compute_finding_key(
    *,
    frame_type: str,
    subject_handle_id: uuid.UUID,
    predicate: str,
    object_handle_id: uuid.UUID | None,
) -> str:
    parts = [
        frame_type,
        str(subject_handle_id),
        predicate,
        str(object_handle_id) if object_handle_id else "",
    ]
    content = "|".join(parts)
    digest = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{frame_type}:{predicate}:{digest}"


def _parse_findings(
    raw: dict[str, Any],
    evidence: tuple[InvestigationEvidence, ...],
) -> tuple[DerivedPropositionDraft, ...]:
    findings_raw = raw.get("findings", [])
    if not isinstance(findings_raw, list):
        return ()

    drafts: list[DerivedPropositionDraft] = []
    for f in findings_raw:
        if not isinstance(f, dict):
            continue

        text = f.get("normalized_text", "")
        predicate = f.get("predicate", "")
        subject = f.get("subject_name", "")
        if not text or not predicate or not subject:
            continue

        indices = f.get("evidence_indices", [])
        if not isinstance(indices, list) or len(indices) < 2:
            continue

        valid_indices = list(
            dict.fromkeys(
                i
                for i in indices
                if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(evidence)
            )
        )
        if len(valid_indices) < 2:
            continue

        doc_ids = {
            evidence[i].document_id for i in valid_indices if evidence[i].document_id is not None
        }
        if len(doc_ids) < 2:
            continue

        prop_indices = [i for i in valid_indices if evidence[i].is_proposition]
        basis = (
            tuple(evidence[i].proposition_id for i in prop_indices)
            if prop_indices
            else tuple(evidence[i].proposition_id for i in valid_indices)
        )

        has_chunk_evidence = any(not evidence[i].is_proposition for i in valid_indices)
        chunk_only = len(prop_indices) == 0
        raw_confidence = f.get("confidence")
        if not isinstance(raw_confidence, (int, float)) or isinstance(raw_confidence, bool):
            continue
        confidence = float(raw_confidence)
        if not (0.0 <= confidence <= 1.0) or not math.isfinite(confidence):
            continue
        if chunk_only:
            confidence *= 0.6
        elif has_chunk_evidence and len(prop_indices) < len(valid_indices):
            confidence *= 0.85

        drafts.append(
            DerivedPropositionDraft(
                normalized_text=str(text),
                frame_type="finding",
                predicate=str(predicate),
                subject_name=str(subject),
                object_name=f.get("object_name"),
                derivation_basis=basis,
                confidence=confidence,
            )
        )

    return tuple(drafts)
