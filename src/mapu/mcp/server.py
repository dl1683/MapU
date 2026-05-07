"""MapU MCP server: exposes knowledge substrate operations as MCP tools."""

from __future__ import annotations

import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

_engine = None
_session_factory = None


def _get_session_factory():
    global _engine, _session_factory
    if _session_factory is None:
        from mapu.config import Settings
        from mapu.db.engine import build_engine

        settings = Settings()
        _engine, _session_factory = build_engine(settings.database)
    return _session_factory


server = FastMCP(
    name="MapU",
    instructions=(
        "MapU is a persistent knowledge substrate for document-heavy reasoning. "
        "Use these tools to query knowledge, ingest documents, manage entities, "
        "and perform repair operations on knowledge graphs."
    ),
)


@server.tool()
async def query(
    corpus_id: str,
    question: str,
    max_results: int = 20,
    situation_id: str | None = None,
) -> dict[str, Any]:
    """Ask a question against a MapU knowledge corpus.

    Returns structured results with proposition hits, synthesis, and gaps.
    """
    from mapu.query.intent import HeuristicIntentClassifier
    from mapu.query.service import QueryService
    from mapu.query.types import QueryRequest

    cid = uuid.UUID(corpus_id)
    sid = uuid.UUID(situation_id) if situation_id else None
    max_results = min(max(max_results, 1), 500)
    factory = _get_session_factory()
    async with factory() as session:
        from mapu.providers.embeddings import get_default_embedding_provider
        from mapu.providers.llms import get_default_llm_provider

        classifier = HeuristicIntentClassifier()
        svc = QueryService(
            session, classifier,
            llm_provider=get_default_llm_provider(),
            embedding_provider=get_default_embedding_provider(),
        )
        request = QueryRequest(
            corpus_id=cid, question=question,
            max_results=max_results, situation_id=sid,
        )
        result = await svc.query(request)
        return {
            "intent": result.intent.value,
            "tier_used": result.tier_used.name,
            "synthesis": result.synthesis,
            "hits": [
                {
                    "proposition_id": str(h.proposition_id),
                    "normalized_text": h.normalized_text,
                    "predicate": h.predicate,
                    "subject_name": h.subject_name,
                    "object_name": h.object_name,
                    "confidence": h.extraction_confidence,
                    "authority_score": h.authority_score,
                }
                for h in result.hits
            ],
            "gaps": list(result.gaps),
            "chunk_hits": [
                {
                    "chunk_id": str(ch.chunk_id),
                    "text": ch.text,
                    "score": ch.score,
                }
                for ch in result.chunk_hits
            ],
            "metadata": result.metadata,
        }


@server.tool()
async def ingest_document(
    corpus_id: str,
    content: str,
    mime_type: str = "text/plain",
    source_uri: str = "",
    document_type: str | None = None,
    publication_context: str | None = None,
    source_identity: str | None = None,
    independence_group: str | None = None,
) -> dict[str, Any]:
    """Ingest a document into a MapU corpus.

    The document is parsed, chunked, and embedded for later querying.
    Optional authority metadata (document_type, publication_context, etc.)
    influences the computed authority score for propositions extracted from
    this document.
    """
    from mapu.evidence.chunking import SpanAwareChunker
    from mapu.evidence.ingest import IngestionService
    from mapu.evidence.parsers import ParserRegistry
    from mapu.evidence.types import DocumentBlob

    content_bytes = content.encode("utf-8")
    if len(content_bytes) > 10_000_000:
        return {"error": "Content exceeds 10MB limit"}

    cid = uuid.UUID(corpus_id)
    factory = _get_session_factory()
    async with factory() as session:
        from mapu.extraction import get_default_extractors
        from mapu.providers.embeddings import get_default_embedding_provider

        registry = ParserRegistry.create_default()
        chunker = SpanAwareChunker()
        svc = IngestionService(
            session, cid, registry, chunker,
            embedding_provider=get_default_embedding_provider(),
            extractors=get_default_extractors(),
        )
        metadata: dict[str, str] = {}
        if document_type:
            metadata["document_type"] = document_type
        if publication_context:
            metadata["publication_context"] = publication_context
        if source_identity:
            metadata["source_identity"] = source_identity
        if independence_group:
            metadata["independence_group"] = independence_group
        blob = DocumentBlob(
            content=content_bytes,
            mime_type=mime_type,
            source_uri=source_uri,
            metadata=metadata,
        )
        result = await svc.ingest(blob)
        await session.commit()
        return {
            "document_id": str(result.document_id),
            "expression_id": str(result.expression_id),
            "spans": result.span_count,
            "chunks": result.chunk_count,
            "embeddings": result.embedding_count,
            "propositions": result.propositions_extracted,
        }


