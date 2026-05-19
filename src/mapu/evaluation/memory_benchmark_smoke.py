"""One-command smoke workflow for public memory benchmark CLI adapters."""

from __future__ import annotations

import hashlib
import json
import subprocess
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from mapu.evaluation import ama_bench, memoryarena
from mapu.evaluation.benchmark_score_gate import ScoreSpec, run_gate


def _worktree_fingerprint(repo_root: Path) -> tuple[dict[str, Any], list[str]]:
    commands = {
        "status": ["git", "status", "--porcelain=v1"],
        "changed": ["git", "diff", "--name-only", "HEAD"],
        "untracked": ["git", "ls-files", "--others", "--exclude-standard"],
    }
    results = {}
    for name, command in commands.items():
        try:
            results[name] = subprocess.run(
                command,
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return {}, [f"{command[0]} command unavailable: {exc}"]
    errors = [
        result.stderr.strip() or f"{' '.join(commands[name])} failed"
        for name, result in results.items()
        if result.returncode != 0
    ]
    if errors:
        return {}, errors

    status_lines = [
        line for line in results["status"].stdout.splitlines() if line.strip()
    ]
    changed_files = {
        line
        for source in (results["changed"].stdout, results["untracked"].stdout)
        for line in source.splitlines()
        if line.strip()
    }
    payload_parts = ["[status]", *status_lines, "[files]"]
    for relative in sorted(changed_files):
        path = repo_root / relative
        if path.is_file():
            file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            payload_parts.append(f"{relative}\t{file_hash}")
        else:
            payload_parts.append(f"{relative}\t<missing-or-directory>")
    payload = "\n".join(payload_parts)
    return {
        "worktree_status_porcelain": status_lines,
        "worktree_dirty_path_count": len(status_lines),
        "worktree_fingerprint_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }, []


@dataclass(frozen=True)
class SmokePaths:
    output_dir: Path
    memoryarena_scenarios: Path
    memoryarena_predictions: Path
    memoryarena_score: Path
    ama_scenarios: Path
    ama_predictions: Path
    ama_score: Path
    gate: Path
    report: Path


def _paths(output_dir: Path) -> SmokePaths:
    return SmokePaths(
        output_dir=output_dir,
        memoryarena_scenarios=output_dir / "memoryarena_scenarios.jsonl",
        memoryarena_predictions=output_dir / "memoryarena_predictions.jsonl",
        memoryarena_score=output_dir / "memoryarena_score.json",
        ama_scenarios=output_dir / "ama_scenarios.jsonl",
        ama_predictions=output_dir / "ama_predictions.jsonl",
        ama_score=output_dir / "ama_score.json",
        gate=output_dir / "score_gate.json",
        report=output_dir / "smoke_report.json",
    )


def run_smoke(
    *,
    output_dir: Path,
    memoryarena_scenarios: Path | None = None,
    ama_scenarios: Path | None = None,
    export: bool = True,
    memoryarena_limit_per_config: int = 1,
    ama_limit: int = 1,
    predictor: str = "benchmark_agnostic",
    min_token_f1: float = 0.45,
    allow_non_release_methods: bool = False,
    allow_diagnostic_methods: bool = False,
    verbose_steps: bool = False,
) -> tuple[int, dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths(output_dir)
    steps: dict[str, dict[str, Any]] = {}
    non_release_allowed = bool(allow_non_release_methods or allow_diagnostic_methods)
    worktree_fingerprint, worktree_fingerprint_errors = _worktree_fingerprint(Path.cwd())

    def _run_step(name: str, fn: Any, *args: Any, **kwargs: Any) -> int:
        captured = StringIO()
        if verbose_steps:
            rc = fn(*args, **kwargs)
            stdout = ""
        else:
            with redirect_stdout(captured):
                rc = fn(*args, **kwargs)
            stdout = captured.getvalue()
        steps[name] = {"return_code": rc, "stdout": stdout}
        return int(rc or 0)

    if not 0.0 <= min_token_f1 <= 1.0:
        raise SystemExit("--min-token-f1 must be between 0.0 and 1.0.")

    if predictor in {"diagnostic_templates", "web_grounded"} and not non_release_allowed:
        raise SystemExit(
            "Non-release predictors require --allow-non-release-methods "
            "(or compatibility alias --allow-diagnostic-methods) so the smoke "
            "report cannot be confused with release evidence."
        )

    if export:
        memoryarena_export_rc = _run_step(
            "memoryarena_export",
            memoryarena.export,
            str(paths.memoryarena_scenarios),
            memoryarena_limit_per_config,
        )
        ama_export_rc = _run_step(
            "ama_bench_export",
            ama_bench.export,
            str(paths.ama_scenarios),
            ama_limit,
        )
    else:
        memoryarena_export_rc = 0
        ama_export_rc = 0

    memoryarena_scenario_path = memoryarena_scenarios or paths.memoryarena_scenarios
    ama_scenario_path = ama_scenarios or paths.ama_scenarios
    if not memoryarena_scenario_path.exists():
        raise SystemExit(
            f"MemoryArena scenario file does not exist: {memoryarena_scenario_path}"
        )
    if not ama_scenario_path.exists():
        raise SystemExit(f"AMA-Bench scenario file does not exist: {ama_scenario_path}")

    ama_predictor = "benchmark_agnostic" if predictor == "web_grounded" else predictor
    memoryarena_predict_rc = _run_step(
        "memoryarena_predict",
        memoryarena.predict,
        str(memoryarena_scenario_path),
        str(paths.memoryarena_predictions),
        predictor=predictor,
    )
    memoryarena_score_rc = _run_step(
        "memoryarena_score",
        memoryarena.score,
        str(memoryarena_scenario_path),
        str(paths.memoryarena_predictions),
        str(paths.memoryarena_score),
    )
    ama_predict_rc = _run_step(
        "ama_bench_predict",
        ama_bench.predict,
        str(ama_scenario_path),
        str(paths.ama_predictions),
        predictor=ama_predictor,
    )
    ama_score_rc = _run_step(
        "ama_bench_score",
        ama_bench.score,
        str(ama_scenario_path),
        str(paths.ama_predictions),
        str(paths.ama_score),
    )

    gate_rc, gate_report = run_gate(
        [
            ScoreSpec(
                benchmark="memoryarena",
                path=paths.memoryarena_score,
                metric="token_f1",
                min_exact_match=min_token_f1,
            ),
            ScoreSpec(
                benchmark="ama_bench",
                path=paths.ama_score,
                metric="token_f1",
                min_exact_match=min_token_f1,
            ),
        ],
        paths.gate,
        allow_non_release_methods=non_release_allowed,
    )
    status = (
        "ok"
        if all(
            rc == 0
            for rc in (
                memoryarena_export_rc,
                ama_export_rc,
                memoryarena_predict_rc,
                memoryarena_score_rc,
                ama_predict_rc,
                ama_score_rc,
                gate_rc,
            )
        )
        else "fail"
    )
    report = {
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "smoke_only": True,
        "public_performance_evidence": False,
        **worktree_fingerprint,
        "worktree_fingerprint_errors": worktree_fingerprint_errors,
        "evidence_note": (
            "Tiny installed-CLI smoke for adapter and gate health only; "
            "not leaderboard or public performance evidence."
        ),
        "predictor": predictor,
        "effective_predictors": {
            "memoryarena": predictor,
            "ama_bench": ama_predictor,
        },
        "min_token_f1": min_token_f1,
        "allow_diagnostic_methods": non_release_allowed,
        "allow_non_release_methods": non_release_allowed,
        "inputs": {
            "exported_scenarios": export,
            "memoryarena_scenarios": str(memoryarena_scenario_path),
            "ama_scenarios": str(ama_scenario_path),
            "memoryarena_limit_per_config": memoryarena_limit_per_config,
            "ama_limit": ama_limit,
        },
        "paths": {key: str(value) for key, value in asdict(paths).items()},
        "score_exit_codes": {
            "memoryarena_export": memoryarena_export_rc,
            "ama_bench_export": ama_export_rc,
            "memoryarena_predict": memoryarena_predict_rc,
            "memoryarena": memoryarena_score_rc,
            "ama_bench_predict": ama_predict_rc,
            "ama_bench": ama_score_rc,
            "gate": gate_rc,
        },
        "steps": steps,
        "gate": {
            "status": gate_report["status"],
            "scores": gate_report["scores"],
        },
        "score_summary": [
            {
                "benchmark": row["benchmark"],
                "metric": row["metric"],
                "metric_value": row["metric_value"],
                "threshold": row.get("threshold", row["min_exact_match"]),
                "threshold_metric": row.get("threshold_metric", row["metric"]),
                "passed": row["passed"],
                "failure_reason": row.get("failure_reason"),
            }
            for row in gate_report["scores"]
        ],
    }
    paths.report.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    return (0 if status == "ok" else 1), report
