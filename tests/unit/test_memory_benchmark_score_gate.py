"""Unit tests for aggregate memory benchmark score gate."""

from __future__ import annotations

import json
from pathlib import Path

from mapu.evaluation import benchmark_score_gate


def _score_file(
    path: Path,
    *,
    status: str = "ok",
    evaluated: int = 10,
    correct: int = 9,
    exact_match: float = 0.9,
    method_counts: dict[str, int] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "status": status,
                "evaluated": evaluated,
                "correct": correct,
                "exact_match": exact_match,
                "method_counts": method_counts or {},
            }
        ),
        encoding="utf-8",
    )


def test_parse_score_spec() -> None:
    spec = benchmark_score_gate.parse_score_spec(
        "memoryarena=results/memoryarena_score.json:0.80"
    )

    assert spec.benchmark == "memoryarena"
    assert spec.path == Path("results/memoryarena_score.json")
    assert spec.min_exact_match == 0.8
    assert spec.metric == "exact_match"


def test_parse_score_spec_with_metric() -> None:
    spec = benchmark_score_gate.parse_score_spec(
        "ama_bench=results/ama_score.json:token_f1:0.65"
    )

    assert spec.benchmark == "ama_bench"
    assert spec.path == Path("results/ama_score.json")
    assert spec.metric == "token_f1"
    assert spec.min_exact_match == 0.65


def test_run_gate_passes_when_all_scores_meet_threshold(
    tmp_path: Path,
    monkeypatch,
) -> None:
    score_path = tmp_path / "memoryarena_score.json"
    out_path = tmp_path / "gate.json"
    _score_file(score_path, exact_match=0.9)
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="memoryarena",
                path=score_path,
                min_exact_match=0.8,
            )
        ],
        out_path,
    )

    assert rc == 0
    assert report["status"] == "ok"
    assert report["scores"][0]["passed"] is True
    assert json.loads(out_path.read_text(encoding="utf-8"))["status"] == "ok"


def test_run_gate_fails_missing_score_file(tmp_path: Path, monkeypatch) -> None:
    out_path = tmp_path / "gate.json"
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="ama_bench",
                path=Path("missing.json"),
                min_exact_match=0.8,
            )
        ],
        out_path,
    )

    assert rc == 1
    assert report["status"] == "fail"
    assert report["scores"][0]["status"] == "missing_or_invalid"


def test_run_gate_fails_below_threshold(tmp_path: Path, monkeypatch) -> None:
    score_path = tmp_path / "ama_score.json"
    out_path = tmp_path / "gate.json"
    _score_file(score_path, exact_match=0.75)
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="ama_bench",
                path=score_path,
                min_exact_match=0.8,
            )
        ],
        out_path,
    )

    assert rc == 1
    assert report["scores"][0]["passed"] is False
    assert "below" in str(report["scores"][0]["failure_reason"])


def test_run_gate_can_threshold_non_exact_metric(tmp_path: Path, monkeypatch) -> None:
    score_path = tmp_path / "ama_score.json"
    out_path = tmp_path / "gate.json"
    _score_file(score_path, exact_match=0.0)
    score = json.loads(score_path.read_text(encoding="utf-8"))
    score["token_f1"] = 0.72
    score_path.write_text(json.dumps(score), encoding="utf-8")
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="ama_bench",
                path=score_path,
                min_exact_match=0.7,
                metric="token_f1",
            )
        ],
        out_path,
    )

    assert rc == 0
    assert report["scores"][0]["metric"] == "token_f1"
    assert report["scores"][0]["metric_value"] == 0.72
    assert report["scores"][0]["threshold_metric"] == "token_f1"
    assert report["scores"][0]["threshold"] == 0.7
    assert report["scores"][0]["min_exact_match"] == 0.7


def test_run_gate_missing_score_uses_metric_neutral_threshold_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_path = tmp_path / "gate.json"
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="ama_bench",
                path=Path("missing.json"),
                min_exact_match=0.65,
                metric="token_f1",
            )
        ],
        out_path,
    )

    assert rc == 1
    assert report["scores"][0]["threshold_metric"] == "token_f1"
    assert report["scores"][0]["threshold"] == 0.65


