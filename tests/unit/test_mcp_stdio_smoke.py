"""Unit tests for the MCP stdio smoke helper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools import mcp_stdio_smoke


class _FakeStdioClient:
    def __init__(self, server: object) -> None:
        self.server = server

    async def __aenter__(self) -> tuple[object, object]:
        return object(), object()

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeClientSession:
    tool_names: list[str] = []

    def __init__(self, read_stream: object, write_stream: object) -> None:
        self.read_stream = read_stream
        self.write_stream = write_stream
        self.initialized = False

    async def __aenter__(self) -> "_FakeClientSession":
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


@pytest.mark.asyncio
async def test_run_reports_required_tools_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClientSession.tool_names = sorted(mcp_stdio_smoke.REQUIRED_TOOLS | {"extra_tool"})
    monkeypatch.setattr(mcp_stdio_smoke, "stdio_client", _FakeStdioClient)
    monkeypatch.setattr(mcp_stdio_smoke, "ClientSession", _FakeClientSession)

    result = await mcp_stdio_smoke._run("mapu", ["mcp"], None)

    assert result["command"] == "mapu"
    assert result["args"] == ["mcp"]
    assert result["required_tools_present"] is True
    assert result["missing_required_tools"] == []
    assert result["tool_count"] == len(mcp_stdio_smoke.REQUIRED_TOOLS) + 1


@pytest.mark.asyncio
async def test_run_reports_missing_required_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClientSession.tool_names = ["create_corpus", "query"]
    monkeypatch.setattr(mcp_stdio_smoke, "stdio_client", _FakeStdioClient)
    monkeypatch.setattr(mcp_stdio_smoke, "ClientSession", _FakeClientSession)

    result = await mcp_stdio_smoke._run("mapu", ["mcp"], None)

    assert result["required_tools_present"] is False
    assert "delete_corpus" in result["missing_required_tools"]
    assert "reset_all_corpora" in result["missing_required_tools"]


def test_main_exits_when_required_tools_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_run(command: str, args: list[str], cwd: str | None) -> dict[str, object]:
        return {
            "command": command,
            "args": args,
            "tool_count": 1,
            "required_tools_present": False,
            "missing_required_tools": ["query"],
            "tools": ["create_corpus"],
        }

    monkeypatch.setattr(mcp_stdio_smoke, "_run", fake_run)
    monkeypatch.setattr(mcp_stdio_smoke.sys, "argv", ["mcp_stdio_smoke.py"])
    monkeypatch.setattr(mcp_stdio_smoke.Path, "mkdir", MagicMock())
    monkeypatch.setattr(mcp_stdio_smoke.Path, "write_text", MagicMock())

    with pytest.raises(SystemExit) as exc_info:
        mcp_stdio_smoke.main()

    assert exc_info.value.code == 1
    assert "Missing required tools: query" in capsys.readouterr().out
