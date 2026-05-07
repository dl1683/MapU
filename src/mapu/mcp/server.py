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
    as_of: str | None = None,
) -> dict[str, Any]:
    """Ask a question against a MapU knowledge corpus.

    Returns structured results with proposition hits, synthesis, and gaps.
    Pass as_of as an ISO 8601 datetime to get truth as of that point in time.
    """
    from mapu.query.intent import HeuristicIntentClassifier
    from mapu.query.service import QueryService
    from mapu.query.types import QueryRequest

    cid = uuid.UUID(corpus_id)
    sid = uuid.UUID(situation_id) if situation_id else None
    max_results = min(max(max_results, 1), 500)
    as_of_dt = None
    if as_of is not None:
        from datetime import datetime as dt

        try:
            as_of_dt = dt.fromisoformat(as_of)
        except ValueError:
            return {"error": "as_of must be a valid ISO 8601 datetime"}
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
            as_of=as_of_dt,
        )
        result = await svc.query(request)
        return {
            "intent": result.intent.value,
            "tier_used": result.tier_used.name,
            "epistemic_status": result.epistemic_status.value,
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
                    "truth_status": h.truth_status,
                    "source_span_text": h.source_span_text,
                    "document_id": str(h.document_id) if h.document_id else None,
                    "valid_from": h.valid_from.isoformat() if h.valid_from else None,
                    "valid_to": h.valid_to.isoformat() if h.valid_to else None,
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

        from mapu.config import EmbeddingSettings

        registry = ParserRegistry.create_default()
        chunker = SpanAwareChunker()
        svc = IngestionService(
            session, cid, registry, chunker,
            embedding_provider=get_default_embedding_provider(),
            extractors=get_default_extractors(),
            embedding_batch_size=EmbeddingSettings().batch_size,
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
async def repair_rollback(corpus_id: str, changeset_id: str) -> dict[str, Any]:
    """Roll back a previously applied repair changeset.

    Reverses the operations in reverse order, restoring the prior state.
    Only works on changesets with status 'applied'.
    """
    from mapu.repair.service import RepairService

    cid = uuid.UUID(corpus_id)
    csid = uuid.UUID(changeset_id)
    factory = _get_session_factory()
    async with factory() as session:
        svc = RepairService(session, cid)
        result = await svc.rollback(csid)
        await session.commit()
        return {
            "changeset_id": str(result.changeset_id),
            "success": result.success,
            "operations_executed": result.operations_executed,
            "recomputed_propositions": result.recomputed_propositions,
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

    _VALID_STANCES = {"asserts", "denies", "reports", "questions", "conditions"}
    if stance not in _VALID_STANCES:
        return {"error": f"Invalid stance '{stance}'. Must be one of: {', '.join(sorted(_VALID_STANCES))}"}
    if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        return {"error": f"confidence must be a number between 0.0 and 1.0, got {confidence}"}
    subject_name = subject_name.strip()
    predicate = predicate.strip().lower()
    if object_name:
        object_name = object_name.strip()
    if not subject_name or not predicate:
        return {"error": "subject_name and predicate must not be empty"}

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
            extraction_confidence=confidence,
            status="candidate",
            system_created=datetime.now(UTC),
        )
        session.add(att)
        await session.flush()

        from mapu.models.attestation import AttestationSituation
        from mapu.repos.context import SituationRepo

        sit_repo = SituationRepo(session, cid)
        default_sit = await sit_repo.get_or_create_default()
        session.add(AttestationSituation(
            attestation_id=att.id,
            situation_id=default_sit.id,
            corpus_id=cid,
            assignment_confidence=1.0,
            assignment_basis="manual_contribution",
        ))
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

    from sqlalchemy import select

    from mapu.models.attestation import Attestation
    from mapu.repos.audit import ActivityRepo

    cid = uuid.UUID(corpus_id)
    aid = uuid.UUID(attestation_id)
    factory = _get_session_factory()
    async with factory() as session:
        stmt = select(Attestation.id, Attestation.proposition_id).where(
            Attestation.id == aid, Attestation.corpus_id == cid,
        )
        result = await session.execute(stmt)
        row = result.one_or_none()
        if row is None:
            return {"error": f"Attestation {attestation_id} not found in corpus {corpus_id}"}
        proposition_id = row[1]

        repo = AttestationRepo(session, cid)
        if decision == "accepted":
            await repo.accept(aid)
        elif decision == "rejected":
            await repo.reject(aid)
        elif decision == "quarantined":
            await repo.quarantine(aid)

        from mapu.truth.service import TruthComputeService

        truth_svc = TruthComputeService(session, cid)
        await truth_svc.recompute_for_proposition(proposition_id)

        activity_repo = ActivityRepo(session, cid)
        await activity_repo.log(
            event_type="attestation_review",
            actor=actor,
            entity_type="attestation",
            entity_id=aid,
            details={"decision": decision, "reason": reason},
        )

        await session.commit()
        return {
            "attestation_id": str(aid),
            "new_status": decision,
        }


@server.tool()
async def investigate(
    corpus_id: str,
    question: str,
    initial_entities: list[str] | None = None,
    initial_predicates: list[str] | None = None,
    situation_id: str | None = None,
    max_llm_calls: int = 10,
    max_actions: int = 25,
    max_documents_read: int = 50,
    target_coverage: float = 0.9,
) -> dict[str, Any]:
    """Run a multi-step investigation that reasons across documents.

    The investigation engine plans retrieval actions, executes them,
    synthesizes findings, and persists derived propositions.
    Requires an LLM provider to be configured.
    """
    from mapu.investigation.service import InvestigationService
    from mapu.investigation.types import InvestigationBudget

    cid = uuid.UUID(corpus_id)
    sid = uuid.UUID(situation_id) if situation_id else None
    max_llm_calls = min(max(max_llm_calls, 1), 50)
    max_actions = min(max(max_actions, 1), 100)
    max_documents_read = min(max(max_documents_read, 1), 200)
    target_coverage = min(max(target_coverage, 0.1), 1.0)

    factory = _get_session_factory()
    async with factory() as session:
        from mapu.providers.embeddings import get_default_embedding_provider
        from mapu.providers.llms import get_default_llm_provider

        llm = get_default_llm_provider()
        if llm is None:
            return {"error": "No LLM provider configured. Set MAPU_LLM_PROVIDER."}

        budget = InvestigationBudget(
            max_llm_calls=max_llm_calls,
            max_actions=max_actions,
            max_documents_read=max_documents_read,
            target_coverage=target_coverage,
        )
        svc = InvestigationService(
            session, llm, budget=budget,
            embedding_provider=get_default_embedding_provider(),
        )
        result = await svc.investigate(
            question=question,
            corpus_id=cid,
            initial_entities=tuple(initial_entities or []),
            initial_predicates=tuple(initial_predicates or []),
            situation_id=sid,
        )
        await session.commit()
        return {
            "answer": result.answer,
            "evidence": [
                {
                    "proposition_id": str(e.proposition_id),
                    "normalized_text": e.normalized_text,
                    "source_span": e.source_span,
                    "authority_score": e.authority_score,
                    "document_id": str(e.document_id) if e.document_id else None,
                    "is_proposition": e.is_proposition,
                }
                for e in result.evidence
            ],
            "gaps": list(result.gaps),
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
            "persisted_proposition_ids": [
                str(pid) for pid in result.persisted_proposition_ids
            ],
            "termination_reason": result.termination_reason.value,
            "metadata": result.metadata,
        }


@server.tool()
async def list_gaps(
    corpus_id: str,
    status: str = "open",
    kind: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List knowledge gaps in a corpus.

    Gaps represent missing documents, missing evidence, or unresolved
    contradictions. Filter by status (open/resolved), kind, or severity.
    """
    from mapu.repos.gap import GapRepo

    cid = uuid.UUID(corpus_id)
    limit = min(max(limit, 1), 500)
    factory = _get_session_factory()
    async with factory() as session:
        repo = GapRepo(session, cid)
        gaps = await repo.list(
            status=status if status else None,
            kind=kind,
            severity=severity,
            limit=limit,
        )
        return {
            "gaps": [
                {
                    "id": str(g.id),
                    "kind": g.kind,
                    "description": g.description,
                    "severity": g.severity,
                    "status": g.status,
                    "detected_by": g.detected_by,
                    "created_at": g.created_at.isoformat(),
                    "resolved_at": g.resolved_at.isoformat() if g.resolved_at else None,
                }
                for g in gaps
            ],
        }


@server.tool()
async def list_activity(
    corpus_id: str,
    limit: int = 50,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> dict[str, Any]:
    """List activity log entries for a corpus.

    The activity log is an immutable audit trail of all operations
    performed on the corpus: ingestion, review, repair, investigation.
    """
    from mapu.repos.audit import ActivityRepo

    cid = uuid.UUID(corpus_id)
    eid = uuid.UUID(entity_id) if entity_id else None
    limit = min(max(limit, 1), 500)
    factory = _get_session_factory()
    async with factory() as session:
        repo = ActivityRepo(session, cid)
        activities = await repo.list(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=eid,
            limit=limit,
        )
        return {
            "activities": [
                {
                    "id": str(a.id),
                    "event_type": a.event_type,
                    "actor": a.actor,
                    "entity_type": a.entity_type,
                    "entity_id": str(a.entity_id) if a.entity_id else None,
                    "details": a.details,
                    "created_at": a.created_at.isoformat(),
                }
                for a in activities
            ],
        }


def run_mcp() -> None:
    """Entry point for the MCP server."""
    server.run(transport="stdio")
