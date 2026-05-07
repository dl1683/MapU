"""QueryService: facade for the full query pipeline."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

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
        self._embedding_provider = embedding_provider
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

        chunk_hits = await self._chunk_fallback(request, hits)
        synthesis = await self._synthesize(request, plan, hits)

        return QueryResult(
            request=request,
            intent=plan.intent,
            tier_used=plan.selected_tier,
            hits=tuple(hits),
            synthesis=synthesis,
            chunk_hits=tuple(chunk_hits),
            metadata={
                "entities": plan.entities_extracted,
                "predicates": plan.predicates_extracted,
            },
        )

    async def _handle_investigation(
        self, request: QueryRequest, plan: QueryPlan,
    ) -> QueryResult:
        if self._investigation is None:
            hits = await self._structured.execute(plan, request)
            chunk_hits = await self._chunk_fallback(request, hits)
            return QueryResult(
                request=request,
                intent=plan.intent,
                tier_used=Tier.STRUCTURED,
                hits=tuple(hits),
                chunk_hits=tuple(chunk_hits) if chunk_hits else (),
                synthesis=None,
                metadata={
                    "escalation_reason": plan.escalation_reason,
                    "llm_fallback": "structured_query",
                },
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
            self._session, request.corpus_id, self._embedding_provider.model_ref,
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
