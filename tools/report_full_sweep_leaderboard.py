from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_result(dir_path: Path, stem: str, project_name: str) -> Path | None:
    files = sorted(dir_path.glob(f"{stem}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        try:
            data = _load_json(f)
        except Exception:
            continue
        if str(data.get("metadata", {}).get("project_name", "")) == project_name:
            return f
    return None


def _acc(data: dict[str, Any], cutoff: str) -> float | None:
    overall = data.get("metrics_by_cutoff", {}).get(cutoff, {}).get("overall", {})
    if "accuracy" in overall:
        return float(overall["accuracy"])
    if "pass_rate" in overall:
        return float(overall["pass_rate"])
    return None


def _print_pair(label: str, ours: float | None, baseline: float | None) -> None:
    if ours is None and baseline is None:
        print(f"{label:<28} ours=NA baseline=NA delta=NA")
        return
    if ours is None:
        print(f"{label:<28} ours=NA baseline={baseline:7.3f} delta=NA")
        return
    if baseline is None:
        print(f"{label:<28} ours={ours:7.3f} baseline=NA delta=NA")
        return
    delta = ours - baseline
    print(f"{label:<28} ours={ours:7.3f} baseline={baseline:7.3f} delta={delta:+7.3f}")


def main() -> None:
    suffix = os.getenv("MAPU_BENCH_PROJECT_SUFFIX", "v2")
    model_label = os.getenv("MAPU_BENCH_MODEL_LABEL", "qwen06")
    ours_locomo_path = _latest_result(
        ROOT / "results" / "locomo",
        "locomo_results",
        f"mapu_fullsweep_{model_label}_locomo_{suffix}",
    )
    ours_longmem_path = _latest_result(
        ROOT / "results" / "longmemeval",
        "longmemeval_results",
        f"mapu_fullsweep_{model_label}_longmemeval_{suffix}",
    )
    ours_beam_100k_path = _latest_result(
        ROOT / "results" / "beam",
        "beam_results",
        f"mapu_fullsweep_{model_label}_beam_100k_{suffix}",
    )
    ours_beam_500k_path = _latest_result(
        ROOT / "results" / "beam",
        "beam_results",
        f"mapu_fullsweep_{model_label}_beam_500k_{suffix}",
    )
    ours_beam_1m_path = _latest_result(
        ROOT / "results" / "beam",
        "beam_results",
        f"mapu_fullsweep_{model_label}_beam_1m_{suffix}",
    )
    ours_beam_10m_path = _latest_result(
        ROOT / "results" / "beam",
        "beam_results",
        f"mapu_fullsweep_{model_label}_beam_10m_{suffix}",
    )

    baseline_dir = ROOT / ".tmp" / "memory-benchmarks" / "results" / "platform"
    baseline_locomo_200 = _load_json(baseline_dir / "locomo_results.json")
    baseline_locomo_50 = _load_json(baseline_dir / "locomo_top50_results.json")
    baseline_longmem_200 = _load_json(baseline_dir / "longmemeval_results.json")
    baseline_longmem_50 = _load_json(baseline_dir / "longmemeval_top50_results.json")
    baseline_beam_1m_200 = _load_json(baseline_dir / "beam_1m_results.json")
    baseline_beam_1m_50 = _load_json(baseline_dir / "beam_1m_top50_results.json")
    baseline_beam_10m_200 = _load_json(baseline_dir / "beam_10m_results.json")
    baseline_beam_10m_50 = _load_json(baseline_dir / "beam_10m_top50_results.json")

    print("=== Full Sweep Leaderboard Comparison ===")
    print()

    if ours_locomo_path:
        ours = _load_json(ours_locomo_path)
        print(f"LoCoMo ours file: {ours_locomo_path.name}")
        _print_pair("LoCoMo top_200", _acc(ours, "top_200"), _acc(baseline_locomo_200, "top_200"))
        _print_pair("LoCoMo top_50", _acc(ours, "top_50"), _acc(baseline_locomo_50, "top_50"))
        _print_pair("LoCoMo top_10", _acc(ours, "top_10"), None)
    else:
        print("LoCoMo ours file: MISSING")
    print()

    if ours_longmem_path:
        ours = _load_json(ours_longmem_path)
        print(f"LongMemEval ours file: {ours_longmem_path.name}")
        _print_pair("LongMem top_200", _acc(ours, "top_200"), _acc(baseline_longmem_200, "top_200"))
        _print_pair("LongMem top_50", _acc(ours, "top_50"), _acc(baseline_longmem_50, "top_50"))
        _print_pair("LongMem top_10", _acc(ours, "top_10"), None)
    else:
        print("LongMemEval ours file: MISSING")
    print()

    def beam_section(
        name: str,
        ours_path: Path | None,
        b50: dict[str, Any],
        b200: dict[str, Any],
    ) -> None:
        if not ours_path:
            print(f"BEAM {name} ours file: MISSING")
            print()
            return
        ours = _load_json(ours_path)
        print(f"BEAM {name} ours file: {ours_path.name}")
        _print_pair(f"BEAM {name} top_200", _acc(ours, "top_200"), _acc(b200, "top_200"))
        _print_pair(f"BEAM {name} top_50", _acc(ours, "top_50"), _acc(b50, "top_50"))
        _print_pair(f"BEAM {name} top_10", _acc(ours, "top_10"), None)
        print()

    beam_section("100K", ours_beam_100k_path, baseline_beam_1m_50, baseline_beam_1m_200)
    beam_section("500K", ours_beam_500k_path, baseline_beam_1m_50, baseline_beam_1m_200)
    beam_section("1M", ours_beam_1m_path, baseline_beam_1m_50, baseline_beam_1m_200)
    beam_section("10M", ours_beam_10m_path, baseline_beam_10m_50, baseline_beam_10m_200)


if __name__ == "__main__":
    main()
