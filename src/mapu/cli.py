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
    parser = argparse.ArgumentParser(
        prog="mapu",
        description="MapU durable context-memory substrate for agentic systems",
    )
    sub = parser.add_subparsers(dest="command")

    serve_cmd = sub.add_parser("serve", help="Start the REST API server")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8000)

    sub.add_parser("mcp", help="Start the MCP server (stdio)")

    doctor_cmd = sub.add_parser(
        "doctor",
        help="Inspect installed MapU CLI/MCP health without a database connection",
    )
    doctor_cmd.add_argument("--json", action="store_true", dest="json_output")

    query_cmd = sub.add_parser(
        "query",
        help="Query a corpus and return next-step guidance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  mapu query <corpus_uuid> "What changed in the contract?"\n'
            '  mapu query <corpus_uuid> "What should the agent do next?" --json\n'
            "\n"
            "Use --json for automation. Text output is intended for humans and may change."
        ),
    )
    query_cmd.add_argument("corpus_id", type=_uuid_arg, help="Corpus UUID to search.")
    query_cmd.add_argument("question", type=str, help="Question or task to answer from memory.")
    query_cmd.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum retrieved memory records to consider.",
    )
    query_cmd.add_argument(
        "--situation-id",
        type=_uuid_arg,
        default=None,
        help="Optional situation UUID for time-scoped continuity queries.",
    )
    query_cmd.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Optional ISO timestamp for historical/as-of querying.",
    )
    query_cmd.add_argument("--json", action="store_true", dest="json_output")

    ingest_cmd = sub.add_parser(
        "ingest",
        help="Persist source evidence into a corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mapu ingest <corpus_uuid> ./handoff.md\n"
            "  mapu ingest <corpus_uuid> ./notes.md --document-type markdown "
            "\\\n"
            "    --source-uri repo://notes.md\n"
            "\n"
            "Ingest stores source-backed memory. Query or resume the same corpus after ingest."
        ),
    )
    ingest_cmd.add_argument("corpus_id", type=_uuid_arg, help="Corpus UUID to update.")
    ingest_cmd.add_argument("path", type=str, help="Local source file to ingest.")
    ingest_cmd.add_argument(
        "--document-type",
        type=str,
        default=None,
        help="Optional document type label, such as markdown, pdf, code, or transcript.",
    )
    ingest_cmd.add_argument(
        "--source-uri",
        type=str,
        default=None,
        help="Stable provenance URI to store instead of the local file path.",
    )

    inv_cmd = sub.add_parser("investigate", help="Run a multi-document investigation")
    inv_cmd.add_argument("corpus_id", type=_uuid_arg)
    inv_cmd.add_argument("question", type=str)
    inv_cmd.add_argument("--entity", action="append", default=[], dest="entities")
    inv_cmd.add_argument("--predicate", action="append", default=[], dest="predicates")
    inv_cmd.add_argument("--max-actions", type=int, default=25)
    inv_cmd.add_argument("--json", action="store_true", dest="json_output")

    corpus_cmd = sub.add_parser("corpus", help="Long-lived memory corpus management")
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
    gaps_cmd.add_argument("--kind", type=str, default=None)
    gaps_cmd.add_argument("--severity", type=str, default=None)
    gaps_cmd.add_argument("--limit", type=int, default=100)
    gaps_cmd.add_argument("--json", action="store_true", dest="json_output")

    resume_cmd = sub.add_parser(
        "resume",
        help="Generate a Claude-style continuity handoff bundle for a corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mapu resume <corpus_uuid>\n"
            "  mapu resume <corpus_uuid> --max-gaps 10 --max-activity 20 --json\n"
            "\n"
            "Start resumed agent sessions here: inspect open_gaps, recent_activity,\n"
            "and priority_next_actions before querying further."
        ),
    )
    resume_cmd.add_argument("corpus_id", type=_uuid_arg, help="Corpus UUID to summarize.")
    resume_cmd.add_argument("--max-gaps", type=int, default=10, help="Maximum open gaps to show.")
    resume_cmd.add_argument(
        "--max-activity",
        type=int,
        default=20,
        help="Maximum recent activity records to show.",
    )
    resume_cmd.add_argument(
        "--max-actions",
        type=int,
        default=10,
        help="Maximum priority next actions to show.",
    )
    resume_cmd.add_argument("--json", action="store_true", dest="json_output")

    activity_cmd = sub.add_parser(
        "activity",
        help="List auditable memory activity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mapu activity <corpus_uuid> --limit 20\n"
            "  mapu activity <corpus_uuid> --event-type query --json\n"
            "\n"
            "Activity output is the audit trail for what memory changed, what was read,\n"
            "and which entity or situation each event touched."
        ),
    )
    activity_cmd.add_argument("corpus_id", type=_uuid_arg, help="Corpus UUID to inspect.")
    activity_cmd.add_argument("--limit", type=int, default=50, help="Maximum events to list.")
    activity_cmd.add_argument("--event-type", type=str, default=None, help="Optional event filter.")
    activity_cmd.add_argument(
        "--entity-type",
        type=str,
        default=None,
        help="Optional entity type filter.",
    )
    activity_cmd.add_argument(
        "--entity-id",
        type=_uuid_arg,
        default=None,
        help="Optional entity UUID filter.",
    )
    activity_cmd.add_argument("--json", action="store_true", dest="json_output")

    eval_cmd = sub.add_parser(
        "eval",
        help="Run evaluation benchmarks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mapu eval memory-benchmark-smoke --no-export --out-dir .tmp/benchmark-live-smoke\n"
            "  mapu eval benchmark-score-gate "
            "--score memoryarena=results/score.json:token_f1:0.65\n"
            "\n"
            "Memory benchmark smoke commands are smoke-only health checks. They are not\n"
            "public leaderboard or product-performance evidence unless separately gated."
        ),
    )
    eval_cmd.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Filter by domain: code, legal, finance, biomedical",
    )
    eval_cmd.add_argument("--output-dir", type=str, default=".benchmarks")
    eval_cmd.add_argument("--json", action="store_true", dest="json_output")
    eval_sub = eval_cmd.add_subparsers(dest="eval_action")

    memoryarena_cmd = eval_sub.add_parser(
        "memoryarena",
        help="Export or score MemoryArena scenarios",
    )
    memoryarena_sub = memoryarena_cmd.add_subparsers(dest="memoryarena_action", required=True)
    memoryarena_sub.add_parser("catalog", help="Print MemoryArena config sizes and columns.")
    memoryarena_export = memoryarena_sub.add_parser(
        "export",
        help="Export MemoryArena scenarios as JSONL.",
    )
    memoryarena_export.add_argument(
        "--out",
        default="data/benchmarks/memoryarena/scenarios.jsonl",
        help="Output JSONL path.",
    )
    memoryarena_export.add_argument(
        "--limit-per-config",
        type=int,
        default=0,
        help="Optional max scenarios per config. 0 means no limit.",
    )
    memoryarena_predict = memoryarena_sub.add_parser(
        "predict",
        help="Generate local MapU baseline predictions for MemoryArena scenarios.",
    )
    memoryarena_predict.add_argument("--scenarios", required=True)
    memoryarena_predict.add_argument("--out", default="results/memoryarena_predictions.jsonl")
    memoryarena_predict.add_argument(
        "--max-scenarios",
        type=int,
        default=0,
        help="Optional max scenarios to predict. 0 means all scenarios.",
    )
    memoryarena_predict.add_argument(
        "--predictor",
        choices=("benchmark_agnostic", "web_grounded", "diagnostic_templates"),
        default="benchmark_agnostic",
        help=(
            "Prediction mode. benchmark_agnostic uses only exported scenario inputs; "
            "web_grounded can use live web search for source-free questions; "
            "diagnostic_templates is for scorer smoke tests only."
        ),
    )
    memoryarena_score = memoryarena_sub.add_parser(
        "score",
        help="Score prediction JSONL against exported MemoryArena scenarios.",
    )
    memoryarena_score.add_argument("--scenarios", required=True)
    memoryarena_score.add_argument("--predictions", required=True)
    memoryarena_score.add_argument("--out", default="results/memoryarena_score.json")
    memoryarena_score.add_argument("--min-exact-match", type=float, default=None)

    ama_cmd = eval_sub.add_parser(
        "ama-bench",
        help="Export or score AMA-Bench scenarios",
    )
    ama_sub = ama_cmd.add_subparsers(dest="ama_bench_action", required=True)
    ama_sub.add_parser("catalog", help="Print AMA-Bench dataset size and columns.")
    ama_export = ama_sub.add_parser(
        "export",
        help="Export AMA-Bench scenarios as JSONL.",
    )
    ama_export.add_argument(
        "--out",
        default="data/benchmarks/ama_bench/scenarios.sample.jsonl",
        help="Output JSONL path.",
    )
    ama_export.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max scenarios to export. 0 means full dataset.",
    )
    ama_predict = ama_sub.add_parser(
        "predict",
        help="Generate local MapU baseline predictions for AMA-Bench scenarios.",
    )
    ama_predict.add_argument("--scenarios", required=True)
    ama_predict.add_argument("--out", default="results/ama_bench_predictions.jsonl")
    ama_predict.add_argument(
        "--max-scenarios",
        type=int,
        default=0,
        help="Optional max scenarios to predict. 0 means all scenarios.",
    )
    ama_predict.add_argument(
        "--predictor",
        choices=("benchmark_agnostic", "diagnostic_templates"),
        default="benchmark_agnostic",
        help=(
            "Prediction mode. benchmark_agnostic uses generic trajectory retrieval; "
            "diagnostic_templates is for scorer smoke tests only."
        ),
    )
    ama_score = ama_sub.add_parser(
        "score",
        help="Score prediction JSONL against exported AMA-Bench scenarios.",
    )
    ama_score.add_argument("--scenarios", required=True)
    ama_score.add_argument("--predictions", required=True)
    ama_score.add_argument("--out", default="results/ama_bench_score.json")
    ama_score.add_argument("--min-exact-match", type=float, default=None)

    score_gate_cmd = eval_sub.add_parser(
        "benchmark-score-gate",
        help="Validate memory benchmark score artifacts against thresholds",
    )
    score_gate_cmd.add_argument(
        "--score",
        action="append",
        required=True,
        metavar="BENCHMARK=PATH[:METRIC]:MIN_SCORE",
        help=(
            "Score artifact, optional metric, and threshold. Examples: "
            "memoryarena=results/memoryarena_score.json:0.80 or "
            "ama_bench=results/ama_score.json:token_f1:0.65"
        ),
    )
    score_gate_cmd.add_argument(
        "--out",
        default="results/memory_benchmark_score_gate.json",
        help="Output gate report JSON path.",
    )
    score_gate_cmd.add_argument(
        "--require-clean-git",
        action="store_true",
        help="Fail when the git worktree is dirty.",
    )
    score_gate_cmd.add_argument(
        "--allow-non-release-methods",
        action="store_true",
        help=(
            "Allow score artifacts produced by diagnostic/non-release predictors. "
            "Do not use this for release or public-claim gates."
        ),
    )
    score_gate_cmd.add_argument(
        "--allow-diagnostic-methods",
        action="store_true",
        help=(
            "Compatibility alias for --allow-non-release-methods."
        ),
    )

    score_inspect_cmd = eval_sub.add_parser(
        "benchmark-score-inspect",
        help="Print the worst item-level misses from a benchmark score report.",
    )
    score_inspect_cmd.add_argument("score", help="Benchmark score report JSON path.")
    score_inspect_cmd.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of worst items to print.",
    )

    smoke_cmd = eval_sub.add_parser(
        "memory-benchmark-smoke",
        help="Run MemoryArena and AMA-Bench export/predict/score/gate as one smoke workflow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  mapu eval memory-benchmark-smoke --out-dir .tmp/benchmark-live-smoke\n"
            "  mapu eval memory-benchmark-smoke --no-export --out-dir .tmp/benchmark-live-smoke\n"
            "  mapu eval memory-benchmark-smoke --predictor web_grounded "
            "--allow-non-release-methods --min-token-f1 0.0\n"
            "\n"
            "This command writes smoke_report.json with smoke_only=true and\n"
            "public_performance_evidence=false. Use diagnostic_templates only with\n"
            "--allow-non-release-methods for scorer/debug inspection. Use web_grounded\n"
            "with the same flag for external-evidence infrastructure debugging."
        ),
    )
    smoke_cmd.add_argument(
        "--out-dir",
        default=".tmp/benchmark-live-smoke",
        help="Directory for scenarios, predictions, scores, gate, and smoke report.",
    )
    smoke_cmd.add_argument(
        "--no-export",
        action="store_true",
        help="Use existing scenario files instead of downloading/exporting datasets.",
    )
    smoke_cmd.add_argument(
        "--memoryarena-scenarios",
        default=None,
        help="Existing MemoryArena scenarios JSONL to reuse with --no-export.",
    )
    smoke_cmd.add_argument(
        "--ama-scenarios",
        default=None,
        help="Existing AMA-Bench scenarios JSONL to reuse with --no-export.",
    )
    smoke_cmd.add_argument(
        "--memoryarena-limit-per-config",
        type=int,
        default=1,
        help="Rows to export per MemoryArena config when export is enabled.",
    )
    smoke_cmd.add_argument(
        "--ama-limit",
        type=int,
        default=1,
        help="Rows to export from AMA-Bench when export is enabled.",
    )
    smoke_cmd.add_argument(
        "--predictor",
        choices=("benchmark_agnostic", "web_grounded", "diagnostic_templates"),
        default="benchmark_agnostic",
        help=(
            "Prediction mode. benchmark_agnostic is default; web_grounded uses "
            "live web snippets for MemoryArena source-free prompts; "
            "diagnostic_templates is debug-only."
        ),
    )
    smoke_cmd.add_argument(
        "--min-token-f1",
        type=float,
        default=0.45,
        help="Minimum token_f1 threshold applied to both score reports by the aggregate gate.",
    )
    smoke_cmd.add_argument(
        "--allow-non-release-methods",
        action="store_true",
        help="Allow diagnostic/non-release methods in the aggregate gate. Debug only.",
    )
    smoke_cmd.add_argument(
        "--allow-diagnostic-methods",
        action="store_true",
        help="Compatibility alias for --allow-non-release-methods.",
    )
    smoke_cmd.add_argument(
        "--verbose-steps",
        action="store_true",
        help="Print inner export/predict/score command output instead of only the final summary.",
    )

    args = parser.parse_args()

    if args.command == "serve":
        _run_serve(args.host, args.port)
    elif args.command == "mcp":
        _run_mcp()
    elif args.command == "doctor":
        _run_doctor(args)
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
    elif args.command == "resume":
        asyncio.run(_run_resume(args))
    elif args.command == "activity":
        asyncio.run(_run_activity(args))
    elif args.command == "eval":
        if args.eval_action == "memoryarena":
            _run_memoryarena_eval(args)
        elif args.eval_action == "ama-bench":
            _run_ama_bench_eval(args)
        elif args.eval_action == "benchmark-score-gate":
            _run_benchmark_score_gate(args)
        elif args.eval_action == "benchmark-score-inspect":
            _run_benchmark_score_inspect(args)
        elif args.eval_action == "memory-benchmark-smoke":
            _run_memory_benchmark_smoke(args)
        else:
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


