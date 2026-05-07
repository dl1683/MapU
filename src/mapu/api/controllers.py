"""Litestar REST API controllers for MapU."""

from __future__ import annotations

import uuid

from litestar import Controller, get, post
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.api.dtos import (
    CorpusCreate,
    CorpusResponse,
    HandleResponse,
    HealthResponse,
    HitResponse,
    IngestRequestDTO,
    IngestResponse,
    QueryRequestDTO,
    QueryResponse,
    RepairApplyResponse,
    RepairApproveResponse,
    RepairPreviewResponse,
    RepairProposeRequest,
    RepairProposeResponse,
)
from mapu.models.corpus import Corpus


async def _require_corpus(db_session: AsyncSession, corpus_id: uuid.UUID) -> None:
    from litestar.exceptions import NotFoundException

    stmt = select(Corpus.id).where(Corpus.id == corpus_id).limit(1)
    result = await db_session.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise NotFoundException(detail=f"Corpus {corpus_id} not found")


class HealthController(Controller):
    path = "/health"

    @get()
    async def health(self) -> HealthResponse:
        return HealthResponse(status="ok", version="0.1.0")


class CorpusController(Controller):
    path = "/corpora"

    @get()
    async def list_corpora(
        self, db_session: AsyncSession, limit: int = 100,
    ) -> list[CorpusResponse]:
        limit = min(max(limit, 1), 500)
        stmt = select(Corpus).order_by(Corpus.created_at.desc()).limit(limit)
        result = await db_session.execute(stmt)
        return [
            CorpusResponse(id=c.id, name=c.name, description=c.description)
            for c in result.scalars().all()
        ]

    @post()
    async def create_corpus(
        self, data: CorpusCreate, db_session: AsyncSession,
    ) -> CorpusResponse:
        corpus = Corpus(name=data.name, description=data.description)
        db_session.add(corpus)
        await db_session.flush()
        return CorpusResponse(id=corpus.id, name=corpus.name, description=corpus.description)

    @get("/{corpus_id:uuid}")
    async def get_corpus(
        self, corpus_id: uuid.UUID, db_session: AsyncSession,
    ) -> CorpusResponse:
        from litestar.exceptions import NotFoundException

        stmt = select(Corpus).where(Corpus.id == corpus_id)
        result = await db_session.execute(stmt)
        corpus = result.scalar_one_or_none()
        if corpus is None:
            raise NotFoundException(detail=f"Corpus {corpus_id} not found")
        return CorpusResponse(id=corpus.id, name=corpus.name, description=corpus.description)


class QueryController(Controller):
    path = "/corpora/{corpus_id:uuid}/query"

    @post()
    async def query(
        self,
        corpus_id: uuid.UUID,
        data: QueryRequestDTO,
        db_session: AsyncSession,
    ) -> QueryResponse:
        from mapu.query.intent import HeuristicIntentClassifier
        from mapu.query.service import QueryService
        from mapu.query.types import QueryRequest

        await _require_corpus(db_session, corpus_id)
        from mapu.providers.embeddings import get_default_embedding_provider
        from mapu.providers.llms import get_default_llm_provider

        classifier = HeuristicIntentClassifier()
        svc = QueryService(
            db_session, classifier,
            llm_provider=get_default_llm_provider(),
            embedding_provider=get_default_embedding_provider(),
        )
        request = QueryRequest(
            corpus_id=corpus_id,
            question=data.question,
            max_results=data.max_results,
            situation_id=data.situation_id,
        )
        result = await svc.query(request)
        return QueryResponse(
            intent=result.intent.value,
            tier_used=result.tier_used.name,
            synthesis=result.synthesis,
            hits=[
                HitResponse(
                    proposition_id=h.proposition_id,
                    normalized_text=h.normalized_text,
                    predicate=h.predicate,
                    subject_name=h.subject_name,
                    object_name=h.object_name,
                    confidence=h.extraction_confidence,
                    authority_score=h.authority_score,
                )
                for h in result.hits
            ],
            gaps=list(result.gaps),
        )


