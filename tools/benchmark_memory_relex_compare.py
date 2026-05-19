from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mapu.config import Settings
from mapu.db.engine import build_engine
from mapu.evaluation.cases import ALL_BENCHMARK_CASES
from mapu.evaluation.runner import BenchmarkRunner
from mapu.evaluation.types import CaseResult, EvalPhase, SuiteResult
from mapu.extraction import get_default_extractors
from mapu.providers import embeddings as embedding_module
from mapu.providers.embeddings import get_default_embedding_provider

MEMORY_LIKE_TAGS = {
    "amendment",
    "supersession",
    "cross_reference",
    "changelog",
    "migration",
    "step_down",
    "cure_right",
    "drug_interaction",
    "mechanism",
    "clinical_significance",
}


def _memory_like_cases() -> list[Any]:
    return [
        c for c in ALL_BENCHMARK_CASES
        if any(tag in MEMORY_LIKE_TAGS for tag in c.tags)
    ]


def _set_mode(use_relex: bool) -> None:
    os.environ["MAPU_EXTRACTION_GLINER_ENABLED"] = "false"
    os.environ["MAPU_EXTRACTION_SETFIT_ENABLED"] = "false"
    os.environ["MAPU_EXTRACTION_LLM_ENABLED"] = "false"
    os.environ["MAPU_EXTRACTION_GLINER_RELEX_ENABLED"] = "true" if use_relex else "false"
    os.environ["MAPU_EXTRACTION_GLINER_RELEX_ENTITY_THRESHOLD"] = "0.35"
    os.environ["MAPU_EXTRACTION_GLINER_RELEX_RELATION_THRESHOLD"] = "0.6"
    os.environ["MAPU_EXTRACTION_GLINER_RELEX_CALIBRATION"] = "0.75"

    # Reset process-global provider cache so each run picks up fresh settings cleanly.
    embedding_module._cached_embedding_provider = None


def _phase(case: CaseResult, phase: EvalPhase) -> dict[str, object] | None:
    for p in case.phases:
        if p.phase == phase:
            return p.details
    return None


def _case_summary(case: CaseResult) -> dict[str, Any]:
    ext = _phase(case, EvalPhase.EXTRACTION) or {}
    qry = _phase(case, EvalPhase.QUERY) or {}
    truth = _phase(case, EvalPhase.TRUTH) or {}
    return {
        "case_id": case.case_id,
        "domain": case.domain,
        "errors": case.errors,
        "metrics": case.metrics,
        "extraction": {
            "propositions_extracted": ext.get("propositions_extracted"),
            "proposition_f1": ext.get("proposition_f1"),
            "entity_f1": ext.get("entity_f1"),
            "extraction_errors": ext.get("extraction_errors", []),
        },
        "query": {
            "query_f1": qry.get("query_f1"),
            "rank_violation_rate": qry.get("rank_violation_rate"),
            "epistemic_status": qry.get("epistemic_status"),
        },
        "truth": {
            "truth_accuracy": truth.get("truth_accuracy"),
        },
    }


async def _run_suite(use_relex: bool) -> SuiteResult:
    _set_mode(use_relex)
    settings = Settings()
    _engine, session_factory = build_engine(settings.database)

    cases = _memory_like_cases()
    async with session_factory() as session:
        runner = BenchmarkRunner(
            session=session,
            embedding_provider=get_default_embedding_provider(),
            extractors=get_default_extractors(),
        )
        return await runner.run_suite(
            cases,
            suite_name="memory_like_relex_on" if use_relex else "memory_like_relex_off",
        )


def _compare(on: SuiteResult, off: SuiteResult) -> dict[str, Any]:
    by_id_on = {c.case_id: c for c in on.case_results}
    by_id_off = {c.case_id: c for c in off.case_results}
    case_deltas: list[dict[str, Any]] = []
    for case_id in sorted(by_id_on):
        c_on = by_id_on[case_id]
        c_off = by_id_off.get(case_id)
        if c_off is None:
            continue
        case_deltas.append(
            {
                "case_id": case_id,
                "on": _case_summary(c_on),
                "off": _case_summary(c_off),
                "delta": {
                    "query_f1": (
                        c_on.metrics.get("query.query_f1", 0.0)
                        - c_off.metrics.get("query.query_f1", 0.0)
                    ),
                    "extraction_entity_f1": (
                        c_on.metrics.get("extraction.entity_f1", 0.0)
                        - c_off.metrics.get("extraction.entity_f1", 0.0)
                    ),
                    "extraction_proposition_f1": (
                        c_on.metrics.get("extraction.proposition_f1", 0.0)
                        - c_off.metrics.get("extraction.proposition_f1", 0.0)
                    ),
                },
            }
        )
    return {
        "aggregate_on": on.aggregate_metrics,
        "aggregate_off": off.aggregate_metrics,
        "cases": case_deltas,
    }


async def _main() -> dict[str, Any]:
    off = await _run_suite(use_relex=False)
    on = await _run_suite(use_relex=True)
    return _compare(on, off)


if __name__ == "__main__":
    output = asyncio.run(_main())
    print(json.dumps(output, indent=2))