def _run_doctor(args: argparse.Namespace) -> None:
    from mapu import __version__
    from mapu.mcp.server import mcp_tool_surface

    mcp_surface = mcp_tool_surface()
    ok = mcp_surface["required_tools_present"]
    report = {
        "status": "ok" if ok else "fail",
        "mapu_version": __version__,
        "mcp": mcp_surface,
        "claim_boundary": (
            "doctor checks installed CLI/MCP surface only; it is not DB workflow, "
            "release, or benchmark performance evidence"
        ),
    }
    if args.json_output:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        print(f"MapU doctor: {report['status']}")
        print(f"version: {__version__}")
        present_count = (
            mcp_surface["required_tool_count"] - len(mcp_surface["missing_required_tools"])
        )
        required_count = mcp_surface["required_tool_count"]
        tool_count = mcp_surface["tool_count"]
        print(
            f"mcp tools: {present_count}/{required_count} required present "
            f"({tool_count} total)"
        )
        if mcp_surface["missing_required_tools"]:
            print("missing required MCP tools:")
            for tool in mcp_surface["missing_required_tools"]:
                print(f"- {tool}")
        print(report["claim_boundary"])
    if not ok:
        sys.exit(1)


def _build_engine():
    from mapu.config import Settings
    from mapu.db.engine import build_engine

    settings = Settings()
    return build_engine(settings.database)


