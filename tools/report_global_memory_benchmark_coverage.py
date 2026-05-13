from __future__ import annotations

import argparse
import json
import pathlib
from datetime import UTC, datetime
from typing import Any


BENCHMARKS: list[dict[str, Any]] = [
    {
        "id": "locomo",
        "name": "LoCoMo",
        "primary_source": "https://arxiv.org/abs/2402.17753",
        "scope_note": "Very long multi-session conversation memory benchmark.",
        "publicly_used_by": [
            {
                "system": "Mem0",
                "source": "https://docs.mem0.ai/core-concepts/memory-evaluation",
            },
            {
                "system": "Agent Memory Benchmark (Hindsight/Vectorize)",
                "source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
            },
        ],
        "mapu_runnable_now": True,
    },
    {
        "id": "longmemeval",
        "name": "LongMemEval",
        "primary_source": "https://arxiv.org/abs/2410.10813",
        "scope_note": "500-question benchmark for long-term assistant memory abilities.",
        "publicly_used_by": [
            {
                "system": "Mem0",
                "source": "https://docs.mem0.ai/core-concepts/memory-evaluation",
            },
            {
                "system": "Supermemory",
                "source": "https://supermemory.ai/research/",
            },
            {
                "system": "Agent Memory Benchmark (Hindsight/Vectorize)",
                "source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
            },
        ],
        "mapu_runnable_now": True,
    },
    {
        "id": "beam",
        "name": "BEAM",
        "primary_source": "https://docs.mem0.ai/core-concepts/memory-evaluation",
        "scope_note": "Memory benchmark spanning up to 10M-token conversations.",
        "publicly_used_by": [
            {
                "system": "Mem0",
                "source": "https://docs.mem0.ai/core-concepts/memory-evaluation",
            },
            {
                "system": "Agent Memory Benchmark (Hindsight/Vectorize)",
                "source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
            },
        ],
        "mapu_runnable_now": True,
    },
    {
        "id": "lifebench",
        "name": "LifeBench",
        "primary_source": "https://arxiv.org/abs/2603.03781",
        "scope_note": "Long-horizon multi-source personalized memory benchmark.",
        "publicly_used_by": [
            {
                "system": "Agent Memory Benchmark (Hindsight/Vectorize)",
                "source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
            },
        ],
        "mapu_runnable_now": False,
    },
    {
        "id": "membench",
        "name": "MemBench",
        "primary_source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
        "scope_note": "Agent-memory benchmark with multi-level perspective tasks (MCQ-heavy).",
        "publicly_used_by": [
            {
                "system": "Agent Memory Benchmark (Hindsight/Vectorize)",
                "source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
            },
        ],
        "mapu_runnable_now": False,
    },
    {
        "id": "memsim",
        "name": "MemSim",
        "primary_source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
        "scope_note": "Memory simulation benchmark with diverse QA types (including noisy conditions).",
        "publicly_used_by": [
            {
                "system": "Agent Memory Benchmark (Hindsight/Vectorize)",
                "source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
            },
        ],
        "mapu_runnable_now": False,
    },
    {
        "id": "personamem",
        "name": "PersonaMem",
        "primary_source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
        "scope_note": "Long-horizon personal preference tracking across multi-session chats.",
        "publicly_used_by": [
            {
                "system": "Agent Memory Benchmark (Hindsight/Vectorize)",
                "source": "https://github.com/vectorize-io/agent-memory-benchmark/blob/main/catalog.json",
            },
        ],
        "mapu_runnable_now": False,
    },
    {
        "id": "dmr",
        "name": "Deep Memory Retrieval (DMR)",
        "primary_source": "https://arxiv.org/abs/2501.13956",
        "scope_note": "Legacy retrieval benchmark used in memory-system papers such as Zep.",
        "publicly_used_by": [
            {
                "system": "Zep",
                "source": "https://arxiv.org/abs/2501.13956",
            },
        ],
        "mapu_runnable_now": False,
    },
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a global memory benchmark coverage report for MapU.",
    )
    p.add_argument(
        "--proxy-summary",
        default="results/matrix/proxy_mapu_memory_matrix_holdout_v8.json",
        help="Proxy summary JSON with locomo/longmemeval/beam scores.",
    )
    p.add_argument(
        "--output-json",
        default="results/matrix/global_memory_benchmark_coverage.json",
    )
    p.add_argument(
        "--output-md",
        default="results/matrix/global_memory_benchmark_coverage.md",
    )
    return p.parse_args()


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _format_proxy(proxy_summary: dict[str, Any], benchmark_id: str) -> str:
    row = proxy_summary.get(benchmark_id)
    if not isinstance(row, dict):
        return "n/a"
    hit = row.get("support_hit_rate")
    nug = row.get("nugget_hit_rate")
    if isinstance(hit, (int, float)) and isinstance(nug, (int, float)):
        return f"support={hit:.3f}, nugget={nug:.3f}"
    if isinstance(hit, (int, float)):
        return f"support={hit:.3f}"
    return "n/a"


def _coverage_rows(proxy_summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bench in BENCHMARKS:
        adopted_by = sorted({entry["system"] for entry in bench["publicly_used_by"]})
        rows.append(
            {
                "benchmark_id": bench["id"],
                "benchmark_name": bench["name"],
                "primary_source": bench["primary_source"],
                "scope_note": bench["scope_note"],
                "adopted_by": adopted_by,
                "mapu_runnable_now": bool(bench["mapu_runnable_now"]),
                "mapu_latest_proxy": _format_proxy(proxy_summary, bench["id"]),
            }
        )
    return rows


def _render_markdown(rows: list[dict[str, Any]], proxy_path: str) -> str:
    generated_at = datetime.now(UTC).isoformat()
    runnable = sum(1 for r in rows if r["mapu_runnable_now"])
    total = len(rows)
    lines = [
        "# Global Memory Benchmark Coverage (MapU)",
        "",
        f"- Generated: `{generated_at}`",
        f"- Proxy summary source: `{proxy_path}`",
        f"- Runnable now: **{runnable}/{total}**",
        "",
        "| Benchmark | Public Adopters (from public sources) | MapU Runnable Now | Latest MapU Proxy |",
        "|---|---|---:|---|",
    ]
    for row in rows:
        adopters = ", ".join(row["adopted_by"]) if row["adopted_by"] else "n/a"
        runnable_text = "yes" if row["mapu_runnable_now"] else "no"
        lines.append(
            f"| {row['benchmark_name']} | {adopters} | {runnable_text} | {row['mapu_latest_proxy']} |"
        )

    lines.extend(
        [
            "",
            "## Source Registry",
            "",
        ]
    )
    for bench in BENCHMARKS:
        lines.append(f"- **{bench['name']}**: {bench['primary_source']}")
        lines.append(f"  - Scope: {bench['scope_note']}")
        for src in bench["publicly_used_by"]:
            lines.append(f"  - Public usage signal: {src['system']} -> {src['source']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ns = _parse_args()
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    proxy_path = repo_root / ns.proxy_summary
    proxy_summary = _load_json(proxy_path)
    rows = _coverage_rows(proxy_summary)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "proxy_summary_path": str(proxy_path),
        "rows": rows,
    }

    out_json = repo_root / ns.output_json
    out_md = repo_root / ns.output_md
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_md.write_text(_render_markdown(rows, str(proxy_path)), encoding="utf-8")

    runnable = sum(1 for r in rows if r["mapu_runnable_now"])
    print(
        json.dumps(
            {
                "output_json": str(out_json),
                "output_md": str(out_md),
                "runnable_now": runnable,
                "benchmarks_total": len(rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