def test_run_gate_rejects_diagnostic_prediction_methods_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    score_path = tmp_path / "memoryarena_score.json"
    out_path = tmp_path / "gate.json"
    _score_file(
        score_path,
        exact_match=1.0,
        method_counts={"mapu_diagnostic_templates_memoryarena_v1": 10},
    )
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="memoryarena",
                path=score_path,
                min_exact_match=0.8,
            )
        ],
        out_path,
    )

    assert rc == 1
    row = report["scores"][0]
    assert row["passed"] is False
    assert row["diagnostic_methods"] == ["mapu_diagnostic_templates_memoryarena_v1"]
    assert row["non_release_methods"] == ["mapu_diagnostic_templates_memoryarena_v1"]
    assert "diagnostic/non-release" in str(row["failure_reason"])


def test_run_gate_rejects_web_grounded_prediction_methods_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    score_path = tmp_path / "memoryarena_score.json"
    out_path = tmp_path / "gate.json"
    _score_file(
        score_path,
        exact_match=1.0,
        method_counts={"mapu_web_grounded_memoryarena_v1": 10},
    )
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="memoryarena",
                path=score_path,
                min_exact_match=0.8,
            )
        ],
        out_path,
    )

    assert rc == 1
    row = report["scores"][0]
    assert row["passed"] is False
    assert row["diagnostic_methods"] == ["mapu_web_grounded_memoryarena_v1"]
    assert row["non_release_methods"] == ["mapu_web_grounded_memoryarena_v1"]
    assert "diagnostic/non-release" in str(row["failure_reason"])


def test_run_gate_can_allow_non_release_prediction_methods_for_debug(
    tmp_path: Path,
    monkeypatch,
) -> None:
    score_path = tmp_path / "ama_score.json"
    out_path = tmp_path / "gate.json"
    _score_file(
        score_path,
        exact_match=1.0,
        method_counts={"mapu_baba_trajectory_reasoner_v1": 10},
    )
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="ama_bench",
                path=score_path,
                min_exact_match=0.8,
            )
        ],
        out_path,
        allow_non_release_methods=True,
    )

    assert rc == 0
    assert report["allow_diagnostic_methods"] is True
    assert report["allow_non_release_methods"] is True
    assert report["scores"][0]["diagnostic_methods"] == ["mapu_baba_trajectory_reasoner_v1"]


def test_run_gate_keeps_legacy_diagnostic_override_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    score_path = tmp_path / "ama_score.json"
    out_path = tmp_path / "gate.json"
    _score_file(
        score_path,
        exact_match=1.0,
        method_counts={"mapu_baba_trajectory_reasoner_v1": 10},
    )
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda root: {"sha": "abc", "dirty": False, "status_porcelain": []},
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="ama_bench",
                path=score_path,
                min_exact_match=0.8,
            )
        ],
        out_path,
        allow_diagnostic_methods=True,
    )

    assert rc == 0
    assert report["allow_non_release_methods"] is True


def test_run_gate_can_require_clean_git(tmp_path: Path, monkeypatch) -> None:
    score_path = tmp_path / "memoryarena_score.json"
    out_path = tmp_path / "gate.json"
    _score_file(score_path, exact_match=1.0)
    monkeypatch.setattr(benchmark_score_gate, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        benchmark_score_gate,
        "git_identity",
        lambda _repo_root: {
            "sha": "abc",
            "dirty": True,
            "status_porcelain": [" M file.py"],
        },
    )

    rc, report = benchmark_score_gate.run_gate(
        [
            benchmark_score_gate.ScoreSpec(
                benchmark="memoryarena",
                path=score_path,
                min_exact_match=0.8,
            )
        ],
        out_path,
        require_clean_git=True,
    )

    assert rc == 1
    assert report["status"] == "fail"
    assert report["git"]["failure_reason"] == "Git worktree is dirty."
