"""End-to-end smoke test for the installed MapU CLI continuity workflow."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

UUID_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)

DEFAULT_SOURCE_TEXT = """Project Atlas handoff

The current owner is Maya Chen.
The launch codename is Northstar.
The next action is to audit the CLI continuity workflow before changing benchmark logic.
"""


def _run_command(
    base_command: list[str],
    args: list[str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*base_command, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _parse_json(stdout: str, command_label: str) -> Any:
    text = stdout.strip()
    decoder = json.JSONDecoder()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            payload, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if text[index + end :].strip():
            continue
        return payload
    raise RuntimeError(f"{command_label} did not emit valid JSON")


def _require_ok(result: subprocess.CompletedProcess[str], command_label: str) -> str:
    if result.returncode == 0:
        return result.stdout
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    detail = stderr or stdout or f"exit code {result.returncode}"
    raise RuntimeError(f"{command_label} failed: {detail}")


def _write_source_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_SOURCE_TEXT, encoding="utf-8")


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


def run_smoke(
    *,
    base_command: list[str],
    work_dir: Path,
    timeout: int,
) -> tuple[int, dict[str, Any]]:
    work_dir.mkdir(parents=True, exist_ok=True)
    source_path = work_dir / "cli_e2e_source.md"
    _write_source_file(source_path)

    corpus_id: str | None = None
    delete_ok = False
    failures: list[str] = []
    outputs: dict[str, Any] = {}
    name = f"cli-e2e-{int(time.time())}"

    try:
        doctor = _run_command(base_command, ["doctor", "--json"], timeout)
        doctor_payload = _parse_json(_require_ok(doctor, "doctor"), "doctor")

        create = _run_command(base_command, ["corpus", "create", name], timeout)
        create_stdout = _require_ok(create, "corpus create")
        match = UUID_RE.search(create_stdout)
        if not match:
            raise RuntimeError(f"corpus create output did not contain corpus UUID: {create_stdout}")
        corpus_id = match.group(1)

        ingest = _run_command(
            base_command,
            [
                "ingest",
                corpus_id,
                str(source_path),
                "--document-type",
                "markdown",
                "--source-uri",
                "repo://.tmp/cli-e2e-source.md",
            ],
            timeout,
        )
        ingest_stdout = _require_ok(ingest, "ingest")

        resume = _run_command(
            base_command,
            ["resume", corpus_id, "--max-gaps", "5", "--max-activity", "10", "--json"],
            timeout,
        )
        resume_payload = _parse_json(_require_ok(resume, "resume"), "resume")

        query = _run_command(
            base_command,
            [
                "query",
                corpus_id,
                "Who owns Project Atlas and what should happen next?",
                "--json",
            ],
            timeout,
        )
        query_payload = _parse_json(_require_ok(query, "query"), "query")

        activity = _run_command(
            base_command,
            ["activity", corpus_id, "--limit", "10", "--json"],
            timeout,
        )
        activity_payload = _parse_json(_require_ok(activity, "activity"), "activity")

        answer = str(query_payload.get("answer") or "")
        doctor_mcp = doctor_payload.get("mcp") if isinstance(doctor_payload, dict) else None
        outputs = {
            "doctor_ok": isinstance(doctor_payload, dict) and doctor_payload.get("status") == "ok",
            "doctor_required_tools_present": (
                isinstance(doctor_mcp, dict)
                and doctor_mcp.get("required_tools_present") is True
            ),
            "doctor_tool_count": doctor_mcp.get("tool_count")
            if isinstance(doctor_mcp, dict)
            else None,
            "ingest_ok": "Ingested" in ingest_stdout,
            "resume_has_priority_next_actions": "priority_next_actions" in resume_payload,
            "query_answer_nonempty": bool(answer.strip()),
            "query_answer_preview": answer[:240],
            "query_epistemic_status": query_payload.get("epistemic_status"),
            "query_chunk_hits": len(query_payload.get("chunk_hits") or []),
            "query_next_steps": len(query_payload.get("next_steps") or []),
            "activity_count": len(activity_payload) if isinstance(activity_payload, list) else 0,
        }
    except Exception as exc:  # noqa: BLE001 - smoke reports failure details.
        failures.append(str(exc))
    finally:
        if corpus_id:
            try:
                delete = _run_command(
                    base_command,
                    ["corpus", "delete", corpus_id, "--yes"],
                    timeout,
                )
                delete_ok = delete.returncode == 0 and "Deleted corpus" in delete.stdout
                if not delete_ok:
                    failures.append(
                        (delete.stderr or delete.stdout or "corpus delete failed").strip()
                    )
            except Exception as exc:  # noqa: BLE001 - cleanup failures belong in smoke report.
                failures.append(f"corpus delete failed: {exc}")
        with suppress(OSError):
            source_path.unlink()

    required_checks = {
        "doctor_ok": bool(outputs.get("doctor_ok")),
        "doctor_required_tools_present": bool(outputs.get("doctor_required_tools_present")),
        "ingest_ok": bool(outputs.get("ingest_ok")),
        "resume_has_priority_next_actions": bool(outputs.get("resume_has_priority_next_actions")),
        "query_answer_nonempty": bool(outputs.get("query_answer_nonempty")),
        "query_has_next_steps": int(outputs.get("query_next_steps") or 0) > 0,
        "activity_written": int(outputs.get("activity_count") or 0) > 0,
        "delete_ok": delete_ok,
    }
    failed_checks = sorted(name for name, ok in required_checks.items() if not ok)
    report = {
        "status": "ok" if not failures and not failed_checks else "fail",
        "command": base_command,
        "mapu_version": _mapu_version(),
        "git_sha": _git_sha(),
        "corpus_id": corpus_id,
        "work_dir": str(work_dir),
        "required_checks": required_checks,
        "failed_checks": failed_checks,
        "failures": failures,
        **outputs,
    }
    return (0 if report["status"] == "ok" else 1), report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--command",
        default="mapu",
        help="CLI command to execute; defaults to installed mapu script.",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=None,
        dest="args",
        help=(
            "Argument to prefix before MapU subcommands. "
            "Example: --command uv --arg run --arg mapu"
        ),
    )
    parser.add_argument("--work-dir", default=".tmp/cli-e2e-smoke")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    base_command = [args.command, *(args.args or [])]
    rc, report = run_smoke(
        base_command=base_command,
        work_dir=Path(args.work_dir),
        timeout=args.timeout,
    )
    if args.json_output:
        print(json.dumps(report, indent=2))
    else:
        print(f"CLI e2e smoke: {report['status']}")
        print("Required checks:", json.dumps(report["required_checks"], sort_keys=True))
        if report["failures"]:
            print("Failures:")
            for failure in report["failures"]:
                print(f"  - {failure}")

    output_path = Path("logs") / "cli_e2e_smoke_last.json"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    except OSError:
        pass

    sys.exit(rc)


if __name__ == "__main__":
    main()
