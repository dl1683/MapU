from __future__ import annotations

import argparse

from mapu.evaluation import ama_bench


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and normalize AMA-Bench trajectory-memory scenarios.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("catalog", help="Print AMA-Bench dataset size and columns.")

    export = subparsers.add_parser("export", help="Export AMA-Bench scenarios as JSONL.")
    export.add_argument(
        "--out",
        default="data/benchmarks/ama_bench/scenarios.sample.jsonl",
        help="Output JSONL path.",
    )
    export.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max scenarios to export. 0 means full dataset.",
    )
    predict = subparsers.add_parser(
        "predict",
        help="Generate local MapU baseline predictions for AMA-Bench scenarios.",
    )
    predict.add_argument("--scenarios", required=True)
    predict.add_argument("--out", default="results/ama_bench_predictions.jsonl")
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
            "Prediction mode. benchmark_agnostic uses generic trajectory retrieval; "
            "diagnostic_templates is for scorer smoke tests only."
        ),
    )

    score = subparsers.add_parser("score", help="Score prediction JSONL by exact normalized match.")
    score.add_argument("--scenarios", required=True, help="Scenario JSONL from `export`.")
    score.add_argument(
        "--predictions",
        required=True,
        help=(
            "Prediction JSONL with scenario_id, question_index, and prediction fields. "
            "Official AMA-Bench uses LLM-as-judge; this is a cheap local sanity score."
        ),
    )
    score.add_argument(
        "--out",
        default="results/ama_bench_score.json",
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
        return ama_bench.catalog()
    if ns.command == "export":
        return ama_bench.export(ns.out, ns.limit)
    if ns.command == "predict":
        return ama_bench.predict(
            ns.scenarios,
            ns.out,
            max_scenarios=ns.max_scenarios,
            predictor=ns.predictor,
        )
    if ns.command == "score":
        return ama_bench.score(
            ns.scenarios,
            ns.predictions,
            ns.out,
            ns.min_exact_match,
        )
    raise AssertionError(f"Unhandled command {ns.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
