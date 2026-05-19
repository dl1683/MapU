"""MapU MCP server: exposes durable context-memory operations as MCP tools."""

from __future__ import annotations

import contextlib
import importlib
import inspect
import sys
import threading
import uuid
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from mapu.mcp.tool_contract import REQUIRED_MCP_TOOLS

_engine = None
_session_factory = None
_init_lock = threading.Lock()

_MCP_RUNTIME_PRELOAD_MODULES = (
    "mapu.models",
    "mapu.context_learning",
    "mapu.evidence.chunking",
    "mapu.evidence.ingest",
    "mapu.evidence.parsers",
    "mapu.evidence.types",
    "mapu.extraction",
    "mapu.providers.embeddings",
    "mapu.providers.llms",
    "mapu.query.intent",
    "mapu.query.service",
    "mapu.query.types",
    "mapu.repair.service",
    "mapu.repos.audit",
    "mapu.repos.corpus_cleanup",
    "mapu.repos.entity",
    "mapu.repos.gap",
)

def _preload_mcp_runtime_modules() -> None:
    """Load heavy runtime modules before the stdio request loop starts."""
    for module_name in _MCP_RUNTIME_PRELOAD_MODULES:
        importlib.import_module(module_name)


def _redirect_tool_stdout_to_stderr() -> None:
    """Keep third-party tool output off MCP's stdout JSON-RPC channel."""
    for tool in server._tool_manager._tools.values():
        if getattr(tool.fn, "_mapu_stdout_redirected", False):
            continue
        original = tool.fn

        if inspect.iscoroutinefunction(original):

            async def async_wrapped(
                *args: Any,
                __original: Callable[..., Any] = original,
                **kwargs: Any,
            ) -> Any:
                with contextlib.redirect_stdout(sys.stderr):
                    return await __original(*args, **kwargs)

            async_wrapped._mapu_stdout_redirected = True  # type: ignore[attr-defined]
            tool.fn = async_wrapped
        else:

            def wrapped(
                *args: Any,
                __original: Callable[..., Any] = original,
                **kwargs: Any,
            ) -> Any:
                with contextlib.redirect_stdout(sys.stderr):
                    return __original(*args, **kwargs)

            wrapped._mapu_stdout_redirected = True  # type: ignore[attr-defined]
            tool.fn = wrapped


