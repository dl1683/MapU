"""Litestar REST API controllers for MapU."""

from __future__ import annotations

import uuid

from litestar import Controller, get, post
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mapu.api.dtos import (
    ChunkHitResponse,
    ContributePropositionRequest,
    ContributePropositionResponse,
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
    ReviewAttestationRequest,
    ReviewAttestationResponse,
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
            as_of=data.as_of,
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
                    truth_status=h.truth_status,
                    source_span_text=h.source_span_text,
                    expression_id=h.document_id,
                    valid_from=h.valid_from,
                    valid_to=h.valid_to,
                )
                for h in result.hits
            ],
            gaps=list(result.gaps),
            chunk_hits=[
                ChunkHitResponse(
                    chunk_id=ch.chunk_id,
                    text=ch.text,
                    score=ch.score,
                )
                for ch in result.chunk_hits
            ],
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
        from mapu.extraction import get_default_extractors
        from mapu.providers.embeddings import get_default_embedding_provider

        from mapu.config import EmbeddingSettings

        await _require_corpus(db_session, corpus_id)
        registry = ParserRegistry.create_default()
        chunker = SpanAwareChunker()
        svc = IngestionService(
            db_session, corpus_id, registry, chunker,
            embedding_provider=get_default_embedding_provider(),
            extractors=get_default_extractors(),
            embedding_batch_size=EmbeddingSettings().batch_size,
        )
        metadata: dict[str, str] = {}
        if data.document_type:
            metadata["document_type"] = data.document_type
        if data.publication_context:
            metadata["publication_context"] = data.publication_context
        if data.source_identity:
            metadata["source_identity"] = data.source_identity
        if data.independence_group:
            metadata["independence_group"] = data.independence_group
        blob = DocumentBlob(
            content=data.content.encode("utf-8"),
            mime_type=data.mime_type,
            source_uri=data.source_uri,
            metadata=metadata,
        )
        result = await svc.ingest(blob)
        return IngestResponse(
            document_id=result.document_id,
            expression_id=result.expression_id,
            spans=result.span_count,
            chunks=result.chunk_count,
            embeddings=result.embedding_count,
            propositions=result.propositions_extracted,
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

    @post("/rollback/{changeset_id:uuid}")
    async def rollback(
        self,
        corpus_id: uuid.UUID,
        changeset_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> RepairApplyResponse:
        from mapu.repair.service import RepairService

        await _require_corpus(db_session, corpus_id)
        svc = RepairService(db_session, corpus_id)
        result = await svc.rollback(changeset_id)
        return RepairApplyResponse(
            changeset_id=result.changeset_id,
            success=result.success,
            operations_executed=result.operations_executed,
            recomputed_propositions=result.recomputed_propositions,
            gaps_created=result.gaps_created,
            errors=result.errors,
        )


class ContributionController(Controller):
    path = "/corpora/{corpus_id:uuid}/contributions"

    @post()
    async def contribute_proposition(
        self,
        corpus_id: uuid.UUID,
        data: ContributePropositionRequest,
        db_session: AsyncSession,
    ) -> ContributePropositionResponse:
        from datetime import UTC, datetime

        from mapu.extraction.grounding import _compute_semantic_key
        from mapu.models.attestation import Attestation
        from mapu.models.entity import Handle
        from mapu.models.proposition import Proposition, PropositionParticipant
        from mapu.repos.entity import HandleRepo

        await _require_corpus(db_session, corpus_id)

        subject_name = data.subject_name.strip()
        predicate = data.predicate.strip().lower()
        object_name = data.object_name.strip() if data.object_name else None

        if not subject_name or not predicate:
            from litestar.exceptions import ValidationException

            raise ValidationException("subject_name and predicate must not be empty")

        handle_repo = HandleRepo(db_session, corpus_id)
        subject = await handle_repo.get_by_name_kind(subject_name, data.subject_kind)
        if subject is None:
            subject = Handle(
                id=uuid.uuid4(),
                corpus_id=corpus_id,
                canonical_name=subject_name,
                kind=data.subject_kind,
                aliases=[],
                status="active",
                created_at=datetime.now(UTC),
            )
            db_session.add(subject)
            await db_session.flush()

        object_handle: Handle | None = None
        if object_name:
            obj_kind = data.object_kind or "entity"
            object_handle = await handle_repo.get_by_name_kind(object_name, obj_kind)
            if object_handle is None:
                object_handle = Handle(
                    id=uuid.uuid4(),
                    corpus_id=corpus_id,
                    canonical_name=object_name,
                    kind=obj_kind,
                    aliases=[],
                    status="active",
                    created_at=datetime.now(UTC),
                )
                db_session.add(object_handle)
                await db_session.flush()

        semantic_key = _compute_semantic_key(
            frame_type=data.frame_type,
            subject_handle_id=subject.id,
            predicate=predicate,
            object_handle_id=object_handle.id if object_handle else None,
            value=None,
            polarity=True,
            modality=None,
        )

        from mapu.repos.proposition import PropositionRepo

        prop_repo = PropositionRepo(db_session, corpus_id)
        existing = await prop_repo.get_by_semantic_key(semantic_key)
        if existing is not None:
            prop = existing
            prop_created = False
        else:
            prop = Proposition(
                id=uuid.uuid4(),
                corpus_id=corpus_id,
                frame_type=data.frame_type,
                subject_handle_id=subject.id,
                predicate=predicate,
                object_handle_id=object_handle.id if object_handle else None,
                normalized_text=data.normalized_text,
                semantic_key=semantic_key,
                system_created=datetime.now(UTC),
            )
            db_session.add(prop)
            prop_created = True
            await db_session.flush()

        if prop_created:
            db_session.add(PropositionParticipant(
                id=uuid.uuid4(),
                proposition_id=prop.id,
                handle_id=subject.id,
                corpus_id=corpus_id,
                role="subject",
                ordinal=0,
            ))
            if object_handle is not None:
                db_session.add(PropositionParticipant(
                    id=uuid.uuid4(),
                    proposition_id=prop.id,
                    handle_id=object_handle.id,
                    corpus_id=corpus_id,
                    role="object",
                    ordinal=1,
                ))
            await db_session.flush()

        att = Attestation(
            id=uuid.uuid4(),
            proposition_id=prop.id,
            corpus_id=corpus_id,
            stance=data.stance,
            extraction_method=f"{data.actor}_contribution",
            extraction_confidence=data.confidence,
            status="candidate",
            system_created=datetime.now(UTC),
        )
        db_session.add(att)
        await db_session.flush()

        from mapu.models.attestation import AttestationSituation
        from mapu.repos.context import SituationRepo

        sit_repo = SituationRepo(db_session, corpus_id)
        default_sit = await sit_repo.get_or_create_default()
        db_session.add(AttestationSituation(
            attestation_id=att.id,
            situation_id=default_sit.id,
            corpus_id=corpus_id,
            assignment_confidence=1.0,
            assignment_basis="manual_contribution",
        ))
        await db_session.flush()

        return ContributePropositionResponse(
            proposition_id=prop.id,
            attestation_id=att.id,
        )

    @post("/review")
    async def review_attestation(
        self,
        corpus_id: uuid.UUID,
        data: ReviewAttestationRequest,
        db_session: AsyncSession,
    ) -> ReviewAttestationResponse:
        from litestar.exceptions import NotFoundException
        from sqlalchemy import select

        from mapu.models.attestation import Attestation
        from mapu.repos.attestation import AttestationRepo
        from mapu.repos.audit import ActivityRepo

        await _require_corpus(db_session, corpus_id)

        stmt = select(Attestation.id, Attestation.proposition_id).where(
            Attestation.id == data.attestation_id,
            Attestation.corpus_id == corpus_id,
        )
        result = await db_session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            raise NotFoundException(
                detail=f"Attestation {data.attestation_id} not found in corpus {corpus_id}",
            )
        proposition_id = row[1]

        from datetime import UTC, datetime

        from mapu.models.review import Changeset, ChangesetOperation

        now = datetime.now(UTC)
        changeset = Changeset(
            corpus_id=corpus_id,
            actor=data.actor,
            actor_type="reviewer",
            description=f"Review attestation {data.attestation_id}: {data.decision}",
            status="applied",
            risk_level="low",
            reviewed_by=data.actor,
            reviewed_at=now,
            review_reason=data.reason or None,
            applied_at=now,
        )
        db_session.add(changeset)
        await db_session.flush()

        db_session.add(ChangesetOperation(
            changeset_id=changeset.id,
            corpus_id=corpus_id,
            ordinal=0,
            operation_type="attestation_review",
            payload={
                "attestation_id": str(data.attestation_id),
                "decision": data.decision,
                "reason": data.reason,
            },
            executed_at=now,
        ))

        repo = AttestationRepo(db_session, corpus_id)
        if data.decision == "accepted":
            await repo.accept(data.attestation_id)
        elif data.decision == "rejected":
            await repo.reject(data.attestation_id)
        elif data.decision == "quarantined":
            await repo.quarantine(data.attestation_id)

        from mapu.truth.service import TruthComputeService

        truth_svc = TruthComputeService(db_session, corpus_id)
        await truth_svc.recompute_for_proposition(proposition_id)

        activity_repo = ActivityRepo(db_session, corpus_id)
        await activity_repo.log(
            event_type="attestation_review",
            actor=data.actor,
            entity_type="attestation",
            entity_id=data.attestation_id,
            details={
                "decision": data.decision,
                "reason": data.reason,
                "changeset_id": str(changeset.id),
            },
        )

        return ReviewAttestationResponse(
            attestation_id=data.attestation_id,
            new_status=data.decision,
        )


def all_controllers() -> list[type[Controller]]:
    return [
        HealthController,
        CorpusController,
        QueryController,
        DocumentController,
        EntityController,
        RepairController,
        ContributionController,
    ]