@server.tool()
async def lookup_entity(corpus_id: str, name: str, limit: int = 20) -> dict[str, Any]:
    """Look up an entity handle by name in a corpus.

    Returns matching handles with aliases.
    """
    from sqlalchemy import select

    from mapu.models.entity import Handle
    from mapu.query.direct import _escape_like

    cid = uuid.UUID(corpus_id)
    limit = min(max(limit, 1), 100)
    factory = _get_session_factory()
    async with factory() as session:
        escaped = _escape_like(name)
        stmt = select(Handle).where(
            Handle.corpus_id == cid,
            Handle.status == "active",
            Handle.canonical_name.ilike(f"%{escaped}%"),
        ).limit(limit)
        result = await session.execute(stmt)
        handles = result.scalars().all()
        return {
            "handles": [
                {
                    "id": str(h.id),
                    "canonical_name": h.canonical_name,
                    "kind": h.kind,
                    "aliases": list(h.aliases) if h.aliases else [],
                }
                for h in handles
            ],
        }


@server.tool()
async def repair_preview(
    corpus_id: str,
    proposition_id: str,
    operation: str = "retract",
) -> dict[str, Any]:
    """Preview the blast radius of a repair operation before applying it.

    Shows which propositions would be affected and the risk level.
    """
    from mapu.repair.blast_radius import compute_blast_radius

    cid = uuid.UUID(corpus_id)
    pid = uuid.UUID(proposition_id)
    factory = _get_session_factory()
    async with factory() as session:
        report = await compute_blast_radius(session, cid, pid)
        return report.to_dict()


@server.tool()
async def repair_propose(
    corpus_id: str,
    proposition_id: str,
    reason: str = "",
    actor: str = "agent",
) -> dict[str, Any]:
    """Propose a retraction repair, creating a changeset for later approval.

    Returns the changeset_id needed for repair_apply.
    """
    from mapu.repair.service import RepairService

    cid = uuid.UUID(corpus_id)
    pid = uuid.UUID(proposition_id)
    factory = _get_session_factory()
    async with factory() as session:
        svc = RepairService(session, cid)
        preview = await svc.preview_retraction(
            proposition_id=pid,
            reason=reason,
            actor=actor,
        )
        changeset_id = await svc.propose(preview, description=reason)
        await session.commit()
        return {
            "changeset_id": str(changeset_id),
            "risk_level": preview.risk_level.value,
            "affected_count": len(preview.blast_radius.affected_proposition_ids),
        }


@server.tool()
async def repair_apply(corpus_id: str, changeset_id: str) -> dict[str, Any]:
    """Approve and execute a proposed repair changeset.

    Atomically approves and applies the changeset created by repair_propose.
    """
    from mapu.repair.service import RepairService

    cid = uuid.UUID(corpus_id)
    csid = uuid.UUID(changeset_id)
    factory = _get_session_factory()
    async with factory() as session:
        svc = RepairService(session, cid)
        result = await svc.approve_and_apply(csid)
        await session.commit()
        return {
            "changeset_id": str(result.changeset_id),
            "success": result.success,
            "operations_executed": result.operations_executed,
            "recomputed_propositions": result.recomputed_propositions,
            "gaps_created": result.gaps_created,
            "errors": result.errors,
        }


@server.tool()
async def create_corpus(name: str, description: str = "") -> dict[str, Any]:
    """Create a new knowledge corpus."""
    from mapu.models.corpus import Corpus

    factory = _get_session_factory()
    async with factory() as session:
        corpus = Corpus(name=name, description=description)
        session.add(corpus)
        await session.flush()
        await session.commit()
        return {
            "id": str(corpus.id),
            "name": corpus.name,
        }


@server.tool()
async def list_corpora(limit: int = 100) -> dict[str, Any]:
    """List all available knowledge corpora."""
    from sqlalchemy import select

    from mapu.models.corpus import Corpus

    limit = min(max(limit, 1), 500)
    factory = _get_session_factory()
    async with factory() as session:
        stmt = select(Corpus).order_by(Corpus.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        corpora = result.scalars().all()
        return {
            "corpora": [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "description": c.description,
                }
                for c in corpora
            ],
        }


