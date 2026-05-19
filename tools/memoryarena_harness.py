from __future__ import annotations

import argparse

from mapu.evaluation import memoryarena


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and normalize MemoryArena into MapU-friendly scenarios.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("catalog", help="Print MemoryArena config sizes and columns.")

    export = subparsers.add_parser("export", help="Export MemoryArena scenarios as JSONL.")
    export.add_argument(
        "--out",
        default="data/benchmarks/memoryarena/scenarios.jsonl",
        help="Output JSONL path.",
    )
    export.add_argument(
        "--limit-per-config",
        type=int,
        default=0,
        help="Optional max scenarios per config. 0 means no limit.",
    )
    predict = subparsers.add_parser(
        "predict",
        help="Generate local MapU baseline predictions for MemoryArena scenarios.",
    )
    predict.add_argument("--scenarios", required=True)
    predict.add_argument("--out", default="results/memoryarena_predictions.jsonl")
    predict.add_argument(
        "--max-scenarios",
        type=int,
        default=0,
        help="Optional max scenarios to predict. 0 means all scenarios.",
    )
    predict.add_argument(
        "--predictor",
        choices=("benchmark_agnostic", "diagnostic_templates"),
        default="benchmark_agnostic",
        help=(
            "Prediction mode. benchmark_agnostic uses only exported scenario inputs; "
            "diagnostic_templates is for scorer smoke tests only."
        ),
    )

    score = subparsers.add_parser(
        "score", help="Score prediction JSONL against exported scenarios."
    )
    score.add_argument("--scenarios", required=True, help="Scenario JSONL from `export`.")
    score.add_argument(
        "--predictions",
        required=True,
        help=(
            "Prediction JSONL with scenario_id, config, turn_index, and prediction fields. "
            "Exact normalized string equality is used."
        ),
    )
    score.add_argument(
        "--out",
        default="results/memoryarena_score.json",
        help="Output score report path.",
    )
    score.add_argument(
        "--min-exact-match",
        type=float,
        default=None,
        help=(
            "Optional minimum exact-match score required for exit code 0. "
            "The scorer always fails when zero predictions are evaluated."
        ),
    )
    return parser.parse_args()


def main() -> int:
    ns = _parse_args()
    if ns.command == "catalog":
        return memoryarena.catalog()
    if ns.command == "export":
        return memoryarena.export(ns.out, ns.limit_per_config)
    if ns.command == "predict":
        return memoryarena.predict(
            ns.scenarios,
            ns.out,
            max_scenarios=ns.max_scenarios,
            predictor=ns.predictor,
        )
    if ns.command == "score":
        return memoryarena.score(
            ns.scenarios,
            ns.predictions,
            ns.out,
            ns.min_exact_match,
        )
    raise AssertionError(f"Unhandled command {ns.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
