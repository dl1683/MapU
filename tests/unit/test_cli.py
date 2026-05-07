"""Unit tests for the MapU CLI entry point."""

from __future__ import annotations

import argparse
import sys
from unittest.mock import AsyncMock, patch

import pytest

from mapu.cli import main


def _make_query_args(
    corpus_id: str = "00000000-0000-0000-0000-000000000001",
    question: str = "What is X?",
    json_output: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        corpus_id=corpus_id,
        question=question,
        max_results=20,
        situation_id=None,
        as_of=None,
        json_output=json_output,
    )


class TestCLIParsing:
    def test_no_args_exits(self) -> None:
        with patch.object(sys, "argv", ["mapu"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_bad_uuid_exits(self) -> None:
        with patch.object(sys, "argv", ["mapu", "query", "not-a-uuid", "What?"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

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

    def test_investigate_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "investigate", cid, "Why?"]),
            patch("mapu.cli.asyncio") as mock_asyncio,
        ):
            main()
            mock_asyncio.run.assert_called_once()

    def test_corpus_create_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "corpus", "create", "TestCorpus"]),
            patch("mapu.cli.asyncio") as mock_asyncio,
        ):
            main()
            mock_asyncio.run.assert_called_once()

    def test_corpus_list_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "corpus", "list"]),
            patch("mapu.cli.asyncio") as mock_asyncio,
        ):
            main()
            mock_asyncio.run.assert_called_once()

    def test_entities_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "entities", cid, "Acme"]),
            patch("mapu.cli.asyncio") as mock_asyncio,
        ):
            main()
            mock_asyncio.run.assert_called_once()

    def test_gaps_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "gaps", cid]),
            patch("mapu.cli.asyncio") as mock_asyncio,
        ):
            main()
            mock_asyncio.run.assert_called_once()

    def test_activity_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "activity", cid]),
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

        args = _make_query_args()
        with (
            patch("mapu.cli._build_engine", return_value=(mock_engine, mock_factory)),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.providers.embeddings.get_default_embedding_provider"),
            patch("mapu.providers.llms.get_default_llm_provider"),
        ):
            await _run_query(args)

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

        args = _make_query_args()
        with (
            patch("mapu.cli._build_engine", return_value=(mock_engine, mock_factory)),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.providers.embeddings.get_default_embedding_provider"),
            patch("mapu.providers.llms.get_default_llm_provider"),
        ):
            await _run_query(args)

        captured = capsys.readouterr()
        assert "defines" in captured.out
        assert "missing data" in captured.out
