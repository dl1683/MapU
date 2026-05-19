"""Unit tests for the MCP stdio smoke helper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from tools import mcp_stdio_smoke


def test_required_tools_use_runtime_contract() -> None:
    from mapu.mcp.tool_contract import REQUIRED_MCP_TOOLS

    assert set(REQUIRED_MCP_TOOLS) == mcp_stdio_smoke.REQUIRED_TOOLS


class _FakeStdioClient:
    def __init__(self, server: object) -> None:
        self.server = server

    async def __aenter__(self) -> tuple[object, object]:
        return object(), object()

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeClientSession:
    tool_names: list[str] = []
    tool_payloads: dict[str, dict[str, object]] = {}
    tool_calls: list[tuple[str, dict[str, object]]] = []

    def __init__(self, read_stream: object, write_stream: object) -> None:
        self.read_stream = read_stream
        self.write_stream = write_stream
        self.initialized = False

    async def __aenter__(self) -> _FakeClientSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def initialize(self) -> None:
        self.initialized = True

    async def list_tools(self) -> SimpleNamespace:
        assert self.initialized
        return SimpleNamespace(
            tools=[SimpleNamespace(name=name) for name in self.tool_names],
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        read_timeout_seconds: object | None = None,
    ) -> SimpleNamespace:
        self.tool_calls.append((name, arguments))
        payload = self.tool_payloads[name]
        return SimpleNamespace(structuredContent=payload, content=[], isError=False)


@pytest.mark.asyncio
async def test_run_reports_required_tools_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClientSession.tool_names = sorted(mcp_stdio_smoke.REQUIRED_TOOLS | {"extra_tool"})
    _FakeClientSession.tool_payloads = {}
    _FakeClientSession.tool_calls = []
    monkeypatch.setattr(mcp_stdio_smoke, "stdio_client", _FakeStdioClient)
    monkeypatch.setattr(mcp_stdio_smoke, "ClientSession", _FakeClientSession)

    result = await mcp_stdio_smoke._run("mapu", ["mcp"], None, workflow=False)

    assert result["command"] == "mapu"
    assert result["status"] == "ok"
    assert result["args"] == ["mcp"]
    assert result["required_tools_present"] is True
    assert result["missing_required_tools"] == []
    assert result["tool_count"] == len(mcp_stdio_smoke.REQUIRED_TOOLS) + 1
    assert result["workflow_enabled"] is False
    assert _FakeClientSession.tool_calls == []


@pytest.mark.asyncio
async def test_run_reports_missing_required_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClientSession.tool_names = ["create_corpus", "query"]
    _FakeClientSession.tool_payloads = {}
    _FakeClientSession.tool_calls = []
    monkeypatch.setattr(mcp_stdio_smoke, "stdio_client", _FakeStdioClient)
    monkeypatch.setattr(mcp_stdio_smoke, "ClientSession", _FakeClientSession)

    result = await mcp_stdio_smoke._run("mapu", ["mcp"], None)

    assert result["status"] == "fail"
    assert result["required_tools_present"] is False
    assert "delete_corpus" in result["missing_required_tools"]
    assert "handoff_context" in result["missing_required_tools"]
    assert "log_learning_feedback" in result["missing_required_tools"]
    assert "reset_all_corpora" in result["missing_required_tools"]
    assert _FakeClientSession.tool_calls == []


@pytest.mark.asyncio
async def test_run_executes_db_backed_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    corpus_id = "cfa1f281-2d70-447e-ac9e-0ea7bf4331e8"
    _FakeClientSession.tool_names = sorted(mcp_stdio_smoke.REQUIRED_TOOLS)
    _FakeClientSession.tool_payloads = {
        "create_corpus": {"id": corpus_id, "name": "smoke"},
        "ingest_document": {"document_id": "doc-1", "chunks": 1},
        "contribute_proposition": {
            "proposition_id": "prop-1",
            "attestation_id": "att-1",
        },
        "review_attestation": {"new_status": "accepted"},
        "query": {
            "answer": "Maya Chen owns Project Orion.",
            "next_steps": ["Review integration workflow evidence."],
        },
        "handoff_context": {
            "protocol": "mapu-resume-handoff",
            "priority_next_actions": [{"step": "query the current owner"}],
        },
        "log_learning_feedback": {"success": True, "event_id": "event-1"},
        "list_activity": {"activities": [{"event_type": "query"}]},
        "delete_corpus": {"deleted_corpus_id": corpus_id},
    }
    _FakeClientSession.tool_calls = []
    monkeypatch.setattr(mcp_stdio_smoke, "stdio_client", _FakeStdioClient)
    monkeypatch.setattr(mcp_stdio_smoke, "ClientSession", _FakeClientSession)

    result = await mcp_stdio_smoke._run("mapu", ["mcp"], None)

    assert result["workflow_enabled"] is True
    assert result["status"] == "ok"
    assert result["failed_checks"] == []
    assert result["required_checks"] == {
        "create_ok": True,
        "ingest_ok": True,
        "contribute_ok": True,
        "review_ok": True,
        "query_answer_nonempty": True,
        "query_has_next_steps": True,
        "handoff_has_protocol": True,
        "handoff_has_priority_actions": True,
        "learning_feedback_logged": True,
        "activity_written": True,
        "delete_ok": True,
    }
    assert [name for name, _ in _FakeClientSession.tool_calls] == [
        "create_corpus",
        "ingest_document",
        "contribute_proposition",
        "review_attestation",
        "query",
        "handoff_context",
        "log_learning_feedback",
        "list_activity",
        "delete_corpus",
    ]


@pytest.mark.asyncio
async def test_run_cleans_up_after_query_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    corpus_id = "cfa1f281-2d70-447e-ac9e-0ea7bf4331e8"
    _FakeClientSession.tool_names = sorted(mcp_stdio_smoke.REQUIRED_TOOLS)
    _FakeClientSession.tool_payloads = {
        "create_corpus": {"id": corpus_id, "name": "smoke"},
        "ingest_document": {"document_id": "doc-1", "chunks": 1},
        "contribute_proposition": {
            "proposition_id": "prop-1",
            "attestation_id": "att-1",
        },
        "review_attestation": {"new_status": "accepted"},
        "query": {"answer": "", "next_steps": []},
        "handoff_context": {
            "protocol": "mapu-resume-handoff",
            "priority_next_actions": [{"step": "query the current owner"}],
        },
        "log_learning_feedback": {"success": True, "event_id": "event-1"},
        "list_activity": {"activities": []},
        "delete_corpus": {"deleted_corpus_id": corpus_id},
    }
    _FakeClientSession.tool_calls = []
    monkeypatch.setattr(mcp_stdio_smoke, "stdio_client", _FakeStdioClient)
    monkeypatch.setattr(mcp_stdio_smoke, "ClientSession", _FakeClientSession)

    result = await mcp_stdio_smoke._run("mapu", ["mcp"], None)

    assert result["status"] == "fail"
    assert "query_answer_nonempty" in result["failed_checks"]
    assert "query_has_next_steps" in result["failed_checks"]
    assert result["required_checks"]["delete_ok"] is True
    assert _FakeClientSession.tool_calls[-1][0] == "delete_corpus"


def test_main_exits_when_required_tools_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_run(
        command: str,
        args: list[str],
        cwd: str | None,
        *,
        workflow: bool = True,
        lightweight_runtime: bool = True,
        tool_timeout_seconds: float = 30.0,
    ) -> dict[str, object]:
        return {
            "status": "fail",
            "command": command,
            "args": args,
            "mapu_version": "0.0.0-test",
            "git_sha": "abc123",
            "tool_count": 1,
            "required_tools_present": False,
            "missing_required_tools": ["query"],
            "tools": ["create_corpus"],
            "workflow_enabled": workflow,
            "lightweight_runtime_overrides": lightweight_runtime,
            "tool_timeout_seconds": tool_timeout_seconds,
        }

    monkeypatch.setattr(mcp_stdio_smoke, "_run", fake_run)
    monkeypatch.setattr(mcp_stdio_smoke.sys, "argv", ["mcp_stdio_smoke.py"])
    monkeypatch.setattr(mcp_stdio_smoke.Path, "mkdir", MagicMock())
    monkeypatch.setattr(mcp_stdio_smoke.Path, "write_text", MagicMock())

    with pytest.raises(SystemExit) as exc_info:
        mcp_stdio_smoke.main()

    assert exc_info.value.code == 1
    assert "Missing required tools: query" in capsys.readouterr().out


def test_main_list_only_skips_db_workflow_and_emits_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_run(
        command: str,
        args: list[str],
        cwd: str | None,
        *,
        workflow: bool = True,
        lightweight_runtime: bool = True,
        tool_timeout_seconds: float = 30.0,
    ) -> dict[str, object]:
        calls.append(
            {
                "command": command,
                "args": args,
                "cwd": cwd,
                "workflow": workflow,
                "lightweight_runtime": lightweight_runtime,
                "tool_timeout_seconds": tool_timeout_seconds,
            }
        )
        return {
            "status": "ok",
            "command": command,
            "args": args,
            "mapu_version": "0.0.0-test",
            "git_sha": "abc123",
            "tool_count": len(mcp_stdio_smoke.REQUIRED_TOOLS),
            "required_tools_present": True,
            "missing_required_tools": [],
            "tools": sorted(mcp_stdio_smoke.REQUIRED_TOOLS),
            "workflow_enabled": workflow,
            "lightweight_runtime_overrides": lightweight_runtime,
            "tool_timeout_seconds": tool_timeout_seconds,
        }

    monkeypatch.setattr(mcp_stdio_smoke, "_run", fake_run)
    monkeypatch.setattr(
        mcp_stdio_smoke.sys,
        "argv",
        [
            "mcp_stdio_smoke.py",
            "--command",
            "mapu",
            "--arg",
            "mcp",
            "--list-only",
            "--json",
        ],
    )
    monkeypatch.setattr(mcp_stdio_smoke.Path, "mkdir", MagicMock())
    write_text = MagicMock()
    monkeypatch.setattr(mcp_stdio_smoke.Path, "write_text", write_text)

    mcp_stdio_smoke.main()

    assert calls == [
        {
            "command": "mapu",
            "args": ["mcp"],
            "cwd": None,
            "workflow": False,
            "lightweight_runtime": True,
            "tool_timeout_seconds": 30.0,
        }
    ]
    report = mcp_stdio_smoke.json.loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    assert report["workflow_enabled"] is False
    assert report["required_tools_present"] is True
    persisted = mcp_stdio_smoke.json.loads(write_text.call_args.args[0])
    assert persisted["workflow_enabled"] is False


def test_main_reports_global_timeout_as_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_run(
        command: str,
        args: list[str],
        cwd: str | None,
        *,
        workflow: bool = True,
        lightweight_runtime: bool = True,
        tool_timeout_seconds: float = 30.0,
    ) -> dict[str, object]:
        await mcp_stdio_smoke.asyncio.sleep(60)
        return {}

    monkeypatch.setattr(mcp_stdio_smoke, "_run", fake_run)
    monkeypatch.setattr(mcp_stdio_smoke, "_mapu_version", lambda: "0.0.0-test")
    monkeypatch.setattr(mcp_stdio_smoke, "_git_sha", lambda: "abc123")
    monkeypatch.setattr(
        mcp_stdio_smoke.sys,
        "argv",
        ["mcp_stdio_smoke.py", "--timeout", "0.01", "--json"],
    )
    monkeypatch.setattr(mcp_stdio_smoke.Path, "mkdir", MagicMock())
    monkeypatch.setattr(mcp_stdio_smoke.Path, "write_text", MagicMock())

    with pytest.raises(SystemExit) as exc_info:
        mcp_stdio_smoke.main()

    assert exc_info.value.code == 1
    report = mcp_stdio_smoke.json.loads(capsys.readouterr().out)
    assert report["timed_out"] is True
    assert report["status"] == "fail"
    assert report["mapu_version"] == "0.0.0-test"
    assert report["git_sha"] == "abc123"
    assert report["failed_checks"] == ["global_timeout"]
    assert "MCP stdio smoke exceeded 0.01 seconds" in report["failures"]
