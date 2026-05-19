"""Aggregate benchmark score gates for MapU memory benchmark runs."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScoreSpec:
    benchmark: str
    path: Path
    min_exact_match: float
    metric: str = "exact_match"


def parse_score_spec(raw: str) -> ScoreSpec:
    if "=" not in raw:
        raise ValueError(f"Invalid score value {raw!r}: missing '='")
    benchmark, rest = raw.split("=", 1)
    if ":" not in rest:
        raise ValueError(f"Invalid score value {raw!r}: missing ':MIN_SCORE'")
    left, threshold_text = rest.rsplit(":", 1)
    path_text = left
    metric = "exact_match"
    if ":" in left:
        candidate_path, candidate_metric = left.rsplit(":", 1)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate_metric):
            path_text = candidate_path
            metric = candidate_metric
    benchmark = benchmark.strip()
    path_text = path_text.strip()
    metric = metric.strip()
    if not benchmark:
        raise ValueError(f"Invalid score value {raw!r}: benchmark is empty")
    if not path_text:
        raise ValueError(f"Invalid score value {raw!r}: path is empty")
    if not metric:
        raise ValueError(f"Invalid score value {raw!r}: metric is empty")
    try:
        threshold = float(threshold_text)
    except ValueError as exc:
        raise ValueError(f"Invalid score value {raw!r}: threshold is not numeric") from exc
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"Invalid score value {raw!r}: threshold must be between 0.0 and 1.0")
    return ScoreSpec(
        benchmark=benchmark,
        path=Path(path_text),
        min_exact_match=threshold,
        metric=metric,
    )


def repo_root() -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd()
    root = result.stdout.strip()
    return Path(root) if root else Path.cwd()


def git_identity(root: Path) -> dict[str, Any]:
    def run_git(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return ""
        return result.stdout.strip()

    sha = run_git("rev-parse", "HEAD")
    status = run_git("status", "--porcelain")
    return {
        "sha": sha or None,
        "dirty": bool(status),
        "status_porcelain": status.splitlines()[:100],
    }


def _load_score(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None


def _non_release_methods(score: dict[str, Any]) -> list[str]:
    method_counts = score.get("method_counts")
    if not isinstance(method_counts, dict):
        return []
    non_release_markers = (
        "diagnostic",
        "template",
        "baba_trajectory_reasoner",
        "exact",
        "web_grounded",
    )
    methods: list[str] = []
    for method in method_counts:
        method_text = str(method)
        method_lower = method_text.lower()
        if any(marker in method_lower for marker in non_release_markers):
            methods.append(method_text)
    return sorted(methods)


def _score_row(
    spec: ScoreSpec,
    root: Path,
    *,
    allow_non_release_methods: bool,
) -> dict[str, Any]:
    path = spec.path if spec.path.is_absolute() else root / spec.path
    score = _load_score(path)
    if score is None:
        return {
            "benchmark": spec.benchmark,
            "path": str(path),
            "metric": spec.metric,
            "threshold_metric": spec.metric,
            "threshold": spec.min_exact_match,
            "min_exact_match": spec.min_exact_match,
            "status": "missing_or_invalid",
            "passed": False,
            "failure_reason": "Score file is missing or invalid JSON.",
        }

    exact_match = score.get("exact_match")
    metric_value = score.get(spec.metric)
    evaluated = score.get("evaluated")
    score_status = score.get("status")
    method_counts_value = score.get("method_counts")
    method_counts = method_counts_value if isinstance(method_counts_value, dict) else {}
    non_release_methods = _non_release_methods(score)
    failure_reason = None
    passed = True

    if score_status != "ok":
        passed = False
        failure_reason = str(score.get("failure_reason") or "score status is not ok")
    elif non_release_methods and not allow_non_release_methods:
        passed = False
        failure_reason = (
            "Score artifact uses diagnostic/non-release prediction methods; "
            "rerun with benchmark-agnostic predictions for release gates."
        )
    elif not isinstance(evaluated, int) or evaluated <= 0:
        passed = False
        failure_reason = "Score file evaluated zero predictions."
    elif not isinstance(metric_value, (int, float)):
        passed = False
        failure_reason = f"Score file has no numeric {spec.metric}."
    elif float(metric_value) < spec.min_exact_match:
        passed = False
        failure_reason = (
            f"{spec.metric}={float(metric_value):.6f} below "
            f"min_{spec.metric}={spec.min_exact_match:.6f}"
        )

    return {
        "benchmark": spec.benchmark,
        "path": str(path),
        "metric": spec.metric,
        "metric_value": metric_value,
        "threshold_metric": spec.metric,
        "threshold": spec.min_exact_match,
        "min_exact_match": spec.min_exact_match,
        "status": score_status,
        "evaluated": evaluated,
        "correct": score.get("correct"),
        "exact_match": exact_match,
        "token_f1": score.get("token_f1"),
        "method_counts": method_counts,
        "diagnostic_methods": non_release_methods,
        "non_release_methods": non_release_methods,
        "passed": passed,
        "failure_reason": failure_reason,
    }


def run_gate(
    specs: list[ScoreSpec],
    out: Path,
    *,
    require_clean_git: bool = False,
    allow_non_release_methods: bool = False,
    allow_diagnostic_methods: bool = False,
) -> tuple[int, dict[str, Any]]:
    root = repo_root()
    git = git_identity(root)
    non_release_allowed = bool(allow_non_release_methods or allow_diagnostic_methods)
    rows = [
        _score_row(
            spec,
            root,
            allow_non_release_methods=non_release_allowed,
        )
        for spec in specs
    ]
    passed = all(bool(row["passed"]) for row in rows)

    if require_clean_git and git["dirty"]:
        passed = False
        git["failure_reason"] = "Git worktree is dirty."

    report = {
        "status": "ok" if passed else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "git": git,
        "require_clean_git": require_clean_git,
        "allow_diagnostic_methods": non_release_allowed,
        "allow_non_release_methods": non_release_allowed,
        "scores": rows,
    }

    out_path = out if out.is_absolute() else root / out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return (0 if passed else 1), report
