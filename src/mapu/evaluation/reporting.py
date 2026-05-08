"""Scorecard reporting: JSON/JSONL output for benchmark results."""

from __future__ import annotations

import json
from pathlib import Path

from mapu.evaluation.types import CaseResult, SuiteResult


def suite_to_dict(result: SuiteResult) -> dict[str, object]:
    return {
        "suite_name": result.suite_name,
        "timestamp": result.timestamp.isoformat(),
        "git_commit": result.git_commit,
        "duration_ms": round(result.duration_ms, 2),
        "aggregate_metrics": {
            k: round(v, 4) for k, v in result.aggregate_metrics.items()
        },
        "cases": [_case_to_dict(c) for c in result.case_results],
    }


def _case_to_dict(result: CaseResult) -> dict[str, object]:
    return {
        "case_id": result.case_id,
        "domain": result.domain,
        "metrics": {k: round(v, 4) for k, v in result.metrics.items()},
        "errors": result.errors,
        "phases": [
            {
                "phase": p.phase.value,
                "success": p.success,
                "duration_ms": round(p.duration_ms, 2),
                "errors": p.errors,
                "details": _serialize_details(p.details),
            }
            for p in result.phases
        ],
    }


def _serialize_details(details: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in details.items():
        if isinstance(v, float):
            out[k] = round(v, 4)
        elif isinstance(v, (str, int, bool)):
            out[k] = v
        elif isinstance(v, list):
            out[k] = [
                round(x, 4) if isinstance(x, float) else x for x in v
            ]
        elif isinstance(v, dict):
            out[k] = _serialize_details(v)
        else:
            out[k] = str(v)
    return out


def write_json_scorecard(result: SuiteResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = result.timestamp.strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"scorecard_{result.suite_name}_{ts}.json"
    data = suite_to_dict(result)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def append_jsonl_entry(result: SuiteResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "benchmark_history.jsonl"
    summary = {
        "suite_name": result.suite_name,
        "timestamp": result.timestamp.isoformat(),
        "git_commit": result.git_commit,
        "duration_ms": round(result.duration_ms, 2),
        "aggregate_metrics": {
            k: round(v, 4) for k, v in result.aggregate_metrics.items()
        },
        "total_cases": len(result.case_results),
        "cases_with_errors": sum(1 for c in result.case_results if c.errors),
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")
    return path


def format_summary(result: SuiteResult) -> str:
    lines = [
        f"Suite: {result.suite_name}",
        f"Commit: {result.git_commit}",
        f"Duration: {result.duration_ms:.0f}ms",
        f"Cases: {len(result.case_results)}",
        "",
    ]

    domain_metrics: dict[str, list[CaseResult]] = {}
    for cr in result.case_results:
        domain_metrics.setdefault(cr.domain, []).append(cr)

    for domain, cases in sorted(domain_metrics.items()):
        lines.append(f"  {domain} ({len(cases)} cases):")
        all_keys: set[str] = set()
        for c in cases:
            all_keys.update(c.metrics.keys())
        for key in sorted(all_keys):
            values = [c.metrics[key] for c in cases if key in c.metrics]
            if values:
                avg = sum(values) / len(values)
                lines.append(f"    {key}: {avg:.3f}")
        error_count = sum(1 for c in cases if c.errors)
        if error_count:
            lines.append(f"    errors: {error_count}/{len(cases)}")
        lines.append("")

    agg = result.aggregate_metrics
    if agg:
        lines.append("Aggregate:")
        for k, v in sorted(agg.items()):
            lines.append(f"  {k}: {v:.4f}")

    return "\n".join(lines)
