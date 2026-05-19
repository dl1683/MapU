from __future__ import annotations

import argparse
import json
from pathlib import Path

from mapu.evaluation.benchmark_score_gate import (
    ScoreSpec,
    parse_score_spec,
    repo_root,
    run_gate,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate memory benchmark score artifacts against release thresholds.",
    )
    parser.add_argument(
        "--score",
        action="append",
        required=True,
        metavar="BENCHMARK=PATH[:METRIC]:MIN_SCORE",
        help=(
            "Score artifact, optional metric, and threshold. Examples: "
            "memoryarena=results/memoryarena_score.json:0.80 or "
            "ama_bench=results/ama_score.json:token_f1:0.65"
        ),
    )
    parser.add_argument(
        "--out",
        default="results/memory_benchmark_score_gate.json",
        help="Output gate report JSON path.",
    )
    parser.add_argument(
        "--require-clean-git",
        action="store_true",
        help="Fail when the git worktree is dirty.",
    )
    parser.add_argument(
        "--allow-non-release-methods",
        action="store_true",
        help=(
            "Allow score artifacts produced by diagnostic/non-release predictors. "
            "Do not use this for release or public-claim gates."
        ),
    )
    parser.add_argument(
        "--allow-diagnostic-methods",
        action="store_true",
        help="Compatibility alias for --allow-non-release-methods.",
    )
    return parser.parse_args()


def _parse_score_spec(raw: str) -> ScoreSpec:
    try:
        return parse_score_spec(raw)
    except ValueError as exc:
        raise SystemExit(str(exc).replace("score value", "--score value")) from exc


def main() -> int:
    ns = _parse_args()
    specs = [_parse_score_spec(raw) for raw in ns.score]
    rc, report = run_gate(
        specs,
        Path(ns.out),
        require_clean_git=bool(ns.require_clean_git),
        allow_non_release_methods=bool(
            ns.allow_non_release_methods or ns.allow_diagnostic_methods
        ),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "path": str((repo_root() / ns.out).resolve()),
                "benchmarks": len(report["scores"]),
                "failed": [
                    row["benchmark"]
                    for row in report["scores"]
                    if not row["passed"]
                ],
            },
            ensure_ascii=True,
        )
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
