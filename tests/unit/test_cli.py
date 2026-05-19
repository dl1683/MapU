"""Unit tests for the MapU CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from mapu.cli import main


def _close_coro(coro: object) -> None:
    close = getattr(coro, "close", None)
    if close is not None:
        close()


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

    def test_doctor_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "doctor", "--json"]),
            patch("mapu.cli._run_doctor") as mock_doctor,
        ):
            main()
            mock_doctor.assert_called_once()
            assert mock_doctor.call_args.args[0].json_output is True

    def test_query_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "query", cid, "What is X?"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_ingest_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "ingest", cid, "test.txt"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_investigate_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "investigate", cid, "Why?"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_corpus_create_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "corpus", "create", "TestCorpus"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_corpus_list_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "corpus", "list"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_corpus_delete_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "corpus", "delete", cid, "--yes"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_corpus_reset_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "corpus", "reset", "--yes"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_entities_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "entities", cid, "Acme"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_gaps_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "gaps", cid]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_activity_dispatches(self) -> None:
        cid = "00000000-0000-0000-0000-000000000001"
        with (
            patch.object(sys, "argv", ["mapu", "activity", cid]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            (["query"], ["Examples:", "--json for automation", "next?"]),
            (["ingest"], ["Examples:", "--source-uri", "Query or resume"]),
            (["resume"], ["Examples:", "open_gaps", "priority_next_actions"]),
            (["activity"], ["Examples:", "--event-type query", "audit trail"]),
        ],
    )
    def test_core_command_help_documents_operator_workflow(
        self,
        command: list[str],
        expected: list[str],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with (
            patch.object(sys, "argv", ["mapu", *command, "--help"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        for text in expected:
            assert text in output

    def test_eval_dispatches(self) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "eval", "--domain", "code"]),
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_run.assert_called_once()

    def test_eval_benchmark_score_gate_dispatches(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "mapu",
                    "eval",
                    "benchmark-score-gate",
                    "--score",
                    "memoryarena=results/memoryarena_score.json:0.8",
                    "--allow-non-release-methods",
                ],
            ),
            patch("mapu.cli._run_benchmark_score_gate") as mock_gate,
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_gate.assert_called_once()
            assert mock_gate.call_args.args[0].allow_non_release_methods is True
            mock_run.assert_not_called()

    def test_eval_benchmark_score_inspect_dispatches(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "mapu",
                    "eval",
                    "benchmark-score-inspect",
                    "results/memoryarena_score.json",
                ],
            ),
            patch("mapu.cli._run_benchmark_score_inspect") as mock_inspect,
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_inspect.assert_called_once()
            mock_run.assert_not_called()

    def test_eval_memory_benchmark_smoke_dispatches(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "mapu",
                    "eval",
                    "memory-benchmark-smoke",
                    "--no-export",
                    "--verbose-steps",
                    "--allow-non-release-methods",
                ],
            ),
            patch("mapu.cli._run_memory_benchmark_smoke") as mock_smoke,
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_smoke.assert_called_once()
            assert mock_smoke.call_args.args[0].allow_non_release_methods is True
            mock_run.assert_not_called()

    def test_eval_memory_benchmark_smoke_help_documents_claim_boundary(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with (
            patch.object(sys, "argv", ["mapu", "eval", "memory-benchmark-smoke", "--help"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        output = capsys.readouterr().out
        assert "smoke_only=true" in output
        assert "public_performance_evidence=false" in output
        assert "--memoryarena-scenarios" in output
        assert "--min-token-f1" in output
        assert "--predictor web_grounded" in output
        assert "--allow-non-release-methods" in output

    def test_eval_memoryarena_dispatches(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                ["mapu", "eval", "memoryarena", "catalog"],
            ),
            patch("mapu.cli._run_memoryarena_eval") as mock_memoryarena,
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_memoryarena.assert_called_once()
            mock_run.assert_not_called()

    def test_eval_ama_bench_dispatches(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                ["mapu", "eval", "ama-bench", "catalog"],
            ),
            patch("mapu.cli._run_ama_bench_eval") as mock_ama,
            patch("mapu.cli.asyncio.run", side_effect=_close_coro) as mock_run,
        ):
            main()
            mock_ama.assert_called_once()
            mock_run.assert_not_called()


class TestRunServe:
    def test_run_serve_calls_uvicorn(self) -> None:
        with patch("uvicorn.run") as mock_uvicorn:
            from mapu.cli import _run_serve

            _run_serve("localhost", 5000)
            mock_uvicorn.assert_called_once_with(
                "mapu.api.app:app",
                host="localhost",
                port=5000,
            )


class TestRunMCP:
    def test_run_mcp_calls_server(self) -> None:
        with patch("mapu.mcp.server.run_mcp") as mock_run:
            from mapu.cli import _run_mcp

            _run_mcp()
            mock_run.assert_called_once()

    def test_run_doctor_prints_installed_tool_surface(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from mapu.cli import _run_doctor
        from mapu.mcp.server import REQUIRED_MCP_TOOLS

        _run_doctor(argparse.Namespace(json_output=True))

        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "ok"
        assert payload["mcp"]["tool_count"] >= len(REQUIRED_MCP_TOOLS)
        assert payload["mcp"]["required_tools_present"] is True
        assert payload["mcp"]["missing_required_tools"] == []
        assert "not DB workflow" in payload["claim_boundary"]


class TestBenchmarkScoreGateCLI:
    def test_run_benchmark_score_gate_prints_summary(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from mapu.cli import _run_benchmark_score_gate
        from mapu.evaluation import benchmark_score_gate

        def fake_run_gate(
            specs,
            out,
            *,
            require_clean_git=False,
            allow_non_release_methods=False,
            allow_diagnostic_methods=False,
        ):
            assert specs == [
                benchmark_score_gate.ScoreSpec(
                    benchmark="memoryarena",
                    path=tmp_path / "score.json",
                    min_exact_match=0.9,
                )
            ]
            assert out == tmp_path / "gate.json"
            assert require_clean_git is True
            assert allow_non_release_methods is True
            assert allow_diagnostic_methods is False
            return 0, {"status": "ok", "scores": [{"benchmark": "memoryarena", "passed": True}]}

        monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
        monkeypatch.setattr(benchmark_score_gate, "run_gate", fake_run_gate)

        _run_benchmark_score_gate(
            argparse.Namespace(
                score=[f"memoryarena={tmp_path / 'score.json'}:0.9"],
                out=str(tmp_path / "gate.json"),
                require_clean_git=True,
                allow_non_release_methods=False,
                allow_diagnostic_methods=True,
            )
        )

        summary = json.loads(capsys.readouterr().out)
        assert summary == {
            "status": "ok",
            "path": str((tmp_path / "gate.json").resolve()),
            "benchmarks": 1,
            "failed": [],
            "failure_details": [],
        }

    def test_run_benchmark_score_gate_exits_nonzero_on_failure(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from mapu.cli import _run_benchmark_score_gate
        from mapu.evaluation import benchmark_score_gate

        monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
        monkeypatch.setattr(
            benchmark_score_gate,
            "run_gate",
            lambda specs,
            out,
            *,
            require_clean_git=False,
            allow_non_release_methods=False,
            allow_diagnostic_methods=False: (
                1,
                {
                    "status": "fail",
                    "scores": [
                        {
                            "benchmark": "ama_bench",
                            "metric": "token_f1",
                            "metric_value": 0.4,
                            "threshold": 0.8,
                            "passed": False,
                            "failure_reason": "token_f1 below threshold",
                        }
                    ],
                },
            ),
        )

        with pytest.raises(SystemExit) as exc_info:
            _run_benchmark_score_gate(
                argparse.Namespace(
                    score=["ama_bench=results/ama_score.json:0.8"],
                    out=str(tmp_path / "gate.json"),
                    require_clean_git=False,
                    allow_non_release_methods=False,
                    allow_diagnostic_methods=False,
                )
            )

        assert exc_info.value.code == 1
        summary = json.loads(capsys.readouterr().out)
        assert summary["failed"] == ["ama_bench"]
        assert summary["failure_details"] == [
            {
                "benchmark": "ama_bench",
                "metric": "token_f1",
                "metric_value": 0.4,
                "threshold": 0.8,
                "failure_reason": "token_f1 below threshold",
            }
        ]


class TestBenchmarkScoreInspectCLI:
    def test_run_benchmark_score_inspect_prints_worst_items(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path,
    ) -> None:
        from mapu.cli import _run_benchmark_score_inspect

        score = tmp_path / "score.json"
        score.write_text(
            json.dumps(
                {
                    "status": "ok",
                    "evaluated": 2,
                    "exact_match": 0.0,
                    "token_f1": 0.25,
                    "method_counts": {"mapu_benchmark_agnostic_memoryarena_v1": 2},
                    "by_config": {
                        "progressive_search": {"evaluated": 1, "token_f1": 0.0}
                    },
                    "worst_items": [
                        {"scenario_id": "a", "token_f1": 0.0},
                        {"scenario_id": "b", "token_f1": 0.5},
                    ],
                }
            ),
            encoding="utf-8",
        )

        _run_benchmark_score_inspect(argparse.Namespace(score=str(score), top=1))

        summary = json.loads(capsys.readouterr().out)
        assert summary["status"] == "ok"
        assert summary["token_f1"] == 0.25
        assert summary["method_counts"] == {"mapu_benchmark_agnostic_memoryarena_v1": 2}
        assert summary["by_config"]["progressive_search"]["token_f1"] == 0.0
        assert summary["worst_items"] == [{"scenario_id": "a", "token_f1": 0.0}]

    def test_run_benchmark_score_inspect_sorts_item_scores_fallback(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path,
    ) -> None:
        from mapu.cli import _run_benchmark_score_inspect

        score = tmp_path / "score.json"
        score.write_text(
            json.dumps(
                {
                    "status": "ok",
                    "evaluated": 2,
                    "item_scores": [
                        {"scenario_id": "b", "token_f1": 0.5},
                        {"scenario_id": "a", "token_f1": 0.0},
                    ],
                }
            ),
            encoding="utf-8",
        )

        _run_benchmark_score_inspect(argparse.Namespace(score=str(score), top=2))

        summary = json.loads(capsys.readouterr().out)
        assert [item["scenario_id"] for item in summary["worst_items"]] == ["a", "b"]

    def test_run_benchmark_score_inspect_rejects_missing_file(self, tmp_path) -> None:
        from mapu.cli import _run_benchmark_score_inspect

        with pytest.raises(SystemExit) as exc_info:
            _run_benchmark_score_inspect(
                argparse.Namespace(score=str(tmp_path / "missing.json"), top=1)
            )

        assert exc_info.value.code == 2

    def test_run_benchmark_score_inspect_rejects_invalid_json(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path,
    ) -> None:
        from mapu.cli import _run_benchmark_score_inspect

        score = tmp_path / "bad_score.json"
        score.write_text("{bad json", encoding="utf-8-sig")

        with pytest.raises(SystemExit) as exc_info:
            _run_benchmark_score_inspect(argparse.Namespace(score=str(score), top=1))

        assert exc_info.value.code == 2
        assert "invalid JSON" in capsys.readouterr().err

    def test_run_benchmark_score_inspect_rejects_non_object_json(
        self,
        capsys: pytest.CaptureFixture[str],
        tmp_path,
    ) -> None:
        from mapu.cli import _run_benchmark_score_inspect

        score = tmp_path / "bad_score.json"
        score.write_text("[]", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            _run_benchmark_score_inspect(argparse.Namespace(score=str(score), top=1))

        assert exc_info.value.code == 2
        assert "must be a JSON object" in capsys.readouterr().err


class TestMemoryBenchmarkSmokeCLI:
    def test_run_memory_benchmark_smoke_prints_summary(
        self,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        from mapu.cli import _run_memory_benchmark_smoke
        from mapu.evaluation import memory_benchmark_smoke

        def fake_run_smoke(**kwargs):
            assert kwargs["output_dir"] == tmp_path
            assert kwargs["export"] is False
            assert kwargs["predictor"] == "benchmark_agnostic"
            assert kwargs["min_token_f1"] == 0.7
            assert kwargs["verbose_steps"] is True
            return (
                0,
                {
                    "status": "ok",
                    "paths": {"report": str(tmp_path / "smoke_report.json")},
                    "gate": {"status": "ok", "scores": []},
                    "score_summary": [
                        {
                            "benchmark": "memoryarena",
                            "metric": "token_f1",
                            "metric_value": 0.7,
                            "threshold": 0.65,
                            "passed": True,
                        }
                    ],
                    "smoke_only": True,
                    "public_performance_evidence": False,
                },
            )

        monkeypatch.setattr(memory_benchmark_smoke, "run_smoke", fake_run_smoke)

        _run_memory_benchmark_smoke(
            argparse.Namespace(
                out_dir=str(tmp_path),
                no_export=True,
                memoryarena_scenarios=None,
                ama_scenarios=None,
                memoryarena_limit_per_config=1,
                ama_limit=1,
                predictor="benchmark_agnostic",
                min_token_f1=0.7,
                allow_non_release_methods=False,
                allow_diagnostic_methods=False,
                verbose_steps=True,
            )
        )

        assert json.loads(capsys.readouterr().out) == {
            "status": "ok",
            "path": str(tmp_path / "smoke_report.json"),
            "gate_status": "ok",
            "failed": [],
            "score_summary": [
                {
                    "benchmark": "memoryarena",
                    "metric": "token_f1",
                    "metric_value": 0.7,
                    "threshold": 0.65,
                    "passed": True,
                }
            ],
            "smoke_only": True,
            "public_performance_evidence": False,
        }


class TestMemoryBenchmarkCLIs:
    def test_run_memoryarena_score_exits_on_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from mapu.cli import _run_memoryarena_eval
        from mapu.evaluation import memoryarena

        monkeypatch.setattr(memoryarena, "score", lambda *args: 1)

        with pytest.raises(SystemExit) as exc_info:
            _run_memoryarena_eval(
                argparse.Namespace(
                    memoryarena_action="score",
                    scenarios="scenarios.jsonl",
                    predictions="predictions.jsonl",
                    out="score.json",
                    min_exact_match=0.8,
                )
            )

        assert exc_info.value.code == 1

    def test_run_ama_bench_score_passes_arguments(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from mapu.cli import _run_ama_bench_eval
        from mapu.evaluation import ama_bench

        calls = []

        def fake_score(scenarios, predictions, out, min_exact_match):
            calls.append((scenarios, predictions, out, min_exact_match))
            return 0

        monkeypatch.setattr(ama_bench, "score", fake_score)

        _run_ama_bench_eval(
            argparse.Namespace(
                ama_bench_action="score",
                scenarios="scenarios.jsonl",
                predictions="predictions.jsonl",
                out="score.json",
                min_exact_match=0.9,
            )
        )

        assert calls == [("scenarios.jsonl", "predictions.jsonl", "score.json", 0.9)]

    def test_run_memoryarena_predict_passes_arguments(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from mapu.cli import _run_memoryarena_eval
        from mapu.evaluation import memoryarena

        calls = []

        def fake_predict(scenarios, out, *, max_scenarios, predictor):
            calls.append((scenarios, out, max_scenarios, predictor))
            return 0

        monkeypatch.setattr(memoryarena, "predict", fake_predict)

        _run_memoryarena_eval(
            argparse.Namespace(
                memoryarena_action="predict",
                scenarios="scenarios.jsonl",
                out="predictions.jsonl",
                max_scenarios=2,
                predictor="benchmark_agnostic",
            )
        )

        assert calls == [("scenarios.jsonl", "predictions.jsonl", 2, "benchmark_agnostic")]

    def test_run_ama_bench_predict_passes_arguments(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from mapu.cli import _run_ama_bench_eval
        from mapu.evaluation import ama_bench

        calls = []

        def fake_predict(scenarios, out, *, max_scenarios, predictor):
            calls.append((scenarios, out, max_scenarios, predictor))
            return 0

        monkeypatch.setattr(ama_bench, "predict", fake_predict)

        _run_ama_bench_eval(
            argparse.Namespace(
                ama_bench_action="predict",
                scenarios="scenarios.jsonl",
                out="predictions.jsonl",
                max_scenarios=3,
                predictor="benchmark_agnostic",
            )
        )

        assert calls == [("scenarios.jsonl", "predictions.jsonl", 3, "benchmark_agnostic")]


class TestCorpusDestructiveGuards:
    @pytest.mark.asyncio
    async def test_run_corpus_delete_requires_yes(self, capsys: pytest.CaptureFixture[str]) -> None:
        from mapu.cli import _run_corpus_delete

        args = argparse.Namespace(
            corpus_id="00000000-0000-0000-0000-000000000001",
            yes=False,
        )

        with (
            patch("mapu.cli._build_engine") as mock_build_engine,
            pytest.raises(SystemExit) as exc_info,
        ):
            await _run_corpus_delete(args)

        assert exc_info.value.code == 2
        assert "Refusing delete without --yes flag." in capsys.readouterr().err
        mock_build_engine.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_corpus_reset_requires_yes(self, capsys: pytest.CaptureFixture[str]) -> None:
        from mapu.cli import _run_corpus_reset

        args = argparse.Namespace(yes=False)

        with (
            patch("mapu.cli._build_engine") as mock_build_engine,
            pytest.raises(SystemExit) as exc_info,
        ):
            await _run_corpus_reset(args)

        assert exc_info.value.code == 2
        assert "Refusing reset without --yes flag." in capsys.readouterr().err
        mock_build_engine.assert_not_called()


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
        self,
        capsys: pytest.CaptureFixture[str],
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

    @pytest.mark.asyncio
    async def test_run_query_json_includes_answer_alias_and_chunk_hits(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from mapu.cli import _run_query

        chunk_id = uuid.uuid4()
        expression_id = uuid.uuid4()
        mock_result = SimpleNamespace(
            intent=SimpleNamespace(value="identity"),
            tier_used=SimpleNamespace(name="STRUCTURED"),
            epistemic_status=SimpleNamespace(value="insufficient"),
            synthesis="Maya Chen owns Project Atlas.",
            hits=[],
            chunk_hits=[
                SimpleNamespace(
                    chunk_id=chunk_id,
                    text="The current owner is Maya Chen.",
                    score=0.92,
                    expression_id=expression_id,
                )
            ],
            gaps=[],
            metadata={"entities": ("Project Atlas",)},
            next_steps=("Inspect source chunk.",),
            structured_next_steps=[],
        )

        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=object())
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = lambda: mock_session  # noqa: E731
        mock_engine = AsyncMock()

        with (
            patch("mapu.cli._build_engine", return_value=(mock_engine, mock_factory)),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.providers.embeddings.get_default_embedding_provider"),
            patch("mapu.providers.llms.get_default_llm_provider"),
        ):
            await _run_query(_make_query_args(json_output=True))

        payload = json.loads(capsys.readouterr().out)
        assert payload["answer"] == "Maya Chen owns Project Atlas."
        assert payload["synthesis"] == payload["answer"]
        assert payload["chunk_hits"][0]["chunk_id"] == str(chunk_id)
        assert payload["chunk_hits"][0]["text"] == "The current owner is Maya Chen."


class TestRunResume:
    @pytest.mark.asyncio
    async def test_run_resume_prints_json_handoff_bundle(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from mapu.cli import _run_resume

        gap = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000111",
            kind="knowledge",
            description="Need source coverage",
            severity="critical",
            status="open",
            detected_by="query",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            resolved_at=None,
        )

        activity = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000222",
            event_type="query",
            actor="agent",
            entity_type="document",
            entity_id="00000000-0000-0000-0000-000000000333",
            details={},
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )

        mock_gap_repo = SimpleNamespace(list=AsyncMock(return_value=[gap]))
        mock_activity_repo = SimpleNamespace(list=AsyncMock(return_value=[activity]))

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = lambda: session  # noqa: E731
        mock_engine = AsyncMock()

        args = argparse.Namespace(
            corpus_id="00000000-0000-0000-0000-000000000999",
            max_gaps=10,
            max_activity=20,
            max_actions=10,
            json_output=True,
        )

        with (
            patch("mapu.cli._build_engine", return_value=(mock_engine, mock_factory)),
            patch("mapu.repos.gap.GapRepo", return_value=mock_gap_repo),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_activity_repo),
        ):
            await _run_resume(args)

        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["protocol_version"] == "1.1.0"
        assert parsed["protocol"] == "mapu-resume-handoff"
        assert len(parsed["open_gaps"]) == 1
        assert parsed["continuity_frontier"]["open_gap_count"] == 1
        assert parsed["priority_next_actions"]
        assert parsed["continuity_governance"]

    @pytest.mark.asyncio
    async def test_run_resume_prints_human_readable_summary(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from mapu.cli import _run_resume

        gap = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000111",
            kind="knowledge",
            description="Need source coverage",
            severity="moderate",
            status="open",
            detected_by="query",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            resolved_at=None,
        )

        mock_gap_repo = SimpleNamespace(list=AsyncMock(return_value=[gap]))
        mock_activity_repo = SimpleNamespace(list=AsyncMock(return_value=[]))

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = lambda: session  # noqa: E731
        mock_engine = AsyncMock()

        args = argparse.Namespace(
            corpus_id="00000000-0000-0000-0000-000000000999",
            max_gaps=5,
            max_activity=10,
            max_actions=10,
            json_output=False,
        )

        with (
            patch("mapu.cli._build_engine", return_value=(mock_engine, mock_factory)),
            patch("mapu.repos.gap.GapRepo", return_value=mock_gap_repo),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_activity_repo),
        ):
            await _run_resume(args)

        captured = capsys.readouterr()
        assert "Resume handoff for corpus" in captured.out
        assert "Priority next actions for Claude/code agents:" in captured.out

    @pytest.mark.asyncio
    async def test_run_resume_clamps_max_actions_for_handoff_bundle(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from mapu.cli import _run_resume

        gap = SimpleNamespace(
            id="00000000-0000-0000-0000-000000000111",
            kind="knowledge",
            description="Need source coverage",
            severity="critical",
            status="open",
            detected_by="query",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            resolved_at=None,
        )

        mock_gap_repo = SimpleNamespace(list=AsyncMock(return_value=[gap]))
        mock_activity_repo = SimpleNamespace(list=AsyncMock(return_value=[]))

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        mock_engine = AsyncMock()
        mock_factory = lambda: session  # noqa: E731

        async_bundle: dict = {
            "protocol_version": "1.1.0",
            "protocol": "mapu-resume-handoff",
            "generated_at": "2026-01-01T00:00:00",
            "continuity_role": "claude-style handoff",
            "corpus_id": "00000000-0000-0000-0000-000000000999",
            "open_gaps": [],
            "recent_activity": [],
            "continuity_frontier": {"open_gap_count": 0, "unresolved_conflict_count": 0},
            "continuity_governance": {
                "guaranteed_fields": ["protocol_version", "protocol"],
                "provisional_fields": ["query(corpus_id='...')"],
                "stale_fields": [],
            },
            "priority_next_actions": [
                {
                    "action_type": "query",
                    "step": "query(...)",
                    "rationale": "fallback",
                    "target": {},
                    "expected_signal_target": {},
                    "uncertainty_reason": "no_open_gaps",
                    "gap_ids": [],
                    "activity_ids": [],
                    "confidence": 0.1,
                }
            ],
        }

        args = argparse.Namespace(
            corpus_id="00000000-0000-0000-0000-000000000999",
            max_gaps=5,
            max_activity=10,
            max_actions=999,
            json_output=False,
        )

        with (
            patch("mapu.cli._build_engine", return_value=(mock_engine, mock_factory)),
            patch(
                "mapu.context_learning.build_handoff_bundle", return_value=async_bundle
            ) as mock_build_bundle,
            patch("mapu.repos.gap.GapRepo", return_value=mock_gap_repo),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_activity_repo),
        ):
            await _run_resume(args)

        captured = capsys.readouterr()
        assert "Resume handoff for corpus" in captured.out
        kwargs = mock_build_bundle.call_args[1]
        assert kwargs["max_actions"] == 30
        assert kwargs["max_gaps"] == 5
        assert kwargs["max_activity"] == 10


class TestAgentSurfaceDurability:
    @pytest.mark.asyncio
    async def test_run_query_commits_learned_gaps_and_activity(self) -> None:
        from types import SimpleNamespace

        from mapu.cli import _run_query

        mock_result = SimpleNamespace(
            intent=SimpleNamespace(value="identity"),
            tier_used=SimpleNamespace(name="DIRECT"),
            epistemic_status=SimpleNamespace(value="sufficient"),
            synthesis="Answer text",
            hits=[],
            gaps=[],
            metadata={},
            next_steps=[],
            structured_next_steps=[],
        )

        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=object())
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = lambda: mock_session  # noqa: E731
        mock_engine = AsyncMock()

        with (
            patch("mapu.cli._build_engine", return_value=(mock_engine, mock_factory)),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.providers.embeddings.get_default_embedding_provider"),
            patch("mapu.providers.llms.get_default_llm_provider"),
        ):
            await _run_query(_make_query_args())

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_resume_rejects_missing_corpus(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from mapu.cli import _run_resume

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = lambda: mock_session  # noqa: E731
        mock_engine = AsyncMock()

        args = argparse.Namespace(
            corpus_id="00000000-0000-0000-0000-000000000999",
            max_gaps=5,
            max_activity=10,
            max_actions=10,
            json_output=True,
        )

        with (
            patch("mapu.cli._build_engine", return_value=(mock_engine, mock_factory)),
            pytest.raises(SystemExit) as exc_info,
        ):
            await _run_resume(args)

        assert exc_info.value.code == 1
        assert "Corpus not found" in capsys.readouterr().err
