"""MapU CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid


def main() -> None:
    parser = argparse.ArgumentParser(prog="mapu", description="MapU knowledge substrate")
    sub = parser.add_subparsers(dest="command")

    serve_cmd = sub.add_parser("serve", help="Start the REST API server")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8000)

    sub.add_parser("mcp", help="Start the MCP server (stdio)")

    query_cmd = sub.add_parser("query", help="Query a corpus")
    query_cmd.add_argument("corpus_id", type=str)
    query_cmd.add_argument("question", type=str)

    ingest_cmd = sub.add_parser("ingest", help="Ingest a file into a corpus")
    ingest_cmd.add_argument("corpus_id", type=str)
    ingest_cmd.add_argument("path", type=str)

    args = parser.parse_args()

    if args.command == "serve":
        _run_serve(args.host, args.port)
    elif args.command == "mcp":
        _run_mcp()
    elif args.command == "query":
        asyncio.run(_run_query(args.corpus_id, args.question))
    elif args.command == "ingest":
        asyncio.run(_run_ingest(args.corpus_id, args.path))
    else:
        parser.print_help()
        sys.exit(1)


def _run_serve(host: str, port: int) -> None:
    import uvicorn
    uvicorn.run("mapu.api.app:app", host=host, port=port)


def _run_mcp() -> None:
    from mapu.mcp.server import run_mcp
    run_mcp()


async def _run_query(corpus_id_str: str, question: str) -> None:
    from mapu.config import Settings
    from mapu.db.engine import build_engine
    from mapu.query.intent import HeuristicIntentClassifier
    from mapu.query.service import QueryService
    from mapu.query.types import QueryRequest

    settings = Settings()
    engine, session_factory = build_engine(settings.database)

    cid = uuid.UUID(corpus_id_str)
    async with session_factory() as session:
        classifier = HeuristicIntentClassifier()
        svc = QueryService(session, classifier)
        request = QueryRequest(corpus_id=cid, question=question)
        result = await svc.query(request)

        if result.synthesis:
            print(result.synthesis)
        else:
            for h in result.hits:
                print(f"  [{h.predicate}] {h.subject_name} → {h.object_name or ''}: "
                      f"{h.normalized_text}")

        if result.gaps:
            print("\nGaps:")
            for g in result.gaps:
                print(f"  - {g}")

    await engine.dispose()


async def _run_ingest(corpus_id_str: str, path: str) -> None:
    from pathlib import Path

    from mapu.config import Settings
    from mapu.db.engine import build_engine
    from mapu.evidence.chunking import SpanAwareChunker
    from mapu.evidence.ingest import IngestionService
    from mapu.evidence.parsers import ParserRegistry
    from mapu.evidence.types import DocumentBlob

    settings = Settings()
    engine, session_factory = build_engine(settings.database)

    file_path = Path(path)
    if not file_path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    content = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    mime_map = {
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    mime_type = mime_map.get(suffix, "text/plain")

    cid = uuid.UUID(corpus_id_str)
    async with session_factory() as session:
        registry = ParserRegistry()
        chunker = SpanAwareChunker()
        svc = IngestionService(session, cid, registry, chunker)
        blob = DocumentBlob(content=content, mime_type=mime_type, source_uri=str(file_path))
        result = await svc.ingest(blob)
        await session.commit()

        print(f"Ingested: {path}")
        print(f"  Document ID: {result.document_id}")
        print(f"  Spans: {result.span_count}")
        print(f"  Chunks: {result.chunk_count}")

    await engine.dispose()


if __name__ == "__main__":
    main()