class DocumentController(Controller):
    path = "/corpora/{corpus_id:uuid}/documents"

    @post()
    async def ingest(
        self,
        corpus_id: uuid.UUID,
        data: IngestRequestDTO,
        db_session: AsyncSession,
    ) -> IngestResponse:
        from mapu.evidence.chunking import SpanAwareChunker
        from mapu.evidence.ingest import IngestionService
        from mapu.evidence.parsers import ParserRegistry
        from mapu.evidence.types import DocumentBlob
        from mapu.providers.embeddings import get_default_embedding_provider

        await _require_corpus(db_session, corpus_id)
        registry = ParserRegistry.create_default()
        chunker = SpanAwareChunker()
        svc = IngestionService(
            db_session, corpus_id, registry, chunker,
            embedding_provider=get_default_embedding_provider(),
        )
        blob = DocumentBlob(
            content=data.content.encode("utf-8"),
            mime_type=data.mime_type,
            source_uri=data.source_uri,
        )
        result = await svc.ingest(blob)
        return IngestResponse(
            document_id=result.document_id,
            expression_id=result.expression_id,
            spans=result.span_count,
            chunks=result.chunk_count,
            embeddings=result.embedding_count,
        )


class EntityController(Controller):
    path = "/corpora/{corpus_id:uuid}/entities"

    @get()
    async def search_entities(
        self,
        corpus_id: uuid.UUID,
        db_session: AsyncSession,
        name: str = "",
        limit: int = 20,
    ) -> list[HandleResponse]:
        from mapu.models.entity import Handle
        from mapu.query.direct import _escape_like

        await _require_corpus(db_session, corpus_id)
        limit = min(max(limit, 1), 100)
        stmt = select(Handle).where(
            Handle.corpus_id == corpus_id,
            Handle.status == "active",
        )
        if name:
            stmt = stmt.where(Handle.canonical_name.ilike(f"%{_escape_like(name)}%"))
        stmt = stmt.limit(limit)

        result = await db_session.execute(stmt)
        return [
            HandleResponse(
                id=h.id,
                canonical_name=h.canonical_name,
                kind=h.kind,
                aliases=list(h.aliases) if h.aliases else [],
            )
            for h in result.scalars().all()
        ]


class RepairController(Controller):
    path = "/corpora/{corpus_id:uuid}/repair"

    @post("/preview")
    async def preview(
        self,
        corpus_id: uuid.UUID,
        proposition_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> RepairPreviewResponse:
        from mapu.repair.blast_radius import compute_blast_radius

        await _require_corpus(db_session, corpus_id)
        report = await compute_blast_radius(db_session, corpus_id, proposition_id)
        return RepairPreviewResponse(
            root_proposition_id=report.root_proposition_id,
            affected_count=len(report.affected_proposition_ids),
            recompute_only_count=len(report.recompute_only_proposition_ids),
            risk_level=report.risk_level.value,
            max_depth=report.max_depth_seen,
            depth_limited=report.depth_limited,
        )

    @post("/propose")
    async def propose(
        self,
        corpus_id: uuid.UUID,
        data: RepairProposeRequest,
        db_session: AsyncSession,
    ) -> RepairProposeResponse:
        from mapu.repair.service import RepairService

        await _require_corpus(db_session, corpus_id)
        svc = RepairService(db_session, corpus_id)
        preview = await svc.preview_retraction(
            proposition_id=data.proposition_id,
            reason=data.reason,
            actor=data.actor,
        )
        changeset_id = await svc.propose(preview, description=data.reason)
        return RepairProposeResponse(
            changeset_id=changeset_id,
            risk_level=preview.risk_level.value,
            affected_count=len(preview.blast_radius.affected_proposition_ids),
        )

    @post("/approve/{changeset_id:uuid}")
    async def approve(
        self,
        corpus_id: uuid.UUID,
        changeset_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> RepairApproveResponse:
        from mapu.repos.review import ChangesetRepo
        from mapu.types import ChangesetStatus

        await _require_corpus(db_session, corpus_id)
        repo = ChangesetRepo(db_session, corpus_id)
        await repo.transition(changeset_id, ChangesetStatus.APPROVED.value)
        return RepairApproveResponse(
            changeset_id=changeset_id,
            status=ChangesetStatus.APPROVED.value,
        )

    @post("/apply/{changeset_id:uuid}")
    async def apply(
        self,
        corpus_id: uuid.UUID,
        changeset_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> RepairApplyResponse:
        from mapu.repair.service import RepairService

        await _require_corpus(db_session, corpus_id)
        svc = RepairService(db_session, corpus_id)
        result = await svc.apply(changeset_id)
        return RepairApplyResponse(
            changeset_id=result.changeset_id,
            success=result.success,
            operations_executed=result.operations_executed,
            recomputed_propositions=result.recomputed_propositions,
            gaps_created=result.gaps_created,
            errors=result.errors,
        )


def all_controllers() -> list[type[Controller]]:
    return [
        HealthController,
        CorpusController,
        QueryController,
        DocumentController,
        EntityController,
        RepairController,
    ]
