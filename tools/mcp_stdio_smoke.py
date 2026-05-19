"""Process-level smoke test for the installed MapU MCP stdio server."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.metadata
import json
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

REPO_SRC = Path(__file__).resolve().parents[1] / "src"
if REPO_SRC.exists() and str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

REQUIRED_TOOLS = set(importlib.import_module("mapu.mcp.tool_contract").REQUIRED_MCP_TOOLS)

LIGHTWEIGHT_RUNTIME_ENV = {
    "MAPU_EMBEDDING_PROVIDER": "local",
    "MAPU_EMBEDDING_MODEL": "hash-deterministic",
    "MAPU_EXTRACTION_GLINER_ENABLED": "false",
    "MAPU_EXTRACTION_GLINER_RELEX_ENABLED": "false",
    "MAPU_EXTRACTION_SETFIT_ENABLED": "false",
    "MAPU_EXTRACTION_LLM_ENABLED": "false",
}

SMOKE_DOCUMENT = """Project Orion handoff

The current owner is Maya Chen.
The launch codename is Northstar.
The next action is to audit real MCP stdio ingestion before tuning benchmarks.
"""


def _extract_tool_payload(result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool call failed: {result!r}")
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", []) or []:
        if getattr(item, "type", None) != "text":
            continue
        text = getattr(item, "text", "").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    return {}


def _mapu_version() -> str:
    try:
        return importlib.metadata.version("mapu")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:  # noqa: BLE001 - provenance is best effort.
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


async def _call_tool(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    read_timeout = timedelta(seconds=timeout_seconds) if timeout_seconds else None
    return _extract_tool_payload(
        await session.call_tool(name, arguments, read_timeout_seconds=read_timeout)
    )


async def _run(
    command: str,
    args: list[str],
    cwd: str | None,
    *,
    workflow: bool = True,
    lightweight_runtime: bool = True,
    tool_timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    server = StdioServerParameters(
        command=command,
        args=args,
        cwd=cwd,
        env=LIGHTWEIGHT_RUNTIME_ENV if lightweight_runtime else None,
    )
    async with (
        stdio_client(server) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        response = await session.list_tools()
        tool_names = sorted(tool.name for tool in response.tools)
        missing = sorted(REQUIRED_TOOLS - set(tool_names))
        result: dict[str, Any] = {
            "status": "ok",
            "command": command,
            "args": args,
            "mapu_version": _mapu_version(),
            "git_sha": _git_sha(),
            "tool_count": len(tool_names),
            "required_tools_present": not missing,
            "missing_required_tools": missing,
            "tools": tool_names,
            "workflow_enabled": workflow,
            "lightweight_runtime_overrides": lightweight_runtime,
            "tool_timeout_seconds": tool_timeout_seconds,
        }
        if missing:
            result["status"] = "fail"
        if not workflow or missing:
            return result

        corpus_id: str | None = None
        checks = {
            "create_ok": False,
            "ingest_ok": False,
            "contribute_ok": False,
            "review_ok": False,
            "query_answer_nonempty": False,
            "query_has_next_steps": False,
            "handoff_has_protocol": False,
            "handoff_has_priority_actions": False,
            "learning_feedback_logged": False,
            "activity_written": False,
            "delete_ok": False,
        }
        failures: list[str] = []
        try:
            created = await _call_tool(
                session,
                "create_corpus",
                {
                    "name": f"mcp-stdio-smoke-{uuid.uuid4()}",
                    "description": "Disposable MCP stdio smoke corpus.",
                },
                timeout_seconds=tool_timeout_seconds,
            )
            corpus_id = str(created.get("id") or "")
            checks["create_ok"] = bool(corpus_id)
            if not corpus_id:
                failures.append("create_corpus did not return an id")
                return result | {
                    "corpus_id": corpus_id,
                    "required_checks": checks,
                    "failed_checks": [key for key, ok in checks.items() if not ok],
                    "failures": failures,
                }

            ingested = await _call_tool(
                session,
                "ingest_document",
                {
                    "corpus_id": corpus_id,
                    "content": SMOKE_DOCUMENT,
                    "mime_type": "text/plain",
                    "source_uri": "mcp-stdio-smoke://project-orion-handoff",
                    "document_type": "handoff",
                    "publication_context": "internal_document",
                    "source_identity": "mcp_stdio_smoke",
                    "independence_group": "mcp_stdio_smoke",
                },
                timeout_seconds=tool_timeout_seconds,
            )
            checks["ingest_ok"] = bool(ingested.get("document_id")) and ingested.get(
                "chunks", 0
            ) > 0
            if not checks["ingest_ok"]:
                failures.append("ingest_document did not return document_id and chunks")

            contributed = await _call_tool(
                session,
                "contribute_proposition",
                {
                    "corpus_id": corpus_id,
                    "subject_name": "Project Orion",
                    "predicate": "owned_by",
                    "object_name": "Maya Chen",
                    "normalized_text": "Project Orion is owned by Maya Chen.",
                    "actor": "mcp_stdio_smoke",
                },
                timeout_seconds=tool_timeout_seconds,
            )
            attestation_id = str(contributed.get("attestation_id") or "")
            checks["contribute_ok"] = bool(contributed.get("proposition_id")) and bool(
                attestation_id
            )
            if not checks["contribute_ok"]:
                failures.append(
                    "contribute_proposition did not return proposition and attestation ids"
                )

            reviewed = await _call_tool(
                session,
                "review_attestation",
                {
                    "corpus_id": corpus_id,
                    "attestation_id": attestation_id,
                    "decision": "accepted",
                    "actor": "mcp_stdio_smoke",
                    "reason": "Smoke fixture assertion accepted for transport validation.",
                },
                timeout_seconds=tool_timeout_seconds,
            )
            checks["review_ok"] = reviewed.get("new_status") == "accepted"
            if not checks["review_ok"]:
                failures.append("review_attestation did not accept the contributed attestation")

            queried = await _call_tool(
                session,
                "query",
                {
                    "corpus_id": corpus_id,
                    "question": "Who owns Project Orion?",
                    "max_results": 5,
                },
                timeout_seconds=tool_timeout_seconds,
            )
            answer = str(queried.get("answer") or queried.get("synthesis") or "").strip()
            checks["query_answer_nonempty"] = bool(answer)
            checks["query_has_next_steps"] = bool(queried.get("next_steps"))
            if not checks["query_answer_nonempty"]:
                failures.append("query did not return a non-empty answer")
            if not checks["query_has_next_steps"]:
                failures.append("query did not return next_steps")

            handoff = await _call_tool(
                session,
                "handoff_context",
                {
                    "corpus_id": corpus_id,
                    "max_gaps": 5,
                    "max_activity": 10,
                    "max_actions": 5,
                },
                timeout_seconds=tool_timeout_seconds,
            )
            checks["handoff_has_protocol"] = handoff.get("protocol") == "mapu-resume-handoff"
            checks["handoff_has_priority_actions"] = bool(
                handoff.get("priority_next_actions")
            )
            if not checks["handoff_has_protocol"]:
                failures.append("handoff_context did not return the resume handoff protocol")
            if not checks["handoff_has_priority_actions"]:
                failures.append("handoff_context did not return priority_next_actions")

            next_steps = queried.get("next_steps")
            if not isinstance(next_steps, list):
                next_steps = []
            first_step = (
                str(next_steps[0])
                if next_steps
                else "Review MCP stdio smoke query evidence."
            )
            feedback = await _call_tool(
                session,
                "log_learning_feedback",
                {
                    "corpus_id": corpus_id,
                    "question": "Who owns Project Orion?",
                    "step": first_step,
                    "outcome": "helpful",
                    "actor": "mcp_stdio_smoke",
                    "notes": "Smoke validation that learning feedback works over MCP stdio.",
                },
                timeout_seconds=tool_timeout_seconds,
            )
            checks["learning_feedback_logged"] = bool(
                feedback.get("success") and feedback.get("event_id")
            )
            if not checks["learning_feedback_logged"]:
                failures.append("log_learning_feedback did not return success and event_id")

            activity = await _call_tool(
                session,
                "list_activity",
                {
                    "corpus_id": corpus_id,
                    "limit": 10,
                },
                timeout_seconds=tool_timeout_seconds,
            )
            checks["activity_written"] = bool(activity.get("activities"))
            if not checks["activity_written"]:
                failures.append("list_activity returned no activity after query")
        except Exception as exc:
            failures.append(str(exc))
        finally:
            if corpus_id:
                try:
                    deleted = await _call_tool(
                        session,
                        "delete_corpus",
                        {"corpus_id": corpus_id, "confirm": True},
                        timeout_seconds=tool_timeout_seconds,
                    )
                    checks["delete_ok"] = deleted.get("deleted_corpus_id") == corpus_id
                    if not checks["delete_ok"]:
                        failures.append("delete_corpus did not confirm deletion")
                except Exception as exc:
                    checks["delete_ok"] = False
                    failures.append(f"delete_corpus failed: {exc}")

        status = "ok" if not failures and not any(not ok for ok in checks.values()) else "fail"
        result.update(
            {
                "status": status,
                "corpus_id": corpus_id,
                "required_checks": checks,
                "failed_checks": [key for key, ok in checks.items() if not ok],
                "failures": failures,
                "query_answer_preview": answer[:200] if "answer" in locals() else "",
                "activity_count": len(activity.get("activities", []))
                if "activity" in locals()
                else 0,
            }
        )
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--command",
        default="mapu",
        help="MCP server command to execute; defaults to installed mapu script.",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=None,
        dest="args",
        help="Argument to pass to command. Defaults to one 'mcp' argument.",
    )
    parser.add_argument("--cwd", default=None, help="Optional working directory for the server.")
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only verify tool discovery; skip the DB-backed MCP workflow.",
    )
    parser.add_argument(
        "--use-current-ml-env",
        action="store_true",
        help=(
            "Inherit current ML/extraction environment instead of forcing lightweight "
            "deterministic smoke settings."
        ),
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="Smoke timeout in seconds.")
    parser.add_argument(
        "--tool-timeout",
        type=float,
        default=30.0,
        help="Per MCP tool-call timeout in seconds.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("logs") / "mcp_stdio_smoke_last.json",
        help="Path where the JSON smoke report is written.",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    try:
        result = asyncio.run(
            asyncio.wait_for(
                _run(
                    args.command,
                    args.args or ["mcp"],
                    args.cwd,
                    workflow=not args.list_only,
                    lightweight_runtime=not args.use_current_ml_env,
                    tool_timeout_seconds=args.tool_timeout,
                ),
                timeout=args.timeout,
            )
        )
    except TimeoutError:
        result = {
            "status": "fail",
            "command": args.command,
            "args": args.args or ["mcp"],
            "mapu_version": _mapu_version(),
            "git_sha": _git_sha(),
            "tool_count": 0,
            "required_tools_present": False,
            "missing_required_tools": sorted(REQUIRED_TOOLS),
            "tools": [],
            "workflow_enabled": not args.list_only,
            "lightweight_runtime_overrides": not args.use_current_ml_env,
            "tool_timeout_seconds": args.tool_timeout,
            "timed_out": True,
            "failed_checks": ["global_timeout"],
            "failures": [f"MCP stdio smoke exceeded {args.timeout} seconds"],
        }
    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"MCP stdio smoke: {result['tool_count']} tools")
        print("Required tools present:", result["required_tools_present"])
        if result["missing_required_tools"]:
            print("Missing required tools:", ", ".join(result["missing_required_tools"]))
        if result.get("workflow_enabled"):
            print("Workflow checks:", "ok" if not result.get("failed_checks") else "failed")
            if result.get("failed_checks"):
                print("Failed checks:", ", ".join(result["failed_checks"]))

    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        pass

    if not result["required_tools_present"] or result.get("failed_checks"):
        sys.exit(1)


if __name__ == "__main__":
    main()
