from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run LOCOMO + LongMemEval + BEAM via MapU Mem0 adapter.",
    )
    parser.add_argument("--project-name", default="mapu_memory_matrix")
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--top-k-cutoffs", default="10,50,200")
    parser.add_argument("--predict-only", action="store_true")
    parser.add_argument("--locomo-conversations", default="0-2")
    parser.add_argument("--locomo-max-questions", type=int, default=60)
    parser.add_argument("--longmemeval-per-type", type=int, default=5)
    parser.add_argument("--beam-chat-sizes", default="100K")
    parser.add_argument("--beam-conversations", default="0-2")
    parser.add_argument(
        "--output-json",
        default="results/matrix/mapu_memory_matrix_summary.json",
    )
    return parser.parse_args()


def _run(repo_root: pathlib.Path, benchmark: str, args: list[str]) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "tools/run_mem0_benchmark_with_mapu.py",
        benchmark,
        "--",
        *args,
    ]
    started = datetime.now(UTC).isoformat()
    child_env = os.environ.copy()
    child_env.setdefault("PYTHONUTF8", "1")
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        env=child_env,
        capture_output=True,
        check=False,
    )
    stdout_text = (
        proc.stdout.decode("utf-8", errors="replace")
        if isinstance(proc.stdout, bytes)
        else str(proc.stdout or "")
    )
    stderr_text = (
        proc.stderr.decode("utf-8", errors="replace")
        if isinstance(proc.stderr, bytes)
        else str(proc.stderr or "")
    )
    finished = datetime.now(UTC).isoformat()
    return {
        "benchmark": benchmark,
        "command": cmd,
        "started_at": started,
        "finished_at": finished,
        "returncode": proc.returncode,
        "stdout_tail": stdout_text[-6000:],
        "stderr_tail": stderr_text[-6000:],
    }


def main() -> int:
    ns = _parse_args()
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    results: list[dict[str, Any]] = []

    common = [
        "--project-name", ns.project_name,
        "--top-k", str(ns.top_k),
        "--top-k-cutoffs", ns.top_k_cutoffs,
        "--max-workers", str(ns.max_workers),
    ]
    if ns.predict_only:
        common.append("--predict-only")

    runs: list[tuple[str, list[str]]] = [
        (
            "locomo",
            [
                *common,
                "--conversations", ns.locomo_conversations,
                "--max-questions", str(ns.locomo_max_questions),
            ],
        ),
        (
            "longmemeval",
            [
                *common,
                "--per-type", str(ns.longmemeval_per_type),
            ],
        ),
        (
            "beam",
            [
                *common,
                "--chat-sizes", ns.beam_chat_sizes,
                "--conversations", ns.beam_conversations,
            ],
        ),
    ]

    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = "dummy"

    for benchmark, run_args in runs:
        print(f"[matrix] running {benchmark} ...")
        result = _run(repo_root, benchmark, run_args)
        results.append(result)
        if result["returncode"] != 0:
            print(f"[matrix] {benchmark} failed with code {result['returncode']}")

    summary = {
        "project_name": ns.project_name,
        "created_at": datetime.now(UTC).isoformat(),
        "runs": results,
        "all_ok": all(r["returncode"] == 0 for r in results),
    }

    output_path = repo_root / ns.output_json
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[matrix] summary written to {output_path}")
    return 0 if summary["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
