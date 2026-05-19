"""QueryService: facade for the full query pipeline."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.context_learning import (
    build_structured_next_steps,
    prioritize_next_steps,
    suggest_gap_based_next_steps,
)
from mapu.evidence.retrieval import ChunkRetrievalService, RetrievalConfig
from mapu.investigation.service import InvestigationService
from mapu.providers.embeddings import EmbeddingProvider
from mapu.providers.llms import LLMProvider
from mapu.query.direct import DirectLookupExecutor
from mapu.query.governor import CascadeGovernor
from mapu.query.structured import StructuredQueryExecutor
from mapu.query.synthesis import LLMSynthesizer, TemplateSynthesizer
from mapu.query.types import (
    ChunkHit,
    EpistemicStatus,
    IntentClassifier,
    PropositionHit,
    QueryIntent,
    QueryPlan,
    QueryRequest,
    QueryResult,
    Tier,
)
from mapu.repos.audit import ActivityRepo

if TYPE_CHECKING:
    from mapu.repos.gap import GapRepo


class QueryService:
    """Orchestrates the query pipeline: classify → plan → execute → synthesize."""

    def __init__(
        self,
        session: AsyncSession,
        intent_classifier: IntentClassifier,
        *,
        gap_repo: GapRepo | None = None,
        activity_repo: ActivityRepo | None = None,
        actor: str = "system",
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._gap_repo = gap_repo
        self._activity_repo = activity_repo
        self._actor = actor
        self._embedding_provider = embedding_provider
        self._governor = CascadeGovernor(
            intent_classifier=intent_classifier,
        )
        self._direct = DirectLookupExecutor(session)
        self._structured = StructuredQueryExecutor(session)
        self._template_synth = TemplateSynthesizer()
        self._llm_synth = LLMSynthesizer(llm_provider) if llm_provider else None
        self._investigation = (
            InvestigationService(
                session,
                llm_provider,
                embedding_provider=embedding_provider,
                gap_repo=gap_repo,
                activity_repo=activity_repo,
                actor=actor,
            )
            if llm_provider
            else None
        )
        self._logger = logging.getLogger(__name__)

    async def query(self, request: QueryRequest) -> QueryResult:
        plan = await self._governor.plan(request)

        if plan.selected_tier == Tier.INVESTIGATION:
            return await self._handle_investigation(request, plan)

        hits = await self._execute_tier(plan, request)

        if not hits and plan.selected_tier == Tier.DIRECT:
            plan = plan.__class__(
                intent=plan.intent,
                selected_tier=Tier.STRUCTURED,
                entities_extracted=plan.entities_extracted,
                predicates_extracted=plan.predicates_extracted,
                escalation_reason="No results at direct tier",
            )
            hits = await self._execute_tier(plan, request)

        hits = _sanitize_hits_for_question(request.question, hits)
        hits = _rerank_hits_for_question(request.question, hits)

        chunk_hits = await self._chunk_fallback(request, hits)
        synthesis = await self._synthesize(request, plan, hits)
        if synthesis is None and chunk_hits:
            synthesis = _chunk_evidence_answer(chunk_hits)
        epistemic = _assess_epistemic_status(hits, chunk_hits, plan)

        result = QueryResult(
            request=request,
            intent=plan.intent,
            tier_used=plan.selected_tier,
            hits=tuple(hits),
            epistemic_status=epistemic,
            synthesis=synthesis,
            chunk_hits=tuple(chunk_hits),
            next_steps=self._build_next_steps(
                plan=plan,
                request=request,
                hits=hits,
                epistemic=epistemic,
            ),
            metadata={
                "entities": plan.entities_extracted,
                "predicates": plan.predicates_extracted,
            },
        )
        return await self._enrich_query_result(request, result)

    async def _handle_investigation(
        self,
        request: QueryRequest,
        plan: QueryPlan,
    ) -> QueryResult:
        if self._investigation is None:
            return await self._structured_investigation_fallback(request, plan)

        result = await self._investigation.investigate(
            question=request.question,
            corpus_id=request.corpus_id,
            initial_entities=plan.entities_extracted,
            initial_predicates=plan.predicates_extracted,
            situation_id=request.situation_id,
        )

        query_result = QueryResult(
            request=request,
            intent=plan.intent,
            tier_used=Tier.INVESTIGATION,
            hits=(),
            synthesis=result.answer,
            gaps=result.gaps,
            metadata={
                "investigation": result.metadata,
                "escalation_reason": plan.escalation_reason,
                "evidence_count": len(result.evidence),
                "findings_count": len(result.findings),
                "findings": [
                    {
                        "normalized_text": f.normalized_text,
                        "predicate": f.predicate,
                        "subject_name": f.subject_name,
                        "object_name": f.object_name,
                        "confidence": f.confidence,
                    }
                    for f in result.findings
                ],
            },
            next_steps=result.next_steps,
        )
        return await self._enrich_query_result(request, query_result)

    async def _execute_tier(
        self,
        plan: QueryPlan,
        request: QueryRequest,
    ) -> Sequence[PropositionHit]:
        if plan.selected_tier == Tier.DIRECT:
            return await self._direct.execute(plan, request)
        if plan.selected_tier == Tier.STRUCTURED:
            return await self._structured.execute(plan, request)
        if plan.selected_tier == Tier.SYNTHESIS:
            return await self._structured.execute(plan, request)
        return ()

    async def _structured_investigation_fallback(
        self,
        request: QueryRequest,
        plan: QueryPlan,
    ) -> QueryResult:
        all_hits: list[PropositionHit] = []
        seen: set[object] = set()

        initial = await self._structured.execute(plan, request)
        for h in initial:
            if h.proposition_id not in seen:
                seen.add(h.proposition_id)
                all_hits.append(h)

        discovered_entities: set[str] = set()
        for h in all_hits:
            if h.object_name:
                discovered_entities.add(h.object_name)
            discovered_entities.add(h.subject_name)

        known = {e.lower() for e in plan.entities_extracted}
        new_entities = tuple(e for e in discovered_entities if e.lower() not in known)[:3]
        for entity in new_entities:
            expansion_plan = QueryPlan(
                intent=QueryIntent.LIST,
                selected_tier=Tier.STRUCTURED,
                entities_extracted=(entity,),
                predicates_extracted=plan.predicates_extracted,
            )
            expansion_hits = await self._structured.execute(expansion_plan, request)
            for h in expansion_hits:
                if h.proposition_id not in seen:
                    seen.add(h.proposition_id)
                    all_hits.append(h)

        chunk_hits = await self._chunk_fallback(request, all_hits)
        synthesis = await self._synthesize(request, plan, all_hits)
        if synthesis is None and chunk_hits:
            synthesis = _chunk_evidence_answer(chunk_hits)
        epistemic = _assess_epistemic_status(all_hits, chunk_hits, plan)

        gaps: list[str] = []
        for e in plan.entities_extracted:
            if not any(
                e.lower() in (h.subject_name.lower(), (h.object_name or "").lower())
                for h in all_hits
            ):
                gaps.append(f"No evidence found for entity: {e}")

        query_result = QueryResult(
            request=request,
            intent=plan.intent,
            tier_used=Tier.STRUCTURED,
            hits=tuple(all_hits),
            epistemic_status=epistemic,
            synthesis=synthesis,
            gaps=tuple(gaps),
            chunk_hits=tuple(chunk_hits),
            metadata={
                "escalation_reason": plan.escalation_reason,
                "llm_fallback": "structured_investigation",
                "expansion_entities": list(new_entities),
            },
            next_steps=self._build_next_steps(
                plan=plan,
                request=request,
                hits=tuple(all_hits),
                epistemic=epistemic,
                explicit_gaps=tuple(gaps),
            ),
        )
        return await self._enrich_query_result(request, query_result)

    async def _enrich_query_result(
        self,
        request: QueryRequest,
        result: QueryResult,
    ) -> QueryResult:
        result = await self._persist_result_gaps(request, result)
        result = await self._enrich_next_steps_with_gaps(request, result)
        if self._activity_repo is not None:
            result = await self._enrich_next_steps_with_history(request, result)

        result = self._attach_structured_next_steps(request, result)

        if self._activity_repo is None:
            return result
        await self._log_query_activity(request, result)
        return result

    async def _persist_result_gaps(
        self,
        request: QueryRequest,
        result: QueryResult,
    ) -> QueryResult:
        gap_repo = self._gap_repo
        if gap_repo is None or not hasattr(gap_repo, "record_open_gap"):
            return result

        gap_descriptions = list(result.gaps)
        if not gap_descriptions and result.epistemic_status in {
            EpistemicStatus.INSUFFICIENT,
            EpistemicStatus.UNKNOWN,
            EpistemicStatus.CONFLICTING,
        }:
            gap_descriptions.append(
                f"Insufficient persisted evidence for query: {request.question[:240]}"
            )

        if not gap_descriptions:
            return result

        persisted_gap_ids: list[str] = []
        for gap_description in gap_descriptions[:8]:
            desc = " ".join(str(gap_description).strip().split())
            if not desc:
                continue
            is_conflict = result.epistemic_status == EpistemicStatus.CONFLICTING
            try:
                gap = await gap_repo.record_open_gap(
                    kind="query_gap",
                    description=desc,
                    detected_by=self._actor,
                    severity="critical" if is_conflict else "moderate",
                    uncertainty_reason=(
                        "contradiction_or_supersession" if is_conflict else "missing_evidence"
                    ),
                    evidence_hypothesis={
                        "source": "query",
                        "question": request.question,
                        "epistemic_status": result.epistemic_status.value,
                        "tier": result.tier_used.name,
                        "hit_count": len(result.hits),
                        "chunk_hit_count": len(result.chunk_hits),
                    },
                    next_action={
                        "action_type": "investigate",
                        "question": desc,
                        "rationale": (
                            "Persisted query gap needs targeted evidence collection before reuse."
                        ),
                        "expected_uncertainty_reduction": 0.55,
                    },
                    expected_resolution=(
                        "Find source-backed evidence, resolve the contradiction, "
                        "or explicitly dismiss this gap."
                    ),
                    governance_tier="stale" if is_conflict else "provisional",
                    priority_score=5.0 if is_conflict else 3.0,
                )
            except Exception:
                self._logger.exception("Failed to persist query gap")
                continue
            persisted_gap_ids.append(str(gap.id))

        if not persisted_gap_ids:
            return result

        metadata = dict(result.metadata)
        metadata["persisted_gap_ids"] = persisted_gap_ids
        return QueryResult(
            request=result.request,
            intent=result.intent,
            tier_used=result.tier_used,
            hits=result.hits,
            epistemic_status=result.epistemic_status,
            synthesis=result.synthesis,
            gaps=result.gaps,
            chunk_hits=result.chunk_hits,
            metadata=metadata,
            next_steps=result.next_steps,
            structured_next_steps=result.structured_next_steps,
        )

    def _attach_structured_next_steps(
        self,
        request: QueryRequest,
        result: QueryResult,
    ) -> QueryResult:
        return QueryResult(
            request=result.request,
            intent=result.intent,
            tier_used=result.tier_used,
            hits=result.hits,
            epistemic_status=result.epistemic_status,
            synthesis=result.synthesis,
            gaps=result.gaps,
            chunk_hits=result.chunk_hits,
            metadata=result.metadata,
            next_steps=result.next_steps,
            structured_next_steps=build_structured_next_steps(
                request.corpus_id,
                result.next_steps,
                question=request.question,
                gaps=result.gaps,
                source="query",
            ),
        )

    async def _enrich_next_steps_with_gaps(
        self,
        request: QueryRequest,
        result: QueryResult,
    ) -> QueryResult:
        if not result.next_steps:
            return result

        gap_repo = self._gap_repo
        if gap_repo is None:
            return result

        try:
            gaps = await gap_repo.open_gaps(limit=32)
        except Exception:
            self._logger.exception("Failed to load open knowledge gaps for next-step guidance")
            return result

        if not gaps:
            return result

        gap_steps = suggest_gap_based_next_steps(
            request.question,
            gaps,
            limit=3,
        )
        if not gap_steps:
            return result

        next_steps = tuple(dict.fromkeys(tuple(result.next_steps) + gap_steps))
        return QueryResult(
            request=result.request,
            intent=result.intent,
            tier_used=result.tier_used,
            hits=result.hits,
            epistemic_status=result.epistemic_status,
            synthesis=result.synthesis,
            gaps=result.gaps,
            chunk_hits=result.chunk_hits,
            metadata=result.metadata,
            next_steps=next_steps,
            structured_next_steps=result.structured_next_steps,
        )

    async def _enrich_next_steps_with_history(
        self,
        request: QueryRequest,
        result: QueryResult,
    ) -> QueryResult:
        if not result.next_steps:
            return result
        try:
            activities = await self._activity_repo.list(limit=240)
        except Exception:
            self._logger.exception("Failed to load query activity history")
            return result

        ranked_steps = await prioritize_next_steps(
            result.next_steps,
            request.question,
            activities,
        )
        if not ranked_steps:
            return result
        return QueryResult(
            request=result.request,
            intent=result.intent,
            tier_used=result.tier_used,
            hits=result.hits,
            epistemic_status=result.epistemic_status,
            synthesis=result.synthesis,
            gaps=result.gaps,
            chunk_hits=result.chunk_hits,
            metadata=result.metadata,
            next_steps=ranked_steps,
            structured_next_steps=result.structured_next_steps,
        )

    async def _log_query_activity(
        self,
        request: QueryRequest,
        result: QueryResult,
    ) -> None:
        if self._activity_repo is None:
            return
        try:
            await self._activity_repo.log(
                event_type="query",
                actor=self._actor,
                entity_type="query",
                details={
                    "question": request.question,
                    "intent": result.intent.value,
                    "tier": result.tier_used.name,
                    "epistemic_status": result.epistemic_status.value,
                    "hits": len(result.hits),
                    "chunks": len(result.chunk_hits),
                    "metadata": result.metadata,
                    "next_steps": list(result.next_steps),
                    "structured_next_steps": list(result.structured_next_steps),
                },
            )
        except Exception:
            self._logger.exception("Failed to persist query activity")

    def _build_next_steps(
        self,
        *,
        plan: QueryPlan,
        request: QueryRequest,
        hits: Sequence[PropositionHit],
        epistemic: EpistemicStatus,
        explicit_gaps: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        next_steps: list[str] = []

        if explicit_gaps:
            next_steps.extend(explicit_gaps)
        elif not hits:
            if plan.entities_extracted:
                for entity in plan.entities_extracted[:3]:
                    next_steps.append(
                        f"Open an entity-focused pass: what is known about '{entity}'?"
                    )
            if plan.predicates_extracted:
                for predicate in plan.predicates_extracted[:2]:
                    next_steps.append(
                        f"Inspect relation-level evidence for predicate '{predicate}'."
                    )
            if not next_steps:
                next_steps.append(
                    "No direct evidence found at this tier; run investigation for deeper retrieval."
                )
        elif epistemic in {EpistemicStatus.INSUFFICIENT, EpistemicStatus.UNKNOWN}:
            next_steps.append(f'Run investigation for: "{request.question}" with a higher budget.')

        if not next_steps:
            next_steps.append(
                "If this answer is insufficient, request a focused investigation "
                "with the same question."
            )

        return tuple(dict.fromkeys(next_steps))

    async def _chunk_fallback(
        self,
        request: QueryRequest,
        proposition_hits: Sequence[PropositionHit],
    ) -> list[ChunkHit]:
        if self._embedding_provider is None:
            return []
        weak_threshold = 3
        if proposition_hits and len(proposition_hits) >= weak_threshold:
            return []
        query_vec = await self._embedding_provider.embed_texts([request.question])
        if not query_vec:
            return []
        retrieval = ChunkRetrievalService(
            self._session,
            request.corpus_id,
            self._embedding_provider.model_ref,
        )
        results = await retrieval.search(
            list(query_vec[0]),
            RetrievalConfig(top_k=min(request.max_results, 10)),
        )
        return [
            ChunkHit(
                chunk_id=r.chunk_id,
                text=r.text,
                score=r.score,
                expression_id=r.expression_id,
            )
            for r in results
        ]

    async def _synthesize(
        self,
        request: QueryRequest,
        plan: QueryPlan,
        hits: Sequence[PropositionHit],
    ) -> str | None:
        if not hits:
            return None

        if plan.selected_tier <= Tier.STRUCTURED:
            return await self._template_synth.synthesize(
                request.question,
                hits,
                plan.intent,
            )

        if self._llm_synth is not None:
            return await self._llm_synth.synthesize(
                request.question,
                hits,
                plan.intent,
            )

        return await self._template_synth.synthesize(
            request.question,
            hits,
            plan.intent,
        )


def _assess_epistemic_status(
    hits: Sequence[PropositionHit],
    chunk_hits: list[ChunkHit],
    plan: QueryPlan,
) -> EpistemicStatus:
    if not hits and not chunk_hits:
        return EpistemicStatus.UNKNOWN

    if not hits:
        return EpistemicStatus.INSUFFICIENT

    truth_statuses = {h.truth_status for h in hits if h.truth_status}
    has_conflict = len(truth_statuses) > 1 and "contested" in truth_statuses
    if has_conflict:
        return EpistemicStatus.CONFLICTING

    avg_confidence = sum(h.extraction_confidence for h in hits) / len(hits)
    obligation_hits = [
        h for h in hits if (h.predicate or "").lower().startswith(("shall_", "must_", "requires"))
    ]
    if obligation_hits:
        avg_auth = sum(float(h.authority_score or 0.0) for h in obligation_hits) / len(
            obligation_hits
        )
        if len(obligation_hits) >= 2 and avg_auth >= 0.6:
            return EpistemicStatus.SUFFICIENT
    if avg_confidence < 0.5 or len(hits) < 2:
        return EpistemicStatus.INSUFFICIENT

    return EpistemicStatus.SUFFICIENT


def _chunk_evidence_answer(chunk_hits: Sequence[ChunkHit]) -> str:
    excerpts: list[str] = []
    for hit in chunk_hits[:3]:
        text = " ".join(hit.text.split())
        if len(text) > 360:
            text = text[:357].rstrip() + "..."
        excerpts.append(f"- {text}")
    return (
        "No structured proposition answer was found. Relevant source excerpts:\n"
        + "\n".join(excerpts)
    )


_OBLIGATION_QUERY_RE = re.compile(
    r"\b(obligation|required|must|shall|duty|duties|required to)\b", re.I
)


def _rerank_hits_for_question(
    question: str,
    hits: Sequence[PropositionHit],
) -> tuple[PropositionHit, ...]:
    if not hits:
        return ()
    q = question.lower()
    if _OBLIGATION_QUERY_RE.search(q) is None:
        return tuple(hits)
    if not hits:
        return ()

    wants_reports = "report" in q or "reporting" in q

    def _score(h: PropositionHit) -> tuple[float, float, float, float]:
        p = (h.predicate or "").lower()
        txt = (h.normalized_text or "").lower()
        obj = (h.object_name or "").lower()
        obligation = 0.0
        if p.startswith("shall_") or p.startswith("must_") or "shall " in txt or "must " in txt:
            obligation = 2.0
        elif p.startswith("requires") or "required" in txt:
            obligation = 1.5
        elif p.startswith("may_") or " may " in txt:
            obligation = 0.3
        object_quality = 0.0
        if wants_reports:
            if "report" in obj:
                object_quality += 0.6
            if any(tok in obj for tok in ("bank", "corp", "llc", "inc", "ltd")):
                object_quality -= 0.4
        return (
            obligation,
            object_quality,
            float(h.authority_score) if h.authority_score is not None else 0.0,
            float(h.extraction_confidence),
        )

    return tuple(sorted(hits, key=_score, reverse=True))


def _filter_malformed_obligation_hits(
    question_lower: str,
    hits: Sequence[PropositionHit],
) -> list[PropositionHit]:
    wants_deliverable = any(
        tok in question_lower for tok in ("report", "statement", "document", "deliverable")
    )
    if not wants_deliverable:
        return list(hits)

    filtered: list[PropositionHit] = []
    for h in hits:
        p = (h.predicate or "").lower()
        if not p.startswith(("shall_", "must_", "requires")):
            filtered.append(h)
            continue
        obj = (h.object_name or "").lower()
        if not obj:
            filtered.append(h)
            continue
        if "report" in obj or "statement" in obj or "document" in obj or "deliverable" in obj:
            filtered.append(h)
            continue
        if any(
            tok in obj for tok in ("bank", "corp", "llc", "inc", "ltd", "company", "organization")
        ):
            continue
        filtered.append(h)
    return filtered


def _sanitize_hits_for_question(
    question: str,
    hits: Sequence[PropositionHit],
) -> tuple[PropositionHit, ...]:
    if not hits:
        return ()
    q = question.lower()
    return tuple(_filter_malformed_obligation_hits(q, hits))