async def _require_corpus_exists(session, corpus_id: uuid.UUID) -> None:
    from mapu.models.corpus import Corpus

    corpus = await session.get(Corpus, corpus_id)
    if corpus is None:
        print(f"Corpus not found: {corpus_id}", file=sys.stderr)
        sys.exit(1)


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
            from mapu.repos.audit import ActivityRepo
            from mapu.repos.gap import GapRepo

            await _require_corpus_exists(session, cid)
            classifier = HeuristicIntentClassifier()
            svc = QueryService(
                session,
                classifier,
                activity_repo=ActivityRepo(session, cid),
                gap_repo=GapRepo(session, cid),
                actor="cli",
                llm_provider=get_default_llm_provider(),
                embedding_provider=get_default_embedding_provider(),
            )
            request = QueryRequest(
                corpus_id=cid,
                question=args.question,
                max_results=max_results,
                situation_id=sid,
                as_of=as_of_dt,
            )
            result = await svc.query(request)
            await session.commit()
            structured_next_steps = tuple(getattr(result, "structured_next_steps", ()) or ())

            if args.json_output:
                print(
                    json.dumps(
                        {
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
                                    "confidence": h.extraction_confidence,
                                    "authority_score": h.authority_score,
                                    "truth_status": h.truth_status,
                                }
                                for h in result.hits
                            ],
                            "chunk_hits": [
                                {
                                    "chunk_id": str(h.chunk_id),
                                    "text": h.text,
                                    "score": h.score,
                                    "expression_id": str(h.expression_id),
                                }
                                for h in result.chunk_hits
                            ],
                            "gaps": list(result.gaps),
                            "metadata": result.metadata,
                            "next_steps": list(result.next_steps),
                            "structured_next_steps": list(structured_next_steps),
                        },
                        indent=2,
                    )
                )
            else:
                if result.synthesis:
                    print(result.synthesis)
                else:
                    for h in result.hits:
                        print(
                            f"  [{h.predicate}] {h.subject_name} -> {h.object_name or ''}: "
                            f"{h.normalized_text}"
                        )

                if result.gaps:
                    print("\nGaps:")
                    for g in result.gaps:
                        print(f"  - {g}")
                if result.next_steps:
                    print("\nNext steps:")
                    for step in result.next_steps:
                        print(f"  - {step}")
                if structured_next_steps:
                    print("\nExecutable next actions:")
                    for action in structured_next_steps[:3]:
                        print(f"  - [{action.get('action_type')}] {action.get('step')}")
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
    corpus_id_str: str,
    path: str,
    args: argparse.Namespace,
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
            await _require_corpus_exists(session, cid)
            registry = ParserRegistry.create_default()
            chunker = SpanAwareChunker()
            from mapu.config import EmbeddingSettings
            from mapu.extraction import get_default_extractors

            metadata: dict[str, str] = {}
            if args.document_type:
                metadata["document_type"] = args.document_type

            svc = IngestionService(
                session,
                cid,
                registry,
                chunker,
                embedding_provider=get_default_embedding_provider(),
                extractors=get_default_extractors(),
                embedding_batch_size=EmbeddingSettings().batch_size,
            )
            blob = DocumentBlob(
                content=content,
                mime_type=mime_type,
                source_uri=source_uri,
                metadata=metadata,
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
            from mapu.repos.audit import ActivityRepo
            from mapu.repos.gap import GapRepo

            await _require_corpus_exists(session, cid)
            llm = get_default_llm_provider()
            if llm is None:
                print("Error: No LLM provider configured. Set MAPU_LLM_PROVIDER.", file=sys.stderr)
                sys.exit(1)

            budget = InvestigationBudget(
                max_actions=min(max(args.max_actions, 1), 100),
            )
            svc = InvestigationService(
                session,
                llm,
                budget=budget,
                activity_repo=ActivityRepo(session, cid),
                gap_repo=GapRepo(session, cid),
                actor="cli",
                embedding_provider=get_default_embedding_provider(),
            )
            result = await svc.investigate(
                question=args.question,
                corpus_id=cid,
                initial_entities=tuple(args.entities),
                initial_predicates=tuple(args.predicates),
            )
            await session.commit()
            structured_next_steps = tuple(getattr(result, "structured_next_steps", ()) or ())

            if args.json_output:
                print(
                    json.dumps(
                        {
                            "answer": result.answer,
                            "evidence_count": len(result.evidence),
                            "gaps": list(result.gaps),
                            "findings_count": len(result.findings),
                            "persisted_ids": [str(p) for p in result.persisted_proposition_ids],
                            "termination_reason": result.termination_reason.value,
                            "metadata": result.metadata,
                            "next_steps": list(result.next_steps),
                            "structured_next_steps": list(structured_next_steps),
                        },
                        indent=2,
                    )
                )
            else:
                print(result.answer)
                if result.gaps:
                    print("\nGaps:")
                    for g in result.gaps:
                        print(f"  - {g}")
                if result.next_steps:
                    print("\nNext steps:")
                    for step in result.next_steps:
                        print(f"  - {step}")
                if structured_next_steps:
                    print("\nExecutable next actions:")
                    for action in structured_next_steps[:3]:
                        print(f"  - [{action.get('action_type')}] {action.get('step')}")
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
                print(
                    json.dumps(
                        [
                            {"id": str(c.id), "name": c.name, "description": c.description}
                            for c in corpora
                        ],
                        indent=2,
                    )
                )
            else:
                if not corpora:
                    print("No corpora found.")
                for c in corpora:
                    print(f"  {c.id}  {c.name}")
    finally:
        await engine.dispose()


async def _run_corpus_delete(args: argparse.Namespace) -> None:
    from mapu.models.corpus import Corpus
    from mapu.repos.corpus_cleanup import delete_corpus_rows

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
            await delete_corpus_rows(session, cid)
            await session.commit()
            print(f"Deleted corpus: {cid}")
    finally:
        await engine.dispose()


async def _run_corpus_reset(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from mapu.models.corpus import Corpus
    from mapu.repos.corpus_cleanup import delete_corpus_rows

    if not args.yes:
        print("Refusing reset without --yes flag.", file=sys.stderr)
        sys.exit(2)

    engine, session_factory = _build_engine()
    try:
        async with session_factory() as session:
            ids = [row[0] for row in (await session.execute(select(Corpus.id))).all()]
            for cid in ids:
                await delete_corpus_rows(session, cid)
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
            await _require_corpus_exists(session, cid)
            stmt = (
                select(Handle)
                .where(
                    Handle.corpus_id == cid,
                    Handle.status == "active",
                    Handle.canonical_name.ilike(f"%{_escape_like(args.name)}%"),
                )
                .limit(limit)
            )
            result = await session.execute(stmt)
            handles = result.scalars().all()

            if args.json_output:
                print(
                    json.dumps(
                        [
                            {
                                "id": str(h.id),
                                "canonical_name": h.canonical_name,
                                "kind": h.kind,
                                "aliases": list(h.aliases) if h.aliases else [],
                            }
                            for h in handles
                        ],
                        indent=2,
                    )
                )
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
        limit = min(max(getattr(args, "limit", 100), 1), 500)
        async with session_factory() as session:
            await _require_corpus_exists(session, cid)
            repo = GapRepo(session, cid)
            gaps = await repo.list(
                status=args.status if args.status else None,
                kind=getattr(args, "kind", None),
                severity=getattr(args, "severity", None),
                limit=limit,
            )

            if args.json_output:
                print(
                    json.dumps(
                        [
                            {
                                "id": str(g.id),
                                "kind": g.kind,
                                "description": g.description,
                                "severity": g.severity,
                                "status": g.status,
                                "uncertainty_reason": getattr(
                                    g, "uncertainty_reason", "missing_evidence"
                                ),
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
                            }
                            for g in gaps
                        ],
                        indent=2,
                    )
                )
            else:
                if not gaps:
                    print("No gaps found.")
                for g in gaps:
                    tier = getattr(g, "governance_tier", "provisional")
                    reason = getattr(g, "uncertainty_reason", "missing_evidence")
                    print(f"  [{g.severity}/{tier}] {g.kind}: {g.description} ({reason})")
    finally:
        await engine.dispose()


async def _run_resume(args: argparse.Namespace) -> None:
    from mapu.context_learning import build_handoff_bundle
    from mapu.repos.audit import ActivityRepo
    from mapu.repos.gap import GapRepo

    engine, session_factory = _build_engine()
    try:
        cid = uuid.UUID(args.corpus_id)
        max_gaps = min(max(args.max_gaps, 1), 50)
        max_activity = min(max(args.max_activity, 1), 200)
        max_actions = min(max(args.max_actions, 1), 30)

        async with session_factory() as session:
            await _require_corpus_exists(session, cid)
            gap_repo = GapRepo(session, cid)
            activity_repo = ActivityRepo(session, cid)
            gaps = await gap_repo.list(status="open", limit=max_gaps)
            activities = await activity_repo.list(limit=max_activity)
            handoff = build_handoff_bundle(
                corpus_id=cid,
                gaps=tuple(gaps),
                activities=activities,
                max_gaps=max_gaps,
                max_activity=max_activity,
                max_actions=max_actions,
            )

            if args.json_output:
                print(json.dumps(handoff, indent=2))
            else:
                open_gaps = handoff["open_gaps"]
                next_actions = handoff["priority_next_actions"]
                activities = handoff["recent_activity"]
                print(f"Resume handoff for corpus: {cid}")
                print(f"Protocol {handoff['protocol_version']}: {handoff['protocol']}")
                frontier = handoff["continuity_frontier"]
                print(
                    f"Open gaps: {frontier.get('open_gap_count', 0)} "
                    f"Unresolved conflicts: {frontier.get('unresolved_conflict_count', 0)}"
                )
                print(
                    f"Frontier: {frontier.get('frontier_completeness', 'partial')} "
                    f"status={frontier.get('continuity_status', 'attention_required')}"
                )
                print(
                    f"Anchors: {frontier.get('anchor_sufficiency', 'none')} "
                    f"reason={frontier.get('readiness_reason', '')}"
                )
                print("\nOpen high-priority gaps:")
                if not open_gaps:
                    print("  No open gaps. Focus on assumption validation and evidence lineage.")
                else:
                    for gap in open_gaps:
                        print(
                            f"  [{gap.get('severity')}/{gap.get('governance_tier')}] "
                            f"{gap.get('kind')}: {gap.get('description')}",
                        )
                        missing = gap.get("missing_contract_fields") or []
                        if missing:
                            print(f"      missing contract: {', '.join(missing)}")

                print("\nPriority next actions for Claude/code agents:")
                print("  Showing top 3; use --json for the full handoff.")
                for i, action in enumerate(next_actions[:3], start=1):
                    confidence = action.get("confidence")
                    if action.get("gap_ids"):
                        uncertainty = f"gap_ids={','.join(action['gap_ids'])}"
                    else:
                        uncertainty = action.get("uncertainty_reason", "unspecified")
                    print(f"  {i:>2}. [{action['action_type']}] conf={confidence} {uncertainty}")
                    print(f"      {action.get('step')}")
                    if action.get("expected_resolution"):
                        print(f"      resolves: {action.get('expected_resolution')}")

                print("\nRecent memory activity:")
                if not activities:
                    print("  No activity found.")
                else:
                    for activity in activities[:max_activity]:
                        created_at = activity.get("created_at") or "unknown"
                        event_type = activity.get("event_type")
                        actor = activity.get("actor")
                        entity_type = activity.get("entity_type") or "n/a"
                        print(f"  {created_at} [{event_type}] {actor} entity={entity_type}")
    finally:
        await engine.dispose()


async def _run_activity(args: argparse.Namespace) -> None:
    from mapu.repos.audit import ActivityRepo

    engine, session_factory = _build_engine()

    try:
        cid = uuid.UUID(args.corpus_id)
        limit = min(max(getattr(args, "limit", 50), 1), 500)
        entity_id_value = getattr(args, "entity_id", None)
        entity_id = (
            entity_id_value
            if isinstance(entity_id_value, uuid.UUID)
            else uuid.UUID(entity_id_value)
            if entity_id_value
            else None
        )
        async with session_factory() as session:
            await _require_corpus_exists(session, cid)
            repo = ActivityRepo(session, cid)
            activities = await repo.list(
                event_type=getattr(args, "event_type", None),
                entity_type=getattr(args, "entity_type", None),
                entity_id=entity_id,
                limit=limit,
            )

            if args.json_output:
                print(
                    json.dumps(
                        [
                            {
                                "id": str(a.id),
                                "event_type": a.event_type,
                                "actor": a.actor,
                                "entity_type": a.entity_type,
                                "entity_id": str(a.entity_id) if a.entity_id else None,
                                "created_at": a.created_at.isoformat(),
                            }
                            for a in activities
                        ],
                        indent=2,
                    )
                )
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


def _run_benchmark_score_gate(args: argparse.Namespace) -> None:
    from pathlib import Path

    from mapu.evaluation.benchmark_score_gate import parse_score_spec, repo_root, run_gate

    try:
        specs = [parse_score_spec(raw) for raw in args.score]
    except ValueError as exc:
        print(str(exc).replace("score value", "--score value"), file=sys.stderr)
        sys.exit(2)

    rc, report = run_gate(
        specs,
        Path(args.out),
        require_clean_git=bool(args.require_clean_git),
        allow_non_release_methods=bool(
            getattr(args, "allow_non_release_methods", False)
            or getattr(args, "allow_diagnostic_methods", False)
        ),
    )
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = repo_root() / out_path
    failed_rows = [row for row in report["scores"] if not row["passed"]]
    print(
        json.dumps(
            {
                "status": report["status"],
                "path": str(out_path.resolve()),
                "benchmarks": len(report["scores"]),
                "failed": [row["benchmark"] for row in failed_rows],
                "failure_details": [
                    {
                        "benchmark": row["benchmark"],
                        "metric": row.get("metric"),
                        "metric_value": row.get("metric_value"),
                        "threshold": row.get("threshold", row.get("min_exact_match")),
                        "failure_reason": row.get("failure_reason"),
                    }
                    for row in failed_rows
                ],
            },
            ensure_ascii=True,
        )
    )
    if rc:
        sys.exit(rc)


def _run_benchmark_score_inspect(args: argparse.Namespace) -> None:
    from pathlib import Path

    score_path = Path(args.score)
    if not score_path.exists():
        print(f"Score report not found: {score_path}", file=sys.stderr)
        sys.exit(2)
    if args.top < 1:
        print("--top must be at least 1", file=sys.stderr)
        sys.exit(2)

    try:
        report = json.loads(score_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"Score report is invalid JSON: {score_path}: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(report, dict):
        print(f"Score report must be a JSON object: {score_path}", file=sys.stderr)
        sys.exit(2)
    items = report.get("worst_items") or sorted(
        report.get("item_scores") or [],
        key=lambda item: float(item.get("token_f1") or 0.0),
    )
    summary = {
        "status": report.get("status"),
        "path": str(score_path),
        "evaluated": report.get("evaluated"),
        "exact_match": report.get("exact_match"),
        "token_f1": report.get("token_f1"),
        "method_counts": report.get("method_counts") or {},
        "by_config": report.get("by_config"),
        "by_type": report.get("by_type"),
        "worst_items": items[: args.top],
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))


def _run_memory_benchmark_smoke(args: argparse.Namespace) -> None:
    from pathlib import Path

    from mapu.evaluation.memory_benchmark_smoke import run_smoke

    rc, report = run_smoke(
        output_dir=Path(args.out_dir),
        memoryarena_scenarios=(
            Path(args.memoryarena_scenarios) if args.memoryarena_scenarios else None
        ),
        ama_scenarios=Path(args.ama_scenarios) if args.ama_scenarios else None,
        export=not bool(args.no_export),
        memoryarena_limit_per_config=args.memoryarena_limit_per_config,
        ama_limit=args.ama_limit,
        predictor=args.predictor,
        min_token_f1=args.min_token_f1,
        allow_non_release_methods=bool(
            getattr(args, "allow_non_release_methods", False)
            or getattr(args, "allow_diagnostic_methods", False)
        ),
        verbose_steps=bool(args.verbose_steps),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "path": report["paths"]["report"],
                "gate_status": report["gate"]["status"],
                "failed": [
                    row["benchmark"]
                    for row in report["gate"]["scores"]
                    if not row["passed"]
                ],
                "score_summary": report.get("score_summary", []),
                "smoke_only": report.get("smoke_only"),
                "public_performance_evidence": report.get("public_performance_evidence"),
            },
            ensure_ascii=True,
        )
    )
    if rc:
        sys.exit(rc)


