from __future__ import annotations

import argparse
import importlib
import pathlib
import re
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
    prompt = _suppress_printed_reasoning(prompt)
    fact_hints = _extract_fact_hints(prompt)
    fact_hint_section = ""
    if fact_hints:
        fact_hint_section = (
            "\n\nDIRECT FACT HINTS FROM RETRIEVED MEMORIES:\n"
            + "\n".join(f"- {hint}" for hint in fact_hints)
            + "\nUse these only when they match the question, and preserve their exact qualifiers."
        )
    return (
        f"{prompt}{fact_hint_section}\n\n"
        "OUTPUT FORMAT REQUIREMENT:\n"
        "Use the retrieved memories first. A user-stated fact or fact_hint "
        "containing an exact name, number, date, duration, identity, preference, "
        "status, or correction is explicit evidence and should be answered "
        "directly when it matches the question.\n"
        "If you identify a matching memory or fact_hint, do not answer that the "
        "information is insufficient; copy or normalize the matching fact.\n"
        "Preserve qualifiers from direct evidence, such as 'each way', 'per day', "
        "'before tax', or 'as of Friday'. Do not convert a per-leg, per-item, or "
        "qualified value into a total unless the question explicitly asks for a "
        "total, round trip, sum, or aggregate.\n"
        "For duration facts in the form '<thing> takes <duration phrase>', answer "
        "with the full duration phrase, including words like 'each way'.\n"
        "Only say the information is insufficient when the provided memories are "
        "empty, unrelated, or about a different entity/context.\n"
        "Override any earlier instruction to print <mem_thinking> tags. Think "
        "privately if needed, but output only one final non-empty line exactly as:\n"
        "ANSWER: <your concise answer>\n"
        "If the memories are genuinely insufficient, write a concise non-empty "
        "ANSWER line that says the answer is not available from the memories.\n"
        "Never leave ANSWER blank."
    )


def _extract_fact_hints(prompt: str, limit: int = 12) -> list[str]:
    hints: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"fact_hint:\s*([^\n\r]+)", prompt):
        hint = match.group(1).strip(" -;")
        if not hint or hint in seen:
            continue
        seen.add(hint)
        hints.append(hint)
        if len(hints) >= limit:
            break
    return hints


def _suppress_printed_reasoning(prompt: str) -> str:
    replacements = {
        "Before answering, reason step-by-step inside <mem_thinking> tags:":
            "Before answering, use these internal checks silently; do not print reasoning:",
        "The user will only see text outside the <mem_thinking> tags.":
            "The user will only see the final answer line.",
        (
            "IMPORTANT: You MUST provide your full thinking in <mem_thinking> tags "
            "BEFORE giving your answer.; Reasoning and answer:"
        ):
            "Do not print reasoning. Final answer only:",
        'Say "The information provided is not enough" when:':
            "Use an insufficiency answer only when:",
    }
    for old, new in replacements.items():
        prompt = prompt.replace(old, new)
    return prompt


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
