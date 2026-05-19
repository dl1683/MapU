from __future__ import annotations

import argparse
import importlib
import pathlib
import sys
from collections.abc import Callable
from typing import Any


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


def _require_nonblank_answer(prompt: str) -> str:
    return (
        f"{prompt}\n\n"
        "OUTPUT FORMAT REQUIREMENT:\n"
        "After any private reasoning tags, write a final non-empty line exactly as:\n"
        "ANSWER: <your concise answer>\n"
        "If the memories are insufficient, still write:\n"
        "ANSWER: The information provided is not enough.\n"
        "Never leave ANSWER blank."
    )


def _wrap_prompt_builder(fn: Callable[..., str]) -> Callable[..., str]:
    def wrapped(*args: Any, **kwargs: Any) -> str:
        return _require_nonblank_answer(fn(*args, **kwargs))

    return wrapped


def _patch_answer_prompt_contract(run_module: Any) -> None:
    # Some benchmark prompts ask models to reason in tags, then benchmark code
    # strips those tags. Local OpenAI-compatible models can otherwise return
    # only stripped reasoning and leave an empty stored answer.
    for name in ("get_answer_generation_prompt", "get_beam_answer_generation_prompt"):
        fn = getattr(run_module, name, None)
        if callable(fn):
            setattr(run_module, name, _wrap_prompt_builder(fn))


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
    _patch_answer_prompt_contract(run_module)

    argv = [f"{benchmark}.run", *benchmark_args]
    old_argv = sys.argv
    try:
        sys.argv = argv
        run_module.main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()