def _parse_uuid(value: str, name: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as err:
        raise _UUIDError(name, value) from err


class _UUIDError(Exception):
    def __init__(self, name: str, value: str) -> None:
        self.error_dict = {"error": f"Invalid {name}: {value!r}. Must be a valid UUID."}
        super().__init__(self.error_dict["error"])


def _get_session_factory():
    global _engine, _session_factory
    if _session_factory is not None:
        return _session_factory
    with _init_lock:
        if _session_factory is None:
            from mapu.config import Settings
            from mapu.db.engine import build_engine

            settings = Settings()
            _engine, _session_factory = build_engine(settings.database)
    return _session_factory


async def _require_corpus(session, corpus_id: uuid.UUID) -> dict[str, Any] | None:
    from mapu.models.corpus import Corpus

    corpus = await session.get(Corpus, corpus_id)
    if corpus is None:
        return {
            "error": f"Corpus {corpus_id} not found",
            "code": "corpus_not_found",
            "corpus_id": str(corpus_id),
        }
    return None


server = FastMCP(
    name="MapU",
    instructions=(
        "MapU is a durable, auditable context-memory substrate for agentic systems. "
        "Use these tools to preserve cross-session knowledge, inspect provenance, "
        "recover gaps/activity after context resets, follow next_steps, and repair "
        "or supersede stale memory explicitly."
    ),
)


def mcp_tool_surface() -> dict[str, Any]:
    """Return the installed MCP tool surface without starting the stdio server."""
    tools = sorted(server._tool_manager._tools)
    missing_required = sorted(set(REQUIRED_MCP_TOOLS).difference(tools))
    return {
        "tool_count": len(tools),
        "required_tool_count": len(REQUIRED_MCP_TOOLS),
        "required_tools_present": not missing_required,
        "missing_required_tools": missing_required,
        "tools": tools,
    }


@server.tool()
async def query(
    corpus_id: str,
    question: str,
    max_results: int = 20,
    situation_id: str | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Ask a question against a MapU knowledge corpus.

    Returns structured results with proposition hits, synthesis, next_steps, and
    gaps.
    Pass as_of as an ISO 8601 datetime to get truth as of that point in time.
    """
    from mapu.query.intent import HeuristicIntentClassifier
    from mapu.query.service import QueryService
    from mapu.query.types import QueryRequest

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        sid = _parse_uuid(situation_id, "situation_id") if situation_id else None
    except _UUIDError as e:
        return e.error_dict
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
        from mapu.repos.gap import GapRepo

        missing = await _require_corpus(session, cid)
        if missing is not None:
            return missing

        classifier = HeuristicIntentClassifier()
        from mapu.repos.audit import ActivityRepo

        svc = QueryService(
            session, classifier,
            activity_repo=ActivityRepo(session, cid),
            gap_repo=GapRepo(session, cid),
            actor="mcp",
            llm_provider=get_default_llm_provider(),
            embedding_provider=get_default_embedding_provider(),
        )
        request = QueryRequest(
            corpus_id=cid, question=question,
            max_results=max_results, situation_id=sid,
            as_of=as_of_dt,
        )
        result = await svc.query(request)
        await session.commit()
        return {
            "intent": result.intent.value,
            "tier_used": result.tier_used.name,
            "epistemic_status": result.epistemic_status.value,
            "answer": result.synthesis,
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
            "next_steps": list(result.next_steps),
            "structured_next_steps": list(result.structured_next_steps),
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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
    except _UUIDError as e:
        return e.error_dict
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > 10_000_000:
        return {"error": "Content exceeds 10MB limit"}
    factory = _get_session_factory()
    async with factory() as session:
        from mapu.config import EmbeddingSettings
        from mapu.extraction import get_default_extractors
        from mapu.providers.embeddings import get_default_embedding_provider

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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
    except _UUIDError as e:
        return e.error_dict
    limit = min(max(limit, 1), 100)
    factory = _get_session_factory()
    async with factory() as session:
        missing = await _require_corpus(session, cid)
        if missing is not None:
            return missing

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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        pid = _parse_uuid(proposition_id, "proposition_id")
    except _UUIDError as e:
        return e.error_dict
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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        pid = _parse_uuid(proposition_id, "proposition_id")
    except _UUIDError as e:
        return e.error_dict
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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        csid = _parse_uuid(changeset_id, "changeset_id")
    except _UUIDError as e:
        return e.error_dict
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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        csid = _parse_uuid(changeset_id, "changeset_id")
    except _UUIDError as e:
        return e.error_dict
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
        valid = ", ".join(sorted(_VALID_STANCES))
        return {"error": f"Invalid stance '{stance}'. Must be one of: {valid}"}
    if not isinstance(confidence, (int, float)) or confidence < 0.0 or confidence > 1.0:
        return {"error": f"confidence must be a number between 0.0 and 1.0, got {confidence}"}
    subject_name = subject_name.strip()
    predicate = predicate.strip().lower()
    if object_name:
        object_name = object_name.strip()
    if not subject_name or not predicate:
        return {"error": "subject_name and predicate must not be empty"}

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
    except _UUIDError as e:
        return e.error_dict
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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        aid = _parse_uuid(attestation_id, "attestation_id")
    except _UUIDError as e:
        return e.error_dict
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
    synthesizes findings, emits next-step guidance, and persists derived
    propositions. Requires an LLM provider to be configured.
    """
    from mapu.investigation.service import InvestigationService
    from mapu.investigation.types import InvestigationBudget

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        sid = _parse_uuid(situation_id, "situation_id") if situation_id else None
    except _UUIDError as e:
        return e.error_dict
    max_llm_calls = min(max(max_llm_calls, 1), 50)
    max_actions = min(max(max_actions, 1), 100)
    max_documents_read = min(max(max_documents_read, 1), 200)
    target_coverage = min(max(target_coverage, 0.1), 1.0)

    factory = _get_session_factory()
    async with factory() as session:
        from mapu.providers.embeddings import get_default_embedding_provider
        from mapu.providers.llms import get_default_llm_provider
        from mapu.repos.audit import ActivityRepo
        from mapu.repos.gap import GapRepo

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
            session,
            llm,
            budget=budget,
            activity_repo=ActivityRepo(session, cid),
            gap_repo=GapRepo(session, cid),
            actor="mcp",
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
            "next_steps": list(result.next_steps),
            "structured_next_steps": list(result.structured_next_steps),
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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
    except _UUIDError as e:
        return e.error_dict
    limit = min(max(limit, 1), 500)
    factory = _get_session_factory()
    async with factory() as session:
        missing = await _require_corpus(session, cid)
        if missing is not None:
            return missing

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
                    "uncertainty_reason": getattr(g, "uncertainty_reason", "missing_evidence"),
                    "evidence_hypothesis": getattr(g, "evidence_hypothesis", {}) or {},
                    "next_action": getattr(g, "next_action", {}) or {},
                    "expected_resolution": getattr(g, "expected_resolution", None),
                    "governance_tier": getattr(g, "governance_tier", "provisional"),
                    "priority_score": getattr(g, "priority_score", None),
                    "resolution_summary": getattr(g, "resolution_summary", None),
                    "last_evaluated_at": (
                        g.last_evaluated_at.isoformat()
                        if getattr(g, "last_evaluated_at", None)
                        else None
                    ),
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

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        eid = _parse_uuid(entity_id, "entity_id") if entity_id else None
    except _UUIDError as e:
        return e.error_dict
    limit = min(max(limit, 1), 500)
    factory = _get_session_factory()
    async with factory() as session:
        missing = await _require_corpus(session, cid)
        if missing is not None:
            return missing

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


@server.tool()
async def handoff_context(
    corpus_id: str,
    max_gaps: int = 10,
    max_activity: int = 20,
    max_actions: int = 10,
) -> dict[str, Any]:
    """Produce a Claude-ready context handoff bundle for resumed sessions."""
    from mapu.context_learning import build_handoff_bundle
    from mapu.repos.audit import ActivityRepo
    from mapu.repos.gap import GapRepo

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
    except _UUIDError as e:
        return e.error_dict
    max_gaps = min(max(max_gaps, 1), 50)
    max_activity = min(max(max_activity, 1), 200)
    max_actions = min(max(max_actions, 1), 30)

    factory = _get_session_factory()
    async with factory() as session:
        missing = await _require_corpus(session, cid)
        if missing is not None:
            return missing

        gap_repo = GapRepo(session, cid)
        activity_repo = ActivityRepo(session, cid)
        gaps = await gap_repo.list(status="open", limit=max_gaps)
        activities = await activity_repo.list(limit=max_activity)

        return build_handoff_bundle(
            corpus_id=cid,
            gaps=tuple(gaps),
            activities=activities,
            max_gaps=max_gaps,
            max_activity=max_activity,
            max_actions=max_actions,
        )


@server.tool()
async def log_learning_feedback(
    corpus_id: str,
    question: str,
    step: str,
    outcome: str,
    actor: str = "agent",
    source_event_type: str = "query",
    source_event_id: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Record learning feedback for a suggested next step.

    The feedback is used to re-rank future next-step suggestions for similar
    questions.
    """
    from mapu.repos.audit import ActivityRepo

    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
        sid = _parse_uuid(source_event_id, "source_event_id") if source_event_id else None
    except _UUIDError as e:
        return e.error_dict

    valid = {"helpful", "partially_helpful", "applied", "not_helpful", "stale", "unknown"}
    if outcome not in valid:
        return {"error": f"Invalid outcome '{outcome}'. Valid values: {', '.join(sorted(valid))}"}

    if not question.strip() or not step.strip():
        return {"error": "question and step must be non-empty"}

    factory = _get_session_factory()
    async with factory() as session:
        repo = ActivityRepo(session, cid)
        entry = await repo.log(
            event_type="learning_feedback",
            actor=actor,
            entity_type="learning_feedback",
            entity_id=sid,
            details={
                "question": question,
                "step": step,
                "outcome": outcome,
                "source_event_type": source_event_type,
                "source_event_id": str(sid) if sid else None,
                "notes": notes,
            },
        )
        await session.commit()
        return {"event_id": str(entry.id), "success": True}


def run_mcp() -> None:
    """Entry point for the MCP server."""
    # Several MCP tools import SQLAlchemy/pgvector/query modules on first use.
    # On Windows/Python 3.13, doing that lazily inside FastMCP's AnyIO request
    # loop can stall stdio tool calls. Startup preloading makes request latency
    # reflect MapU work instead of module import side effects.
    _preload_mcp_runtime_modules()
    # stdout is the MCP protocol stream; model/progress/log output belongs on stderr.
    _redirect_tool_stdout_to_stderr()
    server.run(transport="stdio")


@server.tool()
async def delete_corpus(corpus_id: str, confirm: bool = False) -> dict[str, Any]:
    """Delete one corpus and all related data.

    Set confirm=true to execute.
    """
    from mapu.models.corpus import Corpus
    from mapu.repos.corpus_cleanup import delete_corpus_rows

    if not confirm:
        return {"error": "Refusing delete without confirm=true"}
    try:
        cid = _parse_uuid(corpus_id, "corpus_id")
    except _UUIDError as e:
        return e.error_dict
    factory = _get_session_factory()
    async with factory() as session:
        corpus = await session.get(Corpus, cid)
        if corpus is None:
            return {"error": f"Corpus {corpus_id} not found"}
        await delete_corpus_rows(session, cid)
        await session.commit()
        return {"deleted_corpus_id": str(cid)}


@server.tool()
async def reset_all_corpora(confirm: bool = False) -> dict[str, Any]:
    """Delete all corpora and all related data.

    Set confirm=true to execute.
    """
    from sqlalchemy import select

    from mapu.models.corpus import Corpus
    from mapu.repos.corpus_cleanup import delete_corpus_rows

    if not confirm:
        return {"error": "Refusing reset without confirm=true"}
    factory = _get_session_factory()
    async with factory() as session:
        corpus_ids = [row[0] for row in (await session.execute(select(Corpus.id))).all()]
        for cid in corpus_ids:
            await delete_corpus_rows(session, cid)
        await session.commit()
        ids = [str(cid) for cid in corpus_ids]
        return {"deleted_count": len(ids), "deleted_corpus_ids": ids}