@server.tool()
async def contribute_proposition(
    corpus_id: str,
    subject_name: str,
    predicate: str,
    normalized_text: str,
    subject_kind: str = "entity",
    object_name: str | None = None,
    object_kind: str | None = None,
    frame_type: str = "finding",
    confidence: float = 1.0,
    stance: str = "asserts",
    actor: str = "agent",
) -> dict[str, Any]:
    """Contribute a proposition to a corpus.

    Creates or reuses entity handles, creates a proposition (deduplicated
    by semantic key), and attaches a candidate attestation.
    """
    from datetime import UTC, datetime

    from mapu.extraction.grounding import _compute_semantic_key
    from mapu.models.attestation import Attestation
    from mapu.models.entity import Handle
    from mapu.models.proposition import Proposition, PropositionParticipant
    from mapu.repos.entity import HandleRepo

    cid = uuid.UUID(corpus_id)
    factory = _get_session_factory()
    async with factory() as session:
        handle_repo = HandleRepo(session, cid)
        subject = await handle_repo.get_by_name_kind(subject_name, subject_kind)
        if subject is None:
            subject = Handle(
                id=uuid.uuid4(), corpus_id=cid,
                canonical_name=subject_name, kind=subject_kind,
                aliases=[], status="active", created_at=datetime.now(UTC),
            )
            session.add(subject)
            await session.flush()

        obj_handle: Handle | None = None
        if object_name:
            ok = object_kind or "entity"
            obj_handle = await handle_repo.get_by_name_kind(object_name, ok)
            if obj_handle is None:
                obj_handle = Handle(
                    id=uuid.uuid4(), corpus_id=cid,
                    canonical_name=object_name, kind=ok,
                    aliases=[], status="active", created_at=datetime.now(UTC),
                )
                session.add(obj_handle)
                await session.flush()

        semantic_key = _compute_semantic_key(
            frame_type=frame_type,
            subject_handle_id=subject.id,
            predicate=predicate,
            object_handle_id=obj_handle.id if obj_handle else None,
            value=None, polarity=True, modality=None,
        )

        from mapu.repos.proposition import PropositionRepo

        prop_repo = PropositionRepo(session, cid)
        existing = await prop_repo.get_by_semantic_key(semantic_key)
        if existing is not None:
            prop = existing
            prop_created = False
        else:
            prop = Proposition(
                id=uuid.uuid4(), corpus_id=cid,
                frame_type=frame_type, subject_handle_id=subject.id,
                predicate=predicate,
                object_handle_id=obj_handle.id if obj_handle else None,
                normalized_text=normalized_text, semantic_key=semantic_key,
                system_created=datetime.now(UTC),
            )
            session.add(prop)
            prop_created = True
            await session.flush()

        if prop_created:
            session.add(PropositionParticipant(
                id=uuid.uuid4(), proposition_id=prop.id,
                handle_id=subject.id, corpus_id=cid, role="subject", ordinal=0,
            ))
            if obj_handle is not None:
                session.add(PropositionParticipant(
                    id=uuid.uuid4(), proposition_id=prop.id,
                    handle_id=obj_handle.id, corpus_id=cid, role="object", ordinal=1,
                ))
            await session.flush()

        att = Attestation(
            id=uuid.uuid4(), proposition_id=prop.id, corpus_id=cid,
            stance=stance, extraction_method=f"{actor}_contribution",
            extraction_confidence=confidence, status="candidate",
            system_created=datetime.now(UTC),
        )
        session.add(att)
        await session.flush()
        await session.commit()
        return {
            "proposition_id": str(prop.id),
            "attestation_id": str(att.id),
        }


@server.tool()
async def review_attestation(
    corpus_id: str,
    attestation_id: str,
    decision: str,
    actor: str = "agent",
    reason: str = "",
) -> dict[str, Any]:
    """Review an attestation: accept, reject, or quarantine it.

    The decision must be one of: accepted, rejected, quarantined.
    """
    from mapu.repos.attestation import AttestationRepo

    if decision not in ("accepted", "rejected", "quarantined"):
        return {"error": f"Invalid decision '{decision}'. Must be accepted/rejected/quarantined."}

    cid = uuid.UUID(corpus_id)
    aid = uuid.UUID(attestation_id)
    factory = _get_session_factory()
    async with factory() as session:
        repo = AttestationRepo(session, cid)
        if decision == "accepted":
            await repo.accept(aid)
        elif decision == "rejected":
            await repo.reject(aid)
        elif decision == "quarantined":
            await repo.quarantine(aid)
        await session.commit()
        return {
            "attestation_id": str(aid),
            "new_status": decision,
        }


def run_mcp() -> None:
    """Entry point for the MCP server."""
    server.run(transport="stdio")
