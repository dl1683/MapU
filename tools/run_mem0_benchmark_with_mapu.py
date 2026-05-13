from __future__ import annotations

import argparse
import importlib
import pathlib
import sys


def _parse_args() -> tuple[str, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run Mem0 benchmark scripts using MapU as the memory backend.",
    )
    parser.add_argument(
        "benchmark",
        choices=("locomo", "longmemeval", "beam"),
        help="Benchmark module under memory-benchmarks/benchmarks/",
    )
    parser.add_argument(
        "benchmark_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed directly to benchmark runner.",
    )
    ns = parser.parse_args()
    passthrough = ns.benchmark_args
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    return ns.benchmark, passthrough


def main() -> None:
    benchmark, benchmark_args = _parse_args()
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    mem0_repo = repo_root / ".tmp" / "memory-benchmarks"
    if not mem0_repo.exists():
        raise SystemExit(
            f"Missing benchmark repo at {mem0_repo}. "
            "Clone https://github.com/mem0ai/memory-benchmarks first."
        )

    sys.path.insert(0, str(repo_root / "tools"))
    sys.path.insert(0, str(mem0_repo))

    from mapu_mem0_adapter import MapUMem0Client

    run_module = importlib.import_module(f"benchmarks.{benchmark}.run")
    run_module.Mem0Client = MapUMem0Client

    argv = [f"{benchmark}.run", *benchmark_args]
    old_argv = sys.argv
    try:
        sys.argv = argv
        run_module.main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()
