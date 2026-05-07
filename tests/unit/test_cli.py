"""Unit tests for the MapU CLI entry point."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest

from mapu.cli import main


class TestCLIParsing:
    def test_no_args_exits(self) -> None:
        with patch.object(sys, "argv", ["mapu"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_serve_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "serve", "--host", "0.0.0.0", "--port", "9000"]),
            patch("mapu.cli._run_serve") as mock_serve,
        ):
            main()
            mock_serve.assert_called_once_with("0.0.0.0", 9000)

    def test_serve_defaults(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "serve"]),
            patch("mapu.cli._run_serve") as mock_serve,
        ):
            main()
            mock_serve.assert_called_once_with("127.0.0.1", 8000)

    def test_mcp_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "mcp"]),
            patch("mapu.cli._run_mcp") as mock_mcp,
        ):
            main()
            mock_mcp.assert_called_once()

    def test_query_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "query", cid, "What is X?"]),
            patch("mapu.cli.asyncio") as mock_asyncio,
        ):
            main()
            mock_asyncio.run.assert_called_once()

    def test_ingest_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "ingest", cid, "test.txt"]),
            patch("mapu.cli.asyncio") as mock_asyncio,
        ):
            main()
            mock_asyncio.run.assert_called_once()


class TestRunServe:
    def test_run_serve_calls_uvicorn(self) -> None:
        with patch("uvicorn.run") as mock_uvicorn:
            from mapu.cli import _run_serve

            _run_serve("localhost", 5000)
            mock_uvicorn.assert_called_once_with(
                "mapu.api.app:app", host="localhost", port=5000,
            )


class TestRunMCP:
    def test_run_mcp_calls_server(self) -> None:
        with patch("mapu.mcp.server.run_mcp") as mock_run:
            from mapu.cli import _run_mcp

            _run_mcp()
            mock_run.assert_called_once()


class TestRunQuery:
    @pytest.mark.asyncio
    async def test_run_query_prints_synthesis(self, capsys: pytest.CaptureFixture[str]) -> None:
        from mapu.cli import _run_query

        mock_result = AsyncMock()
        mock_result.synthesis = "Answer text"
        mock_result.gaps = []

        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = lambda: mock_session  # noqa: E731
        mock_engine = AsyncMock()

        with (
            patch("mapu.config.Settings"),
            patch("mapu.db.engine.build_engine", return_value=(mock_engine, mock_factory)),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
        ):
            await _run_query("00000000-0000-0000-0000-000000000001", "What is X?")

        captured = capsys.readouterr()
        assert "Answer text" in captured.out

    @pytest.mark.asyncio
    async def test_run_query_prints_hits_when_no_synthesis(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        from mapu.cli import _run_query

        hit = AsyncMock()
        hit.predicate = "defines"
        hit.subject_name = "Entity"
        hit.object_name = "Target"
        hit.normalized_text = "Entity defines Target"

        mock_result = AsyncMock()
        mock_result.synthesis = None
        mock_result.hits = [hit]
        mock_result.gaps = ["missing data"]

        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = lambda: mock_session  # noqa: E731
        mock_engine = AsyncMock()

        with (
            patch("mapu.config.Settings"),
            patch("mapu.db.engine.build_engine", return_value=(mock_engine, mock_factory)),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
        ):
            await _run_query("00000000-0000-0000-0000-000000000001", "What is X?")

        captured = capsys.readouterr()
        assert "defines" in captured.out
        assert "missing data" in captured.out
