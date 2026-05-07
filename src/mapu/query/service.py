"""QueryService: facade for the full query pipeline."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from mapu.investigation.service import InvestigationService
from mapu.providers.embeddings import EmbeddingProvider
from mapu.providers.llms import LLMProvider
from mapu.query.direct import DirectLookupExecutor
from mapu.query.governor import CascadeGovernor
from mapu.query.structured import StructuredQueryExecutor
from mapu.query.synthesis import LLMSynthesizer, TemplateSynthesizer
from mapu.query.types import (
    IntentClassifier,
    PropositionHit,
    QueryPlan,
    QueryRequest,
    QueryResult,
    Tier,
)


class QueryService:
    """Orchestrates the query pipeline: classify → plan → execute → synthesize."""

    def __init__(
        self,
        session: AsyncSession,
        intent_classifier: IntentClassifier,
        llm_provider: LLMProvider | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._governor = CascadeGovernor(
            intent_classifier=intent_classifier,
        )
        self._direct = DirectLookupExecutor(session)
        self._structured = StructuredQueryExecutor(session)
        self._template_synth = TemplateSynthesizer()
        self._llm_synth = (
            LLMSynthesizer(llm_provider) if llm_provider else None
        )
        self._investigation = (
            InvestigationService(
                session, llm_provider,
                embedding_provider=embedding_provider,
            )
            if llm_provider else None
        )

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

        synthesis = await self._synthesize(request, plan, hits)

        return QueryResult(
            request=request,
            intent=plan.intent,
            tier_used=plan.selected_tier,
            hits=tuple(hits),
            synthesis=synthesis,
            metadata={
                "entities": plan.entities_extracted,
                "predicates": plan.predicates_extracted,
            },
        )

    async def _handle_investigation(
        self, request: QueryRequest, plan: QueryPlan,
    ) -> QueryResult:
        if self._investigation is None:
            return QueryResult(
                request=request,
                intent=plan.intent,
                tier_used=Tier.INVESTIGATION,
                hits=(),
                synthesis=(
                    "Investigation requires an LLM provider "
                    "but none was configured."
                ),
                metadata={"escalation_reason": plan.escalation_reason},
            )

        result = await self._investigation.investigate(
            question=request.question,
            corpus_id=request.corpus_id,
            initial_entities=plan.entities_extracted,
            initial_predicates=plan.predicates_extracted,
            situation_id=request.situation_id,
        )

        return QueryResult(
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
        )

    async def _execute_tier(
        self, plan: QueryPlan, request: QueryRequest,
    ) -> Sequence[PropositionHit]:
        if plan.selected_tier == Tier.DIRECT:
            return await self._direct.execute(plan, request)
        if plan.selected_tier == Tier.STRUCTURED:
            return await self._structured.execute(plan, request)
        if plan.selected_tier == Tier.SYNTHESIS:
            return await self._structured.execute(plan, request)
        return ()

    async def _synthesize(
        self, request: QueryRequest, plan: QueryPlan, hits: Sequence[PropositionHit],
    ) -> str | None:
        if not hits:
            return None

        if plan.selected_tier <= Tier.STRUCTURED:
            return await self._template_synth.synthesize(
                request.question, hits, plan.intent,
            )

        if self._llm_synth is not None:
            return await self._llm_synth.synthesize(
                request.question, hits, plan.intent,
            )

        return await self._template_synth.synthesize(
            request.question, hits, plan.intent,
        )
