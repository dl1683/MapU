from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any


def _normalize(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _token_set(text: str) -> set[str]:
    return {tok for tok in _normalize(text).split() if tok}


def _contains_answer(answer: str, memory: str) -> bool:
    a = _normalize(answer)
    m = _normalize(memory)
    if not a or not m:
        return False
    if a in m:
        return True
    a_toks = _token_set(answer)
    m_toks = _token_set(memory)
    if not a_toks or not m_toks:
        return False
    overlap = len(a_toks & m_toks) / max(1, len(a_toks))
    return overlap >= 0.8


def _expected_nuggets(gt: str) -> list[str]:
    text = gt.strip()
    if not text:
        return []
    low = text.lower()
    nuggets: list[str] = []

    # BEAM-style labels: "llm response should state: X | ...".
    if "llm response should" in low:
        for chunk in re.split(r"\s*\|\s*", text):
            m = re.search(
                r"llm response should (?:state|contain)\s*:\s*(.+)$",
                chunk,
                flags=re.IGNORECASE,
            )
            if m:
                cand = m.group(1).strip().strip("'\"")
                if cand:
                    nuggets.append(cand)
        if nuggets:
            return nuggets

    # LongMemEval / others can be direct answer text.
    return [text]


def _score_file(path: pathlib.Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    gt = str(obj.get("ground_truth_answer", "")).strip()
    retrieval = obj.get("retrieval") or {}
    rows = retrieval.get("search_results") or []
    memories = [str(r.get("memory", "")) for r in rows]
    abstention = bool(obj.get("is_abstention", False)) or (
        "no information related" in _normalize(gt)
    )
    if abstention:
        # abstention is good when retrieval is empty or weak.
        if not memories:
            return {"file": str(path), "support_hit": True, "abstention": True}
        top_tokens = _token_set(memories[0])
        q_tokens = _token_set(str(obj.get("question", "")))
        overlap = len(top_tokens & q_tokens) / max(1, len(q_tokens))
        # If top retrieval has weak query overlap, treat as abstention-friendly.
        return {
            "file": str(path),
            "support_hit": overlap < 0.25,
            "abstention": True,
        }

    nuggets = _expected_nuggets(gt)
    nugget_hits = 0
    for nug in nuggets:
        if any(_contains_answer(nug, mem) for mem in memories):
            nugget_hits += 1
    support = nugget_hits >= max(1, int(len(nuggets) * 0.5))
    return {
        "file": str(path),
        "support_hit": support,
        "abstention": False,
        "nuggets": len(nuggets),
        "nugget_hits": nugget_hits,
    }


def _score_dir(base_dir: pathlib.Path) -> dict[str, Any]:
    files = sorted(base_dir.glob("*.json"))
    rows = [_score_file(p) for p in files if not p.name.startswith("_ingestion_")]
    if not rows:
        return {"dir": str(base_dir), "count": 0, "support_hit_rate": 0.0}
    count = len(rows)
    hits = sum(1 for r in rows if r["support_hit"])
    abstentions = sum(1 for r in rows if r["abstention"])
    nugget_total = sum(int(r.get("nuggets", 0)) for r in rows)
    nugget_hits = sum(int(r.get("nugget_hits", 0)) for r in rows)
    return {
        "dir": str(base_dir),
        "count": count,
        "abstention_count": abstentions,
        "support_hits": hits,
        "support_hit_rate": hits / count,
        "nugget_hit_rate": (nugget_hits / nugget_total) if nugget_total else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Proxy scorer for memory benchmark retrieval outputs.",
    )
    parser.add_argument("--locomo-dir", default="")
    parser.add_argument("--longmemeval-dir", default="")
    parser.add_argument("--beam-dir", default="")
    parser.add_argument(
        "--output-json",
        default="results/matrix/retrieval_proxy_summary.json",
    )
    ns = parser.parse_args()

    reports: dict[str, Any] = {}
    for key, path_str in (
        ("locomo", ns.locomo_dir),
        ("longmemeval", ns.longmemeval_dir),
        ("beam", ns.beam_dir),
    ):
        if path_str:
            reports[key] = _score_dir(pathlib.Path(path_str))

    out = pathlib.Path(ns.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
