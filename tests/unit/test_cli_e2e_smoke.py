from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools import cli_e2e_smoke


def _completed(args: list[str], stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=args,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_cli_e2e_smoke_runs_full_workflow_and_cleans_up(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[list[str]] = []
    corpus_id = "00000000-0000-0000-0000-000000000123"

    def fake_run(args, **_kwargs):
        if args == ["git", "rev-parse", "HEAD"]:
            return _completed(args, "abc123\n")
        calls.append(list(args))
        if args[-2:] == ["doctor", "--json"]:
            return _completed(
                args,
                json.dumps(
                    {
                        "status": "ok",
                        "mcp": {
                            "required_tools_present": True,
                            "missing_required_tools": [],
                            "tool_count": 18,
                        },
                    }
                ),
            )
        if args[-3:] == ["corpus", "create", args[-1]]:
            return _completed(args, f"Created corpus: {corpus_id}\n")
        if "ingest" in args:
            return _completed(args, "Ingested: source.md\n")
        if "resume" in args:
            return _completed(args, json.dumps({"priority_next_actions": []}))
        if "query" in args:
            return _completed(
                args,
                json.dumps(
                    {
                        "answer": "Project Atlas is owned by Maya Chen.",
                        "epistemic_status": "sufficient",
                        "hits": [{"normalized_text": "Project Atlas is owned by Maya Chen."}],
                        "chunk_hits": [{"text": "Maya Chen"}],
                        "next_steps": ["Inspect source chunk."],
                    }
                ),
            )
        if "activity" in args:
            return _completed(args, json.dumps([{"event_type": "query"}]))
        if args[-4:] == ["corpus", "delete", corpus_id, "--yes"]:
            return _completed(args, f"Deleted corpus: {corpus_id}\n")
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(cli_e2e_smoke.subprocess, "run", fake_run)

    rc, report = cli_e2e_smoke.run_smoke(
        base_command=["uv", "run", "mapu"],
        work_dir=tmp_path,
        timeout=10,
    )

    assert rc == 0
    assert report["status"] == "ok"
    assert report["mapu_version"]
    assert report["git_sha"] == "abc123"
    assert report["required_checks"]["doctor_ok"] is True
    assert report["required_checks"]["doctor_required_tools_present"] is True
    assert report["doctor_tool_count"] == 18
    assert report["required_checks"]["delete_ok"] is True
    assert report["required_checks"]["query_has_structured_hit"] is True
    assert report["query_answer_nonempty"] is True
    assert not (tmp_path / "cli_e2e_source.md").exists()
    assert calls[-1][-4:] == ["corpus", "delete", corpus_id, "--yes"]


def test_cli_e2e_smoke_reports_query_failures_but_still_deletes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[list[str]] = []
    corpus_id = "00000000-0000-0000-0000-000000000456"

    def fake_run(args, **_kwargs):
        if args == ["git", "rev-parse", "HEAD"]:
            return _completed(args, "def456\n")
        calls.append(list(args))
        if args[-2:] == ["doctor", "--json"]:
            return _completed(
                args,
                json.dumps({"status": "ok", "mcp": {"required_tools_present": True}}),
            )
        if args[-3:] == ["corpus", "create", args[-1]]:
            return _completed(args, f"Created corpus: {corpus_id}\n")
        if "ingest" in args:
            return _completed(args, "Ingested: source.md\n")
        if "resume" in args:
            return _completed(args, json.dumps({"priority_next_actions": []}))
        if "query" in args:
            return _completed(args, stderr="query failed", returncode=1)
        if args[-4:] == ["corpus", "delete", corpus_id, "--yes"]:
            return _completed(args, f"Deleted corpus: {corpus_id}\n")
        return _completed(args, json.dumps([]))

    monkeypatch.setattr(cli_e2e_smoke.subprocess, "run", fake_run)

    rc, report = cli_e2e_smoke.run_smoke(
        base_command=["mapu"],
        work_dir=tmp_path,
        timeout=10,
    )

    assert rc == 1
    assert report["status"] == "fail"
    assert report["git_sha"] == "def456"
    assert report["required_checks"]["delete_ok"] is True
    assert any("query failed" in failure for failure in report["failures"])
    assert calls[-1][-4:] == ["corpus", "delete", corpus_id, "--yes"]


def test_cli_e2e_smoke_parses_json_after_log_prefix() -> None:
    payload = cli_e2e_smoke._parse_json(
        "INFO startup complete\n{\"answer\": \"ok\"}",
        "query",
    )

    assert payload == {"answer": "ok"}


def test_cli_e2e_smoke_reports_delete_timeout_as_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus_id = "00000000-0000-0000-0000-000000000789"

    def fake_run(args, **_kwargs):
        if args == ["git", "rev-parse", "HEAD"]:
            return _completed(args, "fed789\n")
        if args[-2:] == ["doctor", "--json"]:
            return _completed(
                args,
                json.dumps({"status": "ok", "mcp": {"required_tools_present": True}}),
            )
        if args[-3:] == ["corpus", "create", args[-1]]:
            return _completed(args, f"Created corpus: {corpus_id}\n")
        if "ingest" in args:
            return _completed(args, "Ingested: source.md\n")
        if "resume" in args:
            return _completed(args, json.dumps({"priority_next_actions": []}))
        if "query" in args:
            return _completed(
                args,
                json.dumps(
                    {
                        "answer": "Maya Chen.",
                        "epistemic_status": "insufficient",
                        "hits": [{"normalized_text": "Project Atlas is owned by Maya Chen."}],
                        "chunk_hits": [{"text": "Maya Chen"}],
                        "next_steps": ["Inspect source chunk."],
                    }
                ),
            )
        if "activity" in args:
            return _completed(args, json.dumps([{"event_type": "query"}]))
        if args[-4:] == ["corpus", "delete", corpus_id, "--yes"]:
            raise subprocess.TimeoutExpired(args, timeout=10)
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(cli_e2e_smoke.subprocess, "run", fake_run)

    rc, report = cli_e2e_smoke.run_smoke(
        base_command=["mapu"],
        work_dir=tmp_path,
        timeout=10,
    )

    assert rc == 1
    assert report["git_sha"] == "fed789"
    assert report["required_checks"]["delete_ok"] is False
    assert any("corpus delete failed" in failure for failure in report["failures"])
    assert not (tmp_path / "cli_e2e_source.md").exists()


def test_cli_e2e_smoke_reports_doctor_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_run(args, **_kwargs):
        if args == ["git", "rev-parse", "HEAD"]:
            return _completed(args, "abc123\n")
        if args[-2:] == ["doctor", "--json"]:
            return _completed(
                args,
                json.dumps(
                    {
                        "status": "fail",
                        "mcp": {
                            "required_tools_present": False,
                            "missing_required_tools": ["handoff_context"],
                            "tool_count": 17,
                        },
                    }
                ),
            )
        raise AssertionError(f"unexpected command: {args}")

    monkeypatch.setattr(cli_e2e_smoke.subprocess, "run", fake_run)

    rc, report = cli_e2e_smoke.run_smoke(
        base_command=["mapu"],
        work_dir=tmp_path,
        timeout=10,
    )

    assert rc == 1
    assert report["required_checks"]["doctor_ok"] is False
    assert report["required_checks"]["doctor_required_tools_present"] is False
    assert "doctor_ok" in report["failed_checks"]
    assert "doctor_required_tools_present" in report["failed_checks"]