def _run_memoryarena_eval(args: argparse.Namespace) -> None:
    from mapu.evaluation import memoryarena

    if args.memoryarena_action == "catalog":
        rc = memoryarena.catalog()
    elif args.memoryarena_action == "export":
        rc = memoryarena.export(args.out, args.limit_per_config)
    elif args.memoryarena_action == "predict":
        rc = memoryarena.predict(
            args.scenarios,
            args.out,
            max_scenarios=args.max_scenarios,
            predictor=args.predictor,
        )
    elif args.memoryarena_action == "score":
        rc = memoryarena.score(
            args.scenarios,
            args.predictions,
            args.out,
            args.min_exact_match,
        )
    else:
        raise AssertionError(f"Unhandled MemoryArena action {args.memoryarena_action!r}")
    if rc:
        sys.exit(rc)


def _run_ama_bench_eval(args: argparse.Namespace) -> None:
    from mapu.evaluation import ama_bench

    if args.ama_bench_action == "catalog":
        rc = ama_bench.catalog()
    elif args.ama_bench_action == "export":
        rc = ama_bench.export(args.out, args.limit)
    elif args.ama_bench_action == "predict":
        rc = ama_bench.predict(
            args.scenarios,
            args.out,
            max_scenarios=args.max_scenarios,
            predictor=args.predictor,
        )
    elif args.ama_bench_action == "score":
        rc = ama_bench.score(
            args.scenarios,
            args.predictions,
            args.out,
            args.min_exact_match,
        )
    else:
        raise AssertionError(f"Unhandled AMA-Bench action {args.ama_bench_action!r}")
    if rc:
        sys.exit(rc)


if __name__ == "__main__":
    main()
