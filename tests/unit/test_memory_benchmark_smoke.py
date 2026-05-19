"""Unit tests for the one-command memory benchmark smoke workflow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mapu.evaluation import memory_benchmark_smoke
from mapu.evaluation.benchmark_score_gate import ScoreSpec


def test_memory_benchmark_smoke_orchestrates_honest_default_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def fake_export(name: str):
        def _inner(*args, **kwargs):
            print(f"{name} stdout")
            calls.append((name, args, kwargs))
            Path(str(args[0])).write_text("{}\n", encoding="utf-8")
            return 0

        return _inner

    def fake_predict(name: str):
        def _inner(*args, **kwargs):
            print(f"{name} stdout")
            calls.append((name, args, kwargs))
            Path(str(args[1])).write_text("{}\n", encoding="utf-8")
            return 0

        return _inner

    def fake_score(name: str):
        def _inner(*args, **kwargs):
            print(f"{name} stdout")
            calls.append((name, args, kwargs))
            Path(str(args[2])).write_text('{"status":"ok"}', encoding="utf-8")
            return 0

        return _inner

    def fake_gate(
        specs: list[ScoreSpec],
        out: Path,
        *,
        allow_non_release_methods: bool = False,
        allow_diagnostic_methods: bool = False,
    ):
        calls.append(
            (
                "gate",
                (specs, out),
                {
                    "allow_non_release_methods": allow_non_release_methods,
                    "allow_diagnostic_methods": allow_diagnostic_methods,
                },
            )
        )
        out.write_text('{"status":"fail"}', encoding="utf-8")
        return (
            1,
            {
                "status": "fail",
                "scores": [
                    {
                        "benchmark": "memoryarena",
                        "metric": "token_f1",
                        "metric_value": 0.4,
                        "threshold": 0.65,
                        "threshold_metric": "token_f1",
                        "min_exact_match": 0.65,
                        "passed": False,
                        "failure_reason": "below threshold",
                    },
                    {
                        "benchmark": "ama_bench",
                        "metric": "token_f1",
                        "metric_value": 0.3,
                        "threshold": 0.65,
                        "threshold_metric": "token_f1",
                        "min_exact_match": 0.65,
                        "passed": False,
                        "failure_reason": "below threshold",
                    },
                ],
            },
        )

    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "export", fake_export("memory_export"))
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "export", fake_export("ama_export"))
    monkeypatch.setattr(
        memory_benchmark_smoke.memoryarena,
        "predict",
        fake_predict("memory_predict"),
    )
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "predict", fake_predict("ama_predict"))
    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "score", fake_score("memory_score"))
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "score", fake_score("ama_score"))
    monkeypatch.setattr(memory_benchmark_smoke, "run_gate", fake_gate)

    rc, report = memory_benchmark_smoke.run_smoke(output_dir=tmp_path)

    assert rc == 1
    assert report["status"] == "fail"
    assert report["smoke_only"] is True
    assert report["public_performance_evidence"] is False
    assert "not leaderboard" in report["evidence_note"]
    assert report["predictor"] == "benchmark_agnostic"
    assert report["inputs"] == {
        "exported_scenarios": True,
        "memoryarena_scenarios": str(tmp_path / "memoryarena_scenarios.jsonl"),
        "ama_scenarios": str(tmp_path / "ama_scenarios.jsonl"),
        "memoryarena_limit_per_config": 1,
        "ama_limit": 1,
    }
    assert report["paths"]["report"] == str(tmp_path / "smoke_report.json")
    assert report["score_summary"][0] == {
        "benchmark": "memoryarena",
        "metric": "token_f1",
        "metric_value": 0.4,
        "threshold": 0.65,
        "threshold_metric": "token_f1",
        "passed": False,
        "failure_reason": "below threshold",
    }
    assert capsys.readouterr().out == ""
    assert report["steps"]["memoryarena_export"]["stdout"] == "memory_export stdout\n"
    assert report["steps"]["ama_bench_score"]["stdout"] == "ama_score stdout\n"
    assert report["score_exit_codes"]["memoryarena_predict"] == 0
    assert (tmp_path / "smoke_report.json").exists()
    assert ("memory_export", (str(tmp_path / "memoryarena_scenarios.jsonl"), 1), {}) in calls
    assert ("ama_export", (str(tmp_path / "ama_scenarios.jsonl"), 1), {}) in calls
    assert (
        "memory_predict",
        (
            str(tmp_path / "memoryarena_scenarios.jsonl"),
            str(tmp_path / "memoryarena_predictions.jsonl"),
        ),
        {"predictor": "benchmark_agnostic"},
    ) in calls
    assert (
        "ama_predict",
        (str(tmp_path / "ama_scenarios.jsonl"), str(tmp_path / "ama_predictions.jsonl")),
        {"predictor": "benchmark_agnostic"},
    ) in calls


def test_memory_benchmark_smoke_verbose_steps_prints_inner_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_export(out: str, *_args, **_kwargs):
        print("export stdout")
        Path(out).write_text("{}\n", encoding="utf-8")
        return 0

    def fake_predict(_scenarios: str, out: str, **_kwargs):
        print("predict stdout")
        Path(out).write_text("{}\n", encoding="utf-8")
        return 0

    def fake_score(_scenarios: str, _predictions: str, out: str, *_args, **_kwargs):
        print("score stdout")
        Path(out).write_text('{"status":"ok"}', encoding="utf-8")
        return 0

    def fake_gate(*_args, **_kwargs):
        return 0, {"status": "ok", "scores": []}

    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "export", fake_export)
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "export", fake_export)
    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "predict", fake_predict)
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "predict", fake_predict)
    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "score", fake_score)
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "score", fake_score)
    monkeypatch.setattr(memory_benchmark_smoke, "run_gate", fake_gate)

    rc, report = memory_benchmark_smoke.run_smoke(
        output_dir=tmp_path,
        verbose_steps=True,
    )

    assert rc == 0
    assert "export stdout" in capsys.readouterr().out
    assert report["steps"]["memoryarena_export"]["stdout"] == ""


def test_memory_benchmark_smoke_records_external_input_paths_when_no_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memoryarena_scenarios = tmp_path / "external_memoryarena.jsonl"
    ama_scenarios = tmp_path / "external_ama.jsonl"
    memoryarena_scenarios.write_text("{}\n", encoding="utf-8")
    ama_scenarios.write_text("{}\n", encoding="utf-8")

    def fake_predict(_scenarios: str, out: str, **_kwargs):
        Path(out).write_text("{}\n", encoding="utf-8")
        return 0

    def fake_score(_scenarios: str, _predictions: str, out: str, *_args, **_kwargs):
        Path(out).write_text('{"status":"ok"}', encoding="utf-8")
        return 0

    def fake_gate(*_args, **_kwargs):
        return (
            0,
            {
                "status": "ok",
                "scores": [
                    {
                        "benchmark": "memoryarena",
                        "metric": "token_f1",
                        "metric_value": 1.0,
                        "threshold": 0.65,
                        "threshold_metric": "token_f1",
                        "min_exact_match": 0.65,
                        "passed": True,
                        "failure_reason": None,
                    }
                ],
            },
        )

    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "predict", fake_predict)
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "predict", fake_predict)
    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "score", fake_score)
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "score", fake_score)
    monkeypatch.setattr(memory_benchmark_smoke, "run_gate", fake_gate)

    rc, report = memory_benchmark_smoke.run_smoke(
        output_dir=tmp_path / "out",
        export=False,
        memoryarena_scenarios=memoryarena_scenarios,
        ama_scenarios=ama_scenarios,
    )

    assert rc == 0
    assert report["inputs"]["exported_scenarios"] is False
    assert report["inputs"]["memoryarena_scenarios"] == str(memoryarena_scenarios)
    assert report["inputs"]["ama_scenarios"] == str(ama_scenarios)
    assert report["paths"]["memoryarena_scenarios"] == str(
        tmp_path / "out" / "memoryarena_scenarios.jsonl"
    )


def test_memory_benchmark_smoke_reuses_out_dir_scenarios_when_no_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "memoryarena_scenarios.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "ama_scenarios.jsonl").write_text("{}\n", encoding="utf-8")

    def fake_predict(_scenarios: str, out: str, **_kwargs):
        Path(out).write_text("{}\n", encoding="utf-8")
        return 0

    def fake_score(_scenarios: str, _predictions: str, out: str, *_args, **_kwargs):
        Path(out).write_text('{"status":"ok"}', encoding="utf-8")
        return 0

    def fake_gate(*_args, **_kwargs):
        return 0, {"status": "ok", "scores": []}

    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "predict", fake_predict)
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "predict", fake_predict)
    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "score", fake_score)
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "score", fake_score)
    monkeypatch.setattr(memory_benchmark_smoke, "run_gate", fake_gate)

    rc, report = memory_benchmark_smoke.run_smoke(output_dir=tmp_path, export=False)

    assert rc == 0
    assert report["inputs"]["exported_scenarios"] is False
    assert report["inputs"]["memoryarena_scenarios"] == str(
        tmp_path / "memoryarena_scenarios.jsonl"
    )
    assert report["inputs"]["ama_scenarios"] == str(tmp_path / "ama_scenarios.jsonl")


def test_memory_benchmark_smoke_reports_missing_default_scenarios_when_no_export(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        memory_benchmark_smoke.run_smoke(output_dir=tmp_path, export=False)

    assert "MemoryArena scenario file does not exist" in str(exc_info.value)


def test_memory_benchmark_smoke_reports_missing_memoryarena_scenario_file(
    tmp_path: Path,
) -> None:
    ama = tmp_path / "ama.jsonl"
    ama.write_text("{}\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        memory_benchmark_smoke.run_smoke(
            output_dir=tmp_path,
            export=False,
            memoryarena_scenarios=tmp_path / "missing_memoryarena.jsonl",
            ama_scenarios=ama,
        )

    assert "MemoryArena scenario file does not exist" in str(exc_info.value)


def test_memory_benchmark_smoke_reports_missing_ama_scenario_file(
    tmp_path: Path,
) -> None:
    memoryarena = tmp_path / "memoryarena.jsonl"
    memoryarena.write_text("{}\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        memory_benchmark_smoke.run_smoke(
            output_dir=tmp_path,
            export=False,
            memoryarena_scenarios=memoryarena,
            ama_scenarios=tmp_path / "missing_ama.jsonl",
        )

    assert "AMA-Bench scenario file does not exist" in str(exc_info.value)


def test_memory_benchmark_smoke_rejects_invalid_token_f1_threshold(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        memory_benchmark_smoke.run_smoke(output_dir=tmp_path, min_token_f1=1.5)

    assert "--min-token-f1" in str(exc_info.value)


def test_memory_benchmark_smoke_requires_explicit_debug_flag_for_non_release_predictors(
    tmp_path: Path,
) -> None:
    for predictor in ("diagnostic_templates", "web_grounded"):
        with pytest.raises(SystemExit) as exc_info:
            memory_benchmark_smoke.run_smoke(
                output_dir=tmp_path / predictor,
                predictor=predictor,
            )

        message = str(exc_info.value)
        assert "--allow-non-release-methods" in message
        assert "--allow-diagnostic-methods" in message


def test_memory_benchmark_smoke_allows_web_grounded_with_debug_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    (tmp_path / "memoryarena_scenarios.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "ama_scenarios.jsonl").write_text("{}\n", encoding="utf-8")

    def fake_predict(name: str):
        def inner(*args, **kwargs):
            calls.append((name, kwargs))
            Path(args[1]).write_text("{}\n", encoding="utf-8")
            return 0

        return inner

    def fake_score(*args, **kwargs):
        Path(args[2]).write_text(
            json.dumps(
                {
                    "status": "ok",
                    "benchmark": "memoryarena",
                    "exact_match": 0.0,
                    "token_f1": 1.0,
                    "method_counts": {},
                }
            ),
            encoding="utf-8",
        )
        return 0

    def fake_gate(
        specs,
        out,
        *,
        allow_non_release_methods=False,
        allow_diagnostic_methods=False,
        require_clean_git=False,
    ):
        assert allow_non_release_methods is True
        assert allow_diagnostic_methods is False
        return (
            0,
            {
                "status": "ok",
                "scores": [
                    {
                        "benchmark": spec.benchmark,
                        "metric": spec.metric,
                        "metric_value": 1.0,
                        "min_exact_match": spec.min_exact_match,
                        "passed": True,
                    }
                    for spec in specs
                ],
            },
        )

    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "predict", fake_predict("memory"))
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "predict", fake_predict("ama"))
    monkeypatch.setattr(memory_benchmark_smoke.memoryarena, "score", fake_score)
    monkeypatch.setattr(memory_benchmark_smoke.ama_bench, "score", fake_score)
    monkeypatch.setattr(memory_benchmark_smoke, "run_gate", fake_gate)

    rc, report = memory_benchmark_smoke.run_smoke(
        output_dir=tmp_path,
        export=False,
        predictor="web_grounded",
        allow_diagnostic_methods=True,
    )

    assert rc == 0
    assert report["predictor"] == "web_grounded"
    assert report["allow_diagnostic_methods"] is True
    assert report["allow_non_release_methods"] is True
    assert calls == [
        ("memory", {"predictor": "web_grounded"}),
        ("ama", {"predictor": "benchmark_agnostic"}),
    ]
