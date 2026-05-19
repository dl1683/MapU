from __future__ import annotations

import argparse
import json
import pathlib
import re
from collections import Counter, defaultdict
from typing import Any


def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _expected_nuggets(gt: str) -> list[str]:
    low = gt.lower()
    if "llm response should" in low:
        out: list[str] = []
        for chunk in re.split(r"\s*\|\s*", gt):
            m = re.search(
                r"llm response should (?:state|contain)\s*:\s*(.+)$",
                chunk,
                flags=re.IGNORECASE,
            )
            if m:
                out.append(m.group(1).strip().strip("'\""))
        return out or [gt]
    return [gt]


def _nugget_class(s: str) -> str:
    t = _normalize(s)
    if re.search(r"\b\d+(?:\.\d+)?\b", t):
        if re.search(r"\b(ms|week|day|month|year|commit|port)\b", t):
            return "numeric_metric"
        if re.search(
            r"\b(january|february|march|april|may|june|july|august|september|"
            r"october|november|december|\d{4})\b",
            t,
        ):
            return "date_time"
        return "numeric"
    if any(k in t for k in ("changed", "updated", "from", "to", "latest", "current", "now")):
        return "update_state"
    if any(k in t for k in ("lightweight", "minimal", "avoid", "prefer")):
        return "preference"
    if any(k in t for k in ("should", "must", "recommend", "steps", "security", "libraries")):
        return "instruction"
    if any(k in t for k in ("summary", "implemented", "progress", "milestone", "timeline")):
        return "summary"
    return "other"


def _contains(nugget: str, memory: str) -> bool:
    n = _normalize(nugget)
    m = _normalize(memory)
    if not n or not m:
        return False
    if n in m:
        return True
    nt = {x for x in re.findall(r"[a-z0-9]+", n) if x}
    mt = {x for x in re.findall(r"[a-z0-9]+", m) if x}
    if not nt or not mt:
        return False
    return len(nt & mt) / max(1, len(nt)) >= 0.8


def analyze(dir_path: pathlib.Path) -> dict[str, Any]:
    files = sorted(dir_path.glob("*.json"))
    per_type = Counter()
    per_type_hits = Counter()
    miss_classes = Counter()
    miss_examples: dict[str, list[dict[str, str]]] = defaultdict(list)

    for f in files:
        if f.name.startswith("_ingestion_"):
            continue
        obj = json.loads(f.read_text(encoding="utf-8"))
        qtype = str(obj.get("question_type", "unknown"))
        per_type[qtype] += 1
        gt = str(obj.get("ground_truth_answer", ""))
        memories = [
            str(r.get("memory", ""))
            for r in (obj.get("retrieval", {}).get("search_results") or [])
        ]
        nuggets = _expected_nuggets(gt)
        nug_hits = 0
        for nug in nuggets:
            if any(_contains(nug, mem) for mem in memories):
                nug_hits += 1
            else:
                cls = _nugget_class(nug)
                miss_classes[cls] += 1
                if len(miss_examples[cls]) < 3:
                    miss_examples[cls].append(
                        {
                            "question_type": qtype,
                            "question": str(obj.get("question", ""))[:180],
                            "missing_nugget": nug[:180],
                            "top_memory": (memories[0][:180] if memories else ""),
                        }
                    )
        if nug_hits >= max(1, int(len(nuggets) * 0.5)):
            per_type_hits[qtype] += 1

    rates = {k: per_type_hits[k] / per_type[k] for k in per_type}
    return {
        "dir": str(dir_path),
        "counts": dict(per_type),
        "hit_counts": dict(per_type_hits),
        "hit_rates": rates,
        "missing_nugget_classes": dict(miss_classes),
        "missing_examples": miss_examples,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Analyze BEAM retrieval misses by nugget class.")
    p.add_argument("--beam-dir", required=True)
    p.add_argument("--output-json", default="results/matrix/beam_failure_analysis.json")
    ns = p.parse_args()
    report = analyze(pathlib.Path(ns.beam_dir))
    out = pathlib.Path(ns.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
