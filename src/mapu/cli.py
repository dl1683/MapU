"""MapU CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid


def _uuid_arg(value: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"invalid UUID: {value!r}") from err
    return value


def main() -> None:
    parser = argparse.ArgumentParser(prog="mapu", description="MapU knowledge substrate")
    sub = parser.add_subparsers(dest="command")

    serve_cmd = sub.add_parser("serve", help="Start the REST API server")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8000)

    sub.add_parser("mcp", help="Start the MCP server (stdio)")

    query_cmd = sub.add_parser("query", help="Query a corpus")
    query_cmd.add_argument("corpus_id", type=_uuid_arg)
    query_cmd.add_argument("question", type=str)
    query_cmd.add_argument("--max-results", type=int, default=20)
    query_cmd.add_argument("--situation-id", type=_uuid_arg, default=None)
    query_cmd.add_argument("--as-of", type=str, default=None)
    query_cmd.add_argument("--json", action="store_true", dest="json_output")

    ingest_cmd = sub.add_parser("ingest", help="Ingest a file into a corpus")
    ingest_cmd.add_argument("corpus_id", type=_uuid_arg)
    ingest_cmd.add_argument("path", type=str)
    ingest_cmd.add_argument("--document-type", type=str, default=None)
    ingest_cmd.add_argument("--source-uri", type=str, default=None)

    inv_cmd = sub.add_parser("investigate", help="Run a multi-document investigation")
    inv_cmd.add_argument("corpus_id", type=_uuid_arg)
    inv_cmd.add_argument("question", type=str)
    inv_cmd.add_argument("--entity", action="append", default=[], dest="entities")
    inv_cmd.add_argument("--predicate", action="append", default=[], dest="predicates")
    inv_cmd.add_argument("--max-actions", type=int, default=25)
    inv_cmd.add_argument("--json", action="store_true", dest="json_output")

    corpus_cmd = sub.add_parser("corpus", help="Corpus management")
    corpus_sub = corpus_cmd.add_subparsers(dest="corpus_action")
    cc = corpus_sub.add_parser("create", help="Create a new corpus")
    cc.add_argument("name", type=str)
    cc.add_argument("--description", type=str, default="")
    cl = corpus_sub.add_parser("list", help="List corpora")
    cl.add_argument("--json", action="store_true", dest="json_output")
    cd = corpus_sub.add_parser("delete", help="Delete a corpus by id")
    cd.add_argument("corpus_id", type=_uuid_arg)
    cd.add_argument("--yes", action="store_true", help="Confirm destructive delete")
    cr = corpus_sub.add_parser("reset", help="Delete all corpora (start from scratch)")
    cr.add_argument("--yes", action="store_true", help="Confirm destructive reset")

    entity_cmd = sub.add_parser("entities", help="Look up entities")
    entity_cmd.add_argument("corpus_id", type=_uuid_arg)
    entity_cmd.add_argument("name", type=str)
    entity_cmd.add_argument("--limit", type=int, default=20)
    entity_cmd.add_argument("--json", action="store_true", dest="json_output")

    gaps_cmd = sub.add_parser("gaps", help="List knowledge gaps")
    gaps_cmd.add_argument("corpus_id", type=_uuid_arg)
    gaps_cmd.add_argument("--status", type=str, default="open")
    gaps_cmd.add_argument("--json", action="store_true", dest="json_output")

    activity_cmd = sub.add_parser("activity", help="List activity log")
    activity_cmd.add_argument("corpus_id", type=_uuid_arg)
    activity_cmd.add_argument("--limit", type=int, default=50)
    activity_cmd.add_argument("--json", action="store_true", dest="json_output")

    eval_cmd = sub.add_parser("eval", help="Run evaluation benchmarks")
    eval_cmd.add_argument("--domain", type=str, default=None,
                          help="Filter by domain: code, legal, finance, biomedical")
    eval_cmd.add_argument("--output-dir", type=str, default=".benchmarks")
    eval_cmd.add_argument("--json", action="store_true", dest="json_output")

    args = parser.parse_args()

    if args.command == "serve":
        _run_serve(args.host, args.port)
    elif args.command == "mcp":
        _run_mcp()
    elif args.command == "query":
        asyncio.run(_run_query(args))
    elif args.command == "ingest":
        asyncio.run(_run_ingest(args.corpus_id, args.path, args))
    elif args.command == "investigate":
        asyncio.run(_run_investigate(args))
    elif args.command == "corpus":
        if args.corpus_action == "create":
            asyncio.run(_run_corpus_create(args.name, args.description))
        elif args.corpus_action == "list":
            asyncio.run(_run_corpus_list(args))
        elif args.corpus_action == "delete":
            asyncio.run(_run_corpus_delete(args))
        elif args.corpus_action == "reset":
            asyncio.run(_run_corpus_reset(args))
        else:
            parser.parse_args(["corpus", "--help"])
    elif args.command == "entities":
        asyncio.run(_run_entities(args))
    elif args.command == "gaps":
        asyncio.run(_run_gaps(args))
    elif args.command == "activity":
        asyncio.run(_run_activity(args))
    elif args.command == "eval":
        asyncio.run(_run_eval(args))
    else:
        parser.print_help()
        sys.exit(1)


def _run_serve(host: str, port: int) -> None:
    import uvicorn
    uvicorn.run("mapu.api.app:app", host=host, port=port)


def _run_mcp() -> None:
    from mapu.mcp.server import run_mcp
    run_mcp()


def _build_engine():
    from mapu.config import Settings
    from mapu.db.engine import build_engine
    settings = Settings()
    return build_engine(settings.database)


async def _run_query(args: argparse.Namespace) -> None:
    from mapu.query.intent import HeuristicIntentClassifier
    from mapu.query.service import QueryService
    from mapu.query.types import QueryRequest

    engine, session_factory = _build_engine()

    try:
        cid = uuid.UUID(args.corpus_id)
        sid = uuid.UUID(args.situation_id) if args.situation_id else None
        max_results = min(max(args.max_results, 1), 500)
        as_of_dt = None
        if args.as_of:
            from datetime import datetime as dt
            as_of_dt = dt.fromisoformat(args.as_of)

        async with session_factory() as session:
            from mapu.providers.embeddings import get_default_embedding_provider
            from mapu.providers.llms import get_default_llm_provider

            classifier = HeuristicIntentClassifier()
            svc = QueryService(
                session, classifier,
                llm_provider=get_default_llm_provider(),
                embedding_provider=get_default_embedding_provider(),
            )
            request = QueryRequest(
                corpus_id=cid, question=args.question,
                max_results=max_results, situation_id=sid,
                as_of=as_of_dt,
            )
            result = await svc.query(request)

            if args.json_output:
                print(json.dumps({
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
                            "confidence": h.extraction_confidence,
                            "authority_score": h.authority_score,
                            "truth_status": h.truth_status,
                        }
                        for h in result.hits
                    ],
                    "gaps": list(result.gaps),
                    "metadata": result.metadata,
                }, indent=2))
            else:
                if result.synthesis:
                    print(result.synthesis)
                else:
                    for h in result.hits:
                        print(f"  [{h.predicate}] {h.subject_name} -> {h.object_name or ''}: "
                              f"{h.normalized_text}")

                if result.gaps:
                    print("\nGaps:")
                    for g in result.gaps:
                        print(f"  - {g}")
    finally:
        await engine.dispose()


def _read_ingest_file(path: str) -> tuple[bytes, str, str]:
    from pathlib import Path

    file_path = Path(path)
    if not file_path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    size = file_path.stat().st_size
    if size > 10_000_000:
        print(f"File too large ({size} bytes, max 10MB): {path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    mime_map = {
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return content, mime_map.get(suffix, "text/plain"), str(file_path)


async def _run_ingest(
    corpus_id_str: str, path: str, args: argparse.Namespace,
) -> None:
    from mapu.evidence.chunking import SpanAwareChunker
    from mapu.evidence.ingest import IngestionService
    from mapu.evidence.parsers import ParserRegistry
    from mapu.evidence.types import DocumentBlob
    from mapu.providers.embeddings import get_default_embedding_provider

    content, mime_type, source_uri = _read_ingest_file(path)
    if args.source_uri:
        source_uri = args.source_uri

    engine, session_factory = _build_engine()

    try:
        cid = uuid.UUID(corpus_id_str)
        async with session_factory() as session:
            registry = ParserRegistry.create_default()
            chunker = SpanAwareChunker()
            from mapu.config import EmbeddingSettings
            from mapu.extraction import get_default_extractors

            metadata: dict[str, str] = {}
            if args.document_type:
                metadata["document_type"] = args.document_type

            svc = IngestionService(
                session, cid, registry, chunker,
                embedding_provider=get_default_embedding_provider(),
                extractors=get_default_extractors(),
                embedding_batch_size=EmbeddingSettings().batch_size,
            )
            blob = DocumentBlob(
                content=content, mime_type=mime_type,
                source_uri=source_uri, metadata=metadata,
            )
            result = await svc.ingest(blob)
            await session.commit()

            print(f"Ingested: {path}")
            print(f"  Document ID: {result.document_id}")
            print(f"  Spans: {result.span_count}")
            print(f"  Chunks: {result.chunk_count}")
            print(f"  Embeddings: {result.embedding_count}")
            print(f"  Propositions: {result.propositions_extracted}")
    finally:
        await engine.dispose()


async def _run_investigate(args: argparse.Namespace) -> None:
    from mapu.investigation.service import InvestigationService
    from mapu.investigation.types import InvestigationBudget

    engine, session_factory = _build_engine()

    try:
        cid = uuid.UUID(args.corpus_id)
        async with session_factory() as session:
            from mapu.providers.embeddings import get_default_embedding_provider
            from mapu.providers.llms import get_default_llm_provider

            llm = get_default_llm_provider()
            if llm is None:
                print("Error: No LLM provider configured. Set MAPU_LLM_PROVIDER.", file=sys.stderr)
                sys.exit(1)

            budget = InvestigationBudget(
                max_actions=min(max(args.max_actions, 1), 100),
            )
            svc = InvestigationService(
                session, llm, budget=budget,
                embedding_provider=get_default_embedding_provider(),
            )
            result = await svc.investigate(
                question=args.question,
                corpus_id=cid,
                initial_entities=tuple(args.entities),
                initial_predicates=tuple(args.predicates),
            )
            await session.commit()

            if args.json_output:
                print(json.dumps({
                    "answer": result.answer,
                    "evidence_count": len(result.evidence),
                    "gaps": list(result.gaps),
                    "findings_count": len(result.findings),
                    "persisted_ids": [str(p) for p in result.persisted_proposition_ids],
                    "termination_reason": result.termination_reason.value,
                    "metadata": result.metadata,
                }, indent=2))
            else:
                print(result.answer)
                if result.gaps:
                    print("\nGaps:")
                    for g in result.gaps:
                        print(f"  - {g}")
                if result.findings:
                    print(f"\nDerived {len(result.findings)} cross-document findings.")
    finally:
        await engine.dispose()


async def _run_corpus_create(name: str, description: str) -> None:
    from mapu.models.corpus import Corpus

    engine, session_factory = _build_engine()

    try:
        async with session_factory() as session:
            corpus = Corpus(name=name, description=description)
            session.add(corpus)
            await session.flush()
            await session.commit()
            print(f"Created corpus: {corpus.id}")
            print(f"  Name: {corpus.name}")
    finally:
        await engine.dispose()


async def _run_corpus_list(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from mapu.models.corpus import Corpus

    engine, session_factory = _build_engine()

    try:
        async with session_factory() as session:
            stmt = select(Corpus).order_by(Corpus.created_at.desc()).limit(100)
            result = await session.execute(stmt)
            corpora = result.scalars().all()

            if args.json_output:
                print(json.dumps([
                    {"id": str(c.id), "name": c.name, "description": c.description}
                    for c in corpora
                ], indent=2))
            else:
                if not corpora:
                    print("No corpora found.")
                for c in corpora:
                    print(f"  {c.id}  {c.name}")
    finally:
        await engine.dispose()


async def _run_corpus_delete(args: argparse.Namespace) -> None:
    from mapu.models.corpus import Corpus

    if not args.yes:
        print("Refusing delete without --yes flag.", file=sys.stderr)
        sys.exit(2)

    engine, session_factory = _build_engine()
    try:
        cid = uuid.UUID(args.corpus_id)
        async with session_factory() as session:
            corpus = await session.get(Corpus, cid)
            if corpus is None:
                print(f"Corpus not found: {cid}", file=sys.stderr)
                sys.exit(1)
            await session.delete(corpus)
            await session.commit()
            print(f"Deleted corpus: {cid}")
    finally:
        await engine.dispose()


async def _run_corpus_reset(args: argparse.Namespace) -> None:
    from sqlalchemy import delete, select

    from mapu.models.corpus import Corpus

    if not args.yes:
        print("Refusing reset without --yes flag.", file=sys.stderr)
        sys.exit(2)

    engine, session_factory = _build_engine()
    try:
        async with session_factory() as session:
            ids = [row[0] for row in (await session.execute(select(Corpus.id))).all()]
            await session.execute(delete(Corpus))
            await session.commit()
            print(f"Reset complete. Deleted corpora: {len(ids)}")
    finally:
        await engine.dispose()


async def _run_entities(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from mapu.models.entity import Handle
    from mapu.query.direct import _escape_like

    engine, session_factory = _build_engine()

    try:
        cid = uuid.UUID(args.corpus_id)
        limit = min(max(args.limit, 1), 100)
        async with session_factory() as session:
            stmt = select(Handle).where(
                Handle.corpus_id == cid,
                Handle.status == "active",
                Handle.canonical_name.ilike(f"%{_escape_like(args.name)}%"),
            ).limit(limit)
            result = await session.execute(stmt)
            handles = result.scalars().all()

            if args.json_output:
                print(json.dumps([
                    {
                        "id": str(h.id),
                        "canonical_name": h.canonical_name,
                        "kind": h.kind,
                        "aliases": list(h.aliases) if h.aliases else [],
                    }
                    for h in handles
                ], indent=2))
            else:
                if not handles:
                    print(f"No entities matching '{args.name}'.")
                for h in handles:
                    print(f"  [{h.kind}] {h.canonical_name} ({h.id})")
    finally:
        await engine.dispose()


async def _run_gaps(args: argparse.Namespace) -> None:
    from mapu.repos.gap import GapRepo

    engine, session_factory = _build_engine()

    try:
        cid = uuid.UUID(args.corpus_id)
        async with session_factory() as session:
            repo = GapRepo(session, cid)
            gaps = await repo.list(status=args.status if args.status else None)

            if args.json_output:
                print(json.dumps([
                    {
                        "id": str(g.id),
                        "kind": g.kind,
                        "description": g.description,
                        "severity": g.severity,
                        "status": g.status,
                    }
                    for g in gaps
                ], indent=2))
            else:
                if not gaps:
                    print("No gaps found.")
                for g in gaps:
                    print(f"  [{g.severity}] {g.kind}: {g.description}")
    finally:
        await engine.dispose()


async def _run_activity(args: argparse.Namespace) -> None:
    from mapu.repos.audit import ActivityRepo

    engine, session_factory = _build_engine()

    try:
        cid = uuid.UUID(args.corpus_id)
        limit = min(max(args.limit, 1), 500)
        async with session_factory() as session:
            repo = ActivityRepo(session, cid)
            activities = await repo.list(limit=limit)

            if args.json_output:
                print(json.dumps([
                    {
                        "id": str(a.id),
                        "event_type": a.event_type,
                        "actor": a.actor,
                        "entity_type": a.entity_type,
                        "entity_id": str(a.entity_id) if a.entity_id else None,
                        "created_at": a.created_at.isoformat(),
                    }
                    for a in activities
                ], indent=2))
            else:
                if not activities:
                    print("No activity found.")
                for a in activities:
                    print(f"  {a.created_at.isoformat()} [{a.event_type}] {a.actor}")
    finally:
        await engine.dispose()


async def _run_eval(args: argparse.Namespace) -> None:
    from pathlib import Path

    from mapu.evaluation.cases import ALL_BENCHMARK_CASES, get_cases_by_domain
    from mapu.evaluation.reporting import (
        append_jsonl_entry,
        format_summary,
        write_json_scorecard,
    )
    from mapu.evaluation.runner import BenchmarkRunner
    from mapu.evaluation.types import BenchmarkDomain

    if args.domain:
        try:
            domain = BenchmarkDomain(args.domain.lower())
        except ValueError:
            print(f"Unknown domain: {args.domain}", file=sys.stderr)
            print(f"Valid: {', '.join(d.value for d in BenchmarkDomain)}", file=sys.stderr)
            sys.exit(1)
        cases = get_cases_by_domain(domain)
        suite_name = f"eval_{domain.value}"
    else:
        cases = ALL_BENCHMARK_CASES
        suite_name = "eval_all"

    if not cases:
        print("No benchmark cases found.", file=sys.stderr)
        sys.exit(1)

    engine, session_factory = _build_engine()

    try:
        from mapu.extraction import get_default_extractors
        from mapu.providers.embeddings import get_default_embedding_provider

        async with session_factory() as session:
            runner = BenchmarkRunner(
                session=session,
                embedding_provider=get_default_embedding_provider(),
                extractors=get_default_extractors(),
            )
            result = await runner.run_suite(cases, suite_name=suite_name)
            await session.commit()

        output_dir = Path(args.output_dir)
        scorecard_path = write_json_scorecard(result, output_dir)
        append_jsonl_entry(result, output_dir)

        if args.json_output:
            from mapu.evaluation.reporting import suite_to_dict
            print(json.dumps(suite_to_dict(result), indent=2))
        else:
            print(format_summary(result))
            print(f"\nScorecard written to: {scorecard_path}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    main()
