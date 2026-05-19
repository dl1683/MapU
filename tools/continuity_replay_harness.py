from __future__ import annotations

import argparse
import ast
import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mapu.client import AsyncMapUClient
from mapu.config import Settings
from mapu.context_learning import build_handoff_bundle
from mapu.db.engine import build_engine
from mapu.repos.audit import ActivityRepo
from mapu.repos.gap import GapRepo


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a two-session MapU continuity replay harness.",
    )
    parser.add_argument("--corpus-id", required=True, help="Target corpus UUID.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="REST API base URL.")
    parser.add_argument(
        "--session1-questions",
        nargs="+",
        default=[
            "summarize the repository",
            "who are the main actors?",
        ],
        help="Queries for baseline session.",
    )
    parser.add_argument(
        "--session2-question",
        default="",
        help="Optional extra question to execute after handoff action replay.",
    )
    parser.add_argument("--max-gaps", type=int, default=10)
    parser.add_argument("--max-activity", type=int, default=20)
    parser.add_argument("--max-actions", type=int, default=8)
    parser.add_argument(
        "--max-executed-actions",
        type=int,
        default=4,
        help="Maximum number of handoff actions to execute in session2.",
    )
    parser.add_argument(
        "--out",
        default="results/continuity_replay_harness.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--require-read-reduction-gate",
        action="store_true",
        help="Fail the harness if the session2 baseline-read estimate is not reduced.",
    )
    parser.add_argument(
        "--require-frontier-completeness-gate",
        action="store_true",
        help="Fail the harness if the handoff frontier is partial or missing gap contracts.",
    )
    parser.add_argument(
        "--require-response-quality-gate",
        action="store_true",
        help=(
            "Fail the harness unless resumed query/investigation actions return "
            "non-empty answer text, next-step guidance, and evidence signals."
        ),
    )
    parser.add_argument(
        "--min-quality-pass-rate",
        type=float,
        default=1.0,
        help="Minimum response-quality pass rate required by --require-response-quality-gate.",
    )
    parser.add_argument(
        "--min-estimated-read-delta",
        type=float,
        default=0.0,
        help="Minimum estimated_read_delta required to pass the reduction gate.",
    )
    parser.add_argument("--no-lifecycle-query", action="store_true", help="Skip REST queries.")
    return parser.parse_args()


@dataclass
class SessionRecord:
    label: str
    wall_ms: float
    handoff_action_count: int
    api_calls: int
    estimated_read_calls: float
    top_actions: list[str]
    executed_actions: list[dict[str, Any]]
    frontier_action_count: int
    open_gap_count: int
    unresolved_conflict_count: int
    resumed_from_handoff: bool
    frontier_completeness: str = ""
    continuity_status: str = ""
    missing_gap_contract_count: int = 0
    evidence_anchor_count: int = 0


@dataclass
class ActionExecution:
    action_type: str
    step: str
    success: bool
    wall_ms: float
    estimated_read_calls: float
    result_count: int
    error: str | None = None
    quality: dict[str, Any] = field(default_factory=dict)


HANDOFF_ACTION_TYPES = {"query", "investigate", "list_activity", "list_gaps"}
READ_CALL_WEIGHTS = {
    "query": 1.0,
    "investigate": 1.0,
    "list_activity": 0.25,
    "list_gaps": 0.25,
}


def _coerce_uuid(value: str) -> str:
    # Keep errors explicit and deterministic for harness logs.
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise ValueError(f"Invalid UUID in harness arguments: {value!r}") from exc


def _to_str(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_int(value: object, default: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return default


def _coerce_uuid_opt(value: object) -> str | None:
    if value is None:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


def _resolve_action_corpus_id(parsed_value: object, expected_corpus_id: str) -> str:
    parsed = _coerce_uuid_opt(parsed_value)
    if parsed is None:
        return expected_corpus_id
    if parsed != expected_corpus_id:
        raise ValueError(
            "Handoff action corpus_id does not match harness corpus: "
            f"{parsed} != {expected_corpus_id}"
        )
    return parsed


def _coerce_seq_of_strings(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _count_collection_items(payload: Any) -> int:
    if payload is None:
        return 0
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return sum(len(v) for v in payload.values() if isinstance(v, list))
    return 0


def _count_any_list(payload: dict[str, Any], *keys: str) -> int:
    total = 0
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list | tuple):
            total += len(value)
    return total


def _text_field(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _response_quality(action_type: str, payload: Any) -> dict[str, Any]:
    if action_type not in {"query", "investigate"}:
        return {"required": False, "passed": True, "reason": "not a response action"}
    if not isinstance(payload, dict):
        return {
            "required": True,
            "passed": False,
            "reason": "response payload is not an object",
        }

    answer_text = _text_field(payload, "answer", "synthesis", "summary", "finding")
    next_steps = _count_any_list(payload, "next_steps", "structured_next_steps")
    evidence = _count_any_list(
        payload,
        "chunk_hits",
        "evidence",
        "findings",
        "issue_coverage",
        "leads",
        "gaps",
        "hits",
    )
    checks = {
        "answer_nonempty": bool(answer_text),
        "next_steps_present": next_steps > 0,
        "evidence_present": evidence > 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "required": True,
        "passed": not failures,
        "checks": checks,
        "answer_chars": len(answer_text),
        "next_step_count": next_steps,
        "evidence_count": evidence,
        "reason": "passed" if not failures else ", ".join(failures),
    }


def _frontier_contract_snapshot(frontier: dict[str, Any]) -> dict[str, Any]:
    completeness = str(frontier.get("frontier_completeness") or "unknown")
    missing_contracts = int(frontier.get("missing_gap_contract_count") or 0)
    evidence_anchors = int(frontier.get("evidence_anchor_count") or 0)
    status = str(frontier.get("continuity_status") or "unknown")
    passed = completeness == "complete" and missing_contracts == 0
    reason = "passed"
    if not passed:
        reason = (
            f"frontier_completeness={completeness}; missing_gap_contract_count={missing_contracts}"
        )
    return {
        "frontier_completeness": completeness,
        "continuity_status": status,
        "missing_gap_contract_count": missing_contracts,
        "evidence_anchor_count": evidence_anchors,
        "passed": passed,
        "reason": reason,
    }


def _parse_action_step(step: str) -> tuple[str, dict[str, Any]]:
    try:
        node = ast.parse(_to_str(step), mode="eval").body
    except SyntaxError as exc:
        raise ValueError(f"Invalid action step syntax: {exc}") from exc

    if not isinstance(node, ast.Call):
        raise ValueError("Action step must be a function-style call.")
    if not isinstance(node.func, ast.Name):
        raise ValueError("Action command must use a plain function name.")

    action_type = node.func.id
    if action_type not in HANDOFF_ACTION_TYPES:
        raise ValueError(f"Unsupported action type: {action_type}")

    def _literal(expression: ast.AST) -> Any:
        if isinstance(expression, ast.Constant):
            return expression.value
        if isinstance(expression, ast.List):
            return [_literal(item) for item in expression.elts]
        if isinstance(expression, ast.Tuple):
            return tuple(_literal(item) for item in expression.elts)
        if isinstance(expression, ast.Name):
            if expression.id == "None":
                return None
            if expression.id == "True":
                return True
            if expression.id == "False":
                return False
            raise ValueError(f"Unsupported symbol in action step: {expression.id}")
        raise ValueError("Unsupported action payload expression.")

    params: dict[str, Any] = {}
    if node.args:
        params["corpus_id"] = _literal(node.args[0])
    for keyword in node.keywords:
        if keyword.arg is None:
            continue
        params[keyword.arg] = _literal(keyword.value)

    return action_type, params


async def _execute_handoff_action(
    client: AsyncMapUClient,
    corpus_id: str,
    step: str,
) -> ActionExecution:
    start = datetime.now(UTC)
    try:
        action_type, params = _parse_action_step(step)
    except ValueError as exc:
        return ActionExecution(
            action_type="parse_error",
            step=str(step),
            success=False,
            wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
            estimated_read_calls=0.0,
            result_count=0,
            error=str(exc),
        )

    parsed_corpus = params.get("corpus_id")
    try:
        canonical_corpus_id = _resolve_action_corpus_id(parsed_corpus, corpus_id)
    except ValueError as exc:
        return ActionExecution(
            action_type=action_type,
            step=step,
            success=False,
            wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
            estimated_read_calls=0.0,
            result_count=0,
            error=str(exc),
        )

    if action_type == "query":
        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=False,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=0.0,
                result_count=0,
                error="query action missing a question.",
            )
        try:
            result = await client.query(
                uuid.UUID(canonical_corpus_id),
                question=question,
                max_results=_parse_int(params.get("max_results"), 20),
            )
            quality = _response_quality(action_type, result)
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=True,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=READ_CALL_WEIGHTS[action_type],
                result_count=_count_collection_items(result),
                quality=quality,
            )
        except Exception as exc:  # pragma: no cover - transport-level failure path
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=False,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=0.0,
                result_count=0,
                error=str(exc),
            )

    if action_type == "investigate":
        question = params.get("question")
        if not isinstance(question, str) or not question.strip():
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=False,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=0.0,
                result_count=0,
                error="investigate action missing a question.",
            )
        try:
            result = await client.investigate(
                uuid.UUID(canonical_corpus_id),
                question=question,
                initial_predicates=_coerce_seq_of_strings(params.get("initial_predicates")) or None,
                initial_entities=_coerce_seq_of_strings(params.get("initial_entities")) or None,
                max_actions=_parse_int(params.get("max_actions"), 25),
            )
            quality = _response_quality(action_type, result)
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=True,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=READ_CALL_WEIGHTS[action_type],
                result_count=_count_collection_items(result),
                quality=quality,
            )
        except Exception as exc:  # pragma: no cover - transport-level failure path
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=False,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=0.0,
                result_count=0,
                error=str(exc),
            )

    if action_type == "list_activity":
        entity_id = _coerce_uuid_opt(params.get("entity_id"))
        event_type = params.get("event_type")
        entity_type = params.get("entity_type")
        try:
            result = await client.list_activity(
                uuid.UUID(canonical_corpus_id),
                limit=_parse_int(params.get("limit"), 50),
                event_type=event_type if isinstance(event_type, str) else None,
                entity_type=entity_type if isinstance(entity_type, str) else None,
                entity_id=uuid.UUID(entity_id) if entity_id else None,
            )
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=True,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=READ_CALL_WEIGHTS[action_type],
                result_count=_count_collection_items(result),
            )
        except Exception as exc:  # pragma: no cover - transport-level failure path
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=False,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=0.0,
                result_count=0,
                error=str(exc),
            )

    if action_type == "list_gaps":
        status = params.get("status")
        kind = params.get("kind")
        severity = params.get("severity")
        try:
            result = await client.list_gaps(
                uuid.UUID(canonical_corpus_id),
                status=status if isinstance(status, str) else "open",
                kind=kind if isinstance(kind, str) else None,
                severity=severity if isinstance(severity, str) else None,
                limit=_parse_int(params.get("limit"), 100),
            )
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=True,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=READ_CALL_WEIGHTS[action_type],
                result_count=_count_collection_items(result),
            )
        except Exception as exc:  # pragma: no cover - transport-level failure path
            return ActionExecution(
                action_type=action_type,
                step=step,
                success=False,
                wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                estimated_read_calls=0.0,
                result_count=0,
                error=str(exc),
            )

    return ActionExecution(
        action_type=action_type,
        step=step,
        success=False,
        wall_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
        estimated_read_calls=0.0,
        result_count=0,
        error=f"Unhandled action type '{action_type}'.",
    )


async def _read_handoff(
    session_factory: Any,
    corpus_id: str,
    max_gaps: int,
    max_activity: int,
    max_actions: int,
) -> dict[str, Any]:
    async with session_factory() as session:
        gap_repo = GapRepo(session, corpus_id)
        activity_repo = ActivityRepo(session, corpus_id)
        gaps = await gap_repo.list(status="open", limit=max_gaps)
        activities = await activity_repo.list(limit=max_activity)
        return build_handoff_bundle(
            corpus_id=corpus_id,
            gaps=tuple(gaps),
            activities=activities,
            max_gaps=max_gaps,
            max_activity=max_activity,
            max_actions=max_actions,
        )


async def _session_baseline(
    client: AsyncMapUClient,
    corpus_id: str,
    questions: list[str],
) -> SessionRecord:
    api_calls = 0
    start = datetime.now(UTC)
    top_actions: list[str] = []
    executed_actions: list[dict[str, Any]] = []
    estimated_read_calls = 0.0

    for question in questions:
        answer = await client.query(corpus_id, question)
        quality = _response_quality("query", answer)
        api_calls += 1
        estimated_read_calls += 1.0
        next_steps = answer.get("next_steps", [])
        if isinstance(next_steps, list):
            top_actions.extend(next_steps[:2])
        executed_actions.append(
            {
                "action_type": "query",
                "step": f"query(corpus_id='{corpus_id}', question='{question}')",
                "success": True,
                "estimated_read_calls": 1.0,
                "result_count": _count_collection_items(answer),
                "quality": quality,
            }
        )
    elapsed = (datetime.now(UTC) - start).total_seconds() * 1000

    return SessionRecord(
        label="session1_baseline",
        wall_ms=elapsed,
        handoff_action_count=0,
        api_calls=api_calls,
        estimated_read_calls=estimated_read_calls,
        top_actions=top_actions,
        executed_actions=executed_actions,
        frontier_action_count=0,
        open_gap_count=0,
        unresolved_conflict_count=0,
        resumed_from_handoff=False,
        frontier_completeness="baseline",
        continuity_status="baseline",
    )


async def _session_resume(
    client: AsyncMapUClient,
    handoff: dict[str, Any],
    corpus_id: str,
    resume_question: str,
    max_actions: int,
) -> SessionRecord:
    frontier = handoff.get("continuity_frontier", {})
    frontier_contract = _frontier_contract_snapshot(frontier)
    priority_actions = handoff.get("priority_next_actions", [])
    action_steps = [a.get("step") for a in priority_actions[:max_actions] if isinstance(a, dict)]

    executed: list[dict[str, Any]] = []
    executed_read_calls = 0.0
    top_actions: list[str] = []

    start = datetime.now(UTC)
    for step in action_steps:
        action_exec = await _execute_handoff_action(client, corpus_id, step)
        executed.append(asdict(action_exec))
        if action_exec.success:
            executed_read_calls += action_exec.estimated_read_calls
            top_actions.append(action_exec.step)

    if resume_question.strip():
        # Optional user-directed follow-up question after replay.
        safe_resume_q = str(resume_question).replace("'", "\\'")
        extra = await _execute_handoff_action(
            client,
            corpus_id,
            f"query(corpus_id='{corpus_id}', question='{safe_resume_q}')",
        )
        executed.append(asdict(extra))
        if extra.success:
            executed_read_calls += extra.estimated_read_calls

    wall_ms = (datetime.now(UTC) - start).total_seconds() * 1000
    return SessionRecord(
        label="session2_resumed",
        wall_ms=wall_ms,
        handoff_action_count=len(priority_actions),
        api_calls=len(executed),
        estimated_read_calls=executed_read_calls,
        top_actions=top_actions,
        executed_actions=executed,
        frontier_action_count=len(priority_actions),
        open_gap_count=int(frontier.get("open_gap_count", 0) or 0),
        unresolved_conflict_count=int(frontier.get("unresolved_conflict_count", 0) or 0),
        resumed_from_handoff=True,
        frontier_completeness=frontier_contract["frontier_completeness"],
        continuity_status=frontier_contract["continuity_status"],
        missing_gap_contract_count=frontier_contract["missing_gap_contract_count"],
        evidence_anchor_count=frontier_contract["evidence_anchor_count"],
    )


def _build_handoff_effect(
    session1: SessionRecord,
    session2: SessionRecord,
    required_min_delta: float = 0.0,
    enforce_gate: bool = False,
    enforce_frontier_gate: bool = False,
    enforce_quality_gate: bool = False,
    min_quality_pass_rate: float = 1.0,
) -> dict[str, Any]:
    estimated_read_delta = session1.estimated_read_calls - session2.estimated_read_calls
    passed_gate = estimated_read_delta >= required_min_delta
    if session2.estimated_read_calls <= 0:
        passed_gate = False
    frontier_gate_passed = (
        session2.frontier_completeness == "complete" and session2.missing_gap_contract_count == 0
    )
    quality_summary = _response_quality_summary(session2, min_quality_pass_rate)
    return {
        "api_calls_delta": session1.api_calls - session2.api_calls,
        "estimated_read_delta": estimated_read_delta,
        "top_action_count_delta": len(session1.top_actions) - session2.handoff_action_count,
        "resumed_with_handoff": session2.resumed_from_handoff,
        "unresolved_gaps_carried": session2.open_gap_count,
        "unresolved_conflicts_carried": session2.unresolved_conflict_count,
        "frontier_quality": {
            "frontier_completeness": session2.frontier_completeness,
            "continuity_status": session2.continuity_status,
            "missing_gap_contract_count": session2.missing_gap_contract_count,
            "evidence_anchor_count": session2.evidence_anchor_count,
        },
        "read_reduction_gate": {
            "enabled": bool(enforce_gate),
            "required_min_delta": required_min_delta,
            "passed": bool(passed_gate),
            "reason": (
                "passed"
                if passed_gate
                else (
                    "estimated_read_delta="
                    f"{estimated_read_delta:.4f} < "
                    f"required_min_delta={required_min_delta:.4f}"
                )
            ),
        },
        "handoff_passed_read_reduction_gate": bool(passed_gate),
        "frontier_completeness_gate": {
            "enabled": bool(enforce_frontier_gate),
            "passed": bool(frontier_gate_passed),
            "reason": (
                "passed"
                if frontier_gate_passed
                else (
                    f"frontier_completeness={session2.frontier_completeness}; "
                    f"missing_gap_contract_count={session2.missing_gap_contract_count}"
                )
            ),
        },
        "handoff_passed_frontier_completeness_gate": bool(frontier_gate_passed),
        "response_quality_gate": {
            "enabled": bool(enforce_quality_gate),
            **quality_summary,
        },
        "handoff_passed_response_quality_gate": bool(quality_summary["passed"]),
    }


def _response_quality_summary(
    session: SessionRecord,
    min_quality_pass_rate: float,
) -> dict[str, Any]:
    response_actions = [
        action
        for action in session.executed_actions
        if action.get("action_type") in {"query", "investigate"}
    ]
    quality_records: list[dict[str, Any]] = []
    for action in response_actions:
        quality = action.get("quality")
        if isinstance(quality, dict) and quality.get("required") is True:
            quality_records.append(quality)
            continue
        quality_records.append(
            {
                "required": True,
                "passed": False,
                "reason": action.get("error") or "response action did not return quality evidence",
            }
        )
    required = len(quality_records)
    passed = sum(1 for quality in quality_records if quality.get("passed") is True)
    pass_rate = passed / required if required else 0.0
    failing = [
        {
            "action_type": action.get("action_type"),
            "step": action.get("step"),
            "reason": quality.get("reason"),
        }
        for action, quality in zip(response_actions, quality_records, strict=False)
        if quality.get("passed") is not True
    ]
    gate_passed = required > 0 and pass_rate >= min_quality_pass_rate and not failing
    return {
        "required_action_count": required,
        "passed_action_count": passed,
        "pass_rate": pass_rate,
        "required_min_pass_rate": min_quality_pass_rate,
        "passed": gate_passed,
        "failing_actions": failing[:10],
        "reason": (
            "passed"
            if gate_passed
            else (
                "no query/investigation response actions were executed"
                if required == 0
                else (
                    f"pass_rate={pass_rate:.4f} < "
                    f"required_min_pass_rate={min_quality_pass_rate:.4f}"
                )
            )
        ),
    }


def _should_fail_on_gate(
    session1: SessionRecord,
    session2: SessionRecord,
    required_min_delta: float,
    enforce_gate: bool,
    enforce_frontier_gate: bool = False,
    enforce_quality_gate: bool = False,
    min_quality_pass_rate: float = 1.0,
) -> tuple[bool, str | None]:
    if not enforce_gate and not enforce_frontier_gate and not enforce_quality_gate:
        return False, None
    handoff_effect = _build_handoff_effect(
        session1=session1,
        session2=session2,
        required_min_delta=required_min_delta,
        enforce_gate=enforce_gate,
        enforce_frontier_gate=enforce_frontier_gate,
        enforce_quality_gate=enforce_quality_gate,
        min_quality_pass_rate=min_quality_pass_rate,
    )
    if enforce_gate and not handoff_effect["handoff_passed_read_reduction_gate"]:
        return (
            True,
            (
                "Continuity replay read-reduction gate failed: "
                f"estimated_read_delta={handoff_effect['estimated_read_delta']:.4f}, "
                f"required_min_delta={required_min_delta:.4f}"
            ),
        )
    if enforce_frontier_gate and not handoff_effect["handoff_passed_frontier_completeness_gate"]:
        frontier_gate = handoff_effect["frontier_completeness_gate"]
        return (
            True,
            f"Continuity frontier completeness gate failed: {frontier_gate['reason']}",
        )
    if enforce_quality_gate and not handoff_effect["handoff_passed_response_quality_gate"]:
        quality_gate = handoff_effect["response_quality_gate"]
        return (
            True,
            f"Continuity response quality gate failed: {quality_gate['reason']}",
        )
    if (not enforce_gate or handoff_effect["handoff_passed_read_reduction_gate"]) and (
        not enforce_frontier_gate or handoff_effect["handoff_passed_frontier_completeness_gate"]
    ) and (
        not enforce_quality_gate or handoff_effect["handoff_passed_response_quality_gate"]
    ):
        return False, None
    return True, "Continuity replay gate failed."


async def run_harness() -> int:
    ns = _parse_args()
    engine, session_factory = build_engine(Settings().database)
    corpus_id = _coerce_uuid(ns.corpus_id)
    report: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "corpus_id": corpus_id,
        "session1": None,
        "session2": None,
        "handoff": None,
    }

    try:
        handoff = await _read_handoff(
            session_factory,
            corpus_id,
            ns.max_gaps,
            ns.max_activity,
            ns.max_actions,
        )
        priority_actions = handoff.get("priority_next_actions", [])
        frontier = handoff.get("continuity_frontier", {})
        frontier_contract = _frontier_contract_snapshot(frontier)
        action_confidences = [
            action.get("confidence")
            for action in priority_actions
            if isinstance(action, dict) and isinstance(action.get("confidence"), (int, float))
        ]
        report["handoff"] = {
            "protocol": handoff.get("protocol"),
            "protocol_version": handoff.get("protocol_version"),
            "continuity_frontier": frontier,
            "priority_next_action_count": len(priority_actions),
            "top_priority_actions": [action.get("step") for action in priority_actions[:3]],
            "score": {
                "max_confidence": max(action_confidences, default=0.0),
                "min_confidence": min(action_confidences, default=0.0),
                "avg_confidence": (
                    sum(action_confidences) / len(action_confidences) if action_confidences else 0.0
                ),
                "frontier_complete": frontier_contract["passed"],
                "missing_gap_contract_count": frontier_contract["missing_gap_contract_count"],
                "evidence_anchor_count": frontier_contract["evidence_anchor_count"],
            },
            "carried_items": {
                "open_gap_count": frontier.get("open_gap_count", 0),
                "unresolved_conflict_count": (frontier.get("unresolved_conflict_count", 0)),
            },
        }

        if not ns.no_lifecycle_query:
            async with AsyncMapUClient(base_url=ns.base_url) as api_client:
                session1 = await _session_baseline(api_client, corpus_id, ns.session1_questions)
                session2 = await _session_resume(
                    api_client,
                    handoff,
                    corpus_id,
                    ns.session2_question,
                    ns.max_executed_actions,
                )
                report["session1"] = asdict(session1)
                report["session2"] = asdict(session2)
                report["handoff_effect"] = _build_handoff_effect(
                    session1=session1,
                    session2=session2,
                    required_min_delta=ns.min_estimated_read_delta,
                    enforce_gate=ns.require_read_reduction_gate,
                    enforce_frontier_gate=ns.require_frontier_completeness_gate,
                    enforce_quality_gate=ns.require_response_quality_gate,
                    min_quality_pass_rate=ns.min_quality_pass_rate,
                )
                exit_code = 0
                fail_harness, fail_reason = _should_fail_on_gate(
                    session1=session1,
                    session2=session2,
                    required_min_delta=ns.min_estimated_read_delta,
                    enforce_gate=ns.require_read_reduction_gate,
                    enforce_frontier_gate=ns.require_frontier_completeness_gate,
                    enforce_quality_gate=ns.require_response_quality_gate,
                    min_quality_pass_rate=ns.min_quality_pass_rate,
                )
                if fail_harness and fail_reason:
                    report["failure_reason"] = fail_reason
                    print(json.dumps({"status": "fail", "reason": fail_reason}, indent=2))
                    exit_code = 1
        else:
            report["session1"] = {
                "label": "session1_baseline",
                "wall_ms": 0.0,
                "api_calls": 0,
                "estimated_read_calls": 0.0,
                "top_actions": [],
                "executed_actions": [],
                "frontier_action_count": 0,
                "open_gap_count": 0,
                "unresolved_conflict_count": 0,
                "resumed_from_handoff": False,
            }
            report["session2"] = {
                "label": "session2_resumed",
                "wall_ms": 0.0,
                "api_calls": 0,
                "estimated_read_calls": 0.0,
                "top_actions": [],
                "executed_actions": [],
                "frontier_action_count": len(handoff.get("priority_next_actions", [])),
                "open_gap_count": int(frontier.get("open_gap_count", 0)) or 0,
                "unresolved_conflict_count": int(frontier.get("unresolved_conflict_count", 0)) or 0,
                "resumed_from_handoff": True,
                "frontier_completeness": frontier_contract["frontier_completeness"],
                "continuity_status": frontier_contract["continuity_status"],
                "missing_gap_contract_count": frontier_contract["missing_gap_contract_count"],
                "evidence_anchor_count": frontier_contract["evidence_anchor_count"],
            }
            report["handoff_effect"] = {
                "api_calls_delta": 0,
                "estimated_read_delta": 0.0,
                "top_action_count_delta": len(report["session1"].get("top_actions", []))
                - report["session2"].get("frontier_action_count", 0),
                "resumed_with_handoff": report["session2"].get("resumed_from_handoff", True),
                "unresolved_gaps_carried": report["session2"].get("open_gap_count", 0),
                "unresolved_conflicts_carried": report["session2"].get(
                    "unresolved_conflict_count",
                    0,
                ),
                "frontier_quality": {
                    "frontier_completeness": report["session2"].get("frontier_completeness"),
                    "continuity_status": report["session2"].get("continuity_status"),
                    "missing_gap_contract_count": report["session2"].get(
                        "missing_gap_contract_count",
                        0,
                    ),
                    "evidence_anchor_count": report["session2"].get(
                        "evidence_anchor_count",
                        0,
                    ),
                },
                "read_reduction_gate": {
                    "enabled": False,
                    "required_min_delta": 0.0,
                    "passed": False,
                    "reason": "lifecycle disabled",
                },
                "handoff_passed_read_reduction_gate": False,
                "frontier_completeness_gate": {
                    "enabled": bool(ns.require_frontier_completeness_gate),
                    "passed": bool(frontier_contract["passed"]),
                    "reason": frontier_contract["reason"],
                },
                "handoff_passed_frontier_completeness_gate": bool(frontier_contract["passed"]),
                "response_quality_gate": {
                    "enabled": bool(ns.require_response_quality_gate),
                    "required_action_count": 0,
                    "passed_action_count": 0,
                    "pass_rate": 0.0,
                    "required_min_pass_rate": ns.min_quality_pass_rate,
                    "passed": False,
                    "failing_actions": [],
                    "reason": "lifecycle disabled",
                },
                "handoff_passed_response_quality_gate": False,
            }
            exit_code = 0
            if ns.require_frontier_completeness_gate and not frontier_contract["passed"]:
                fail_reason = (
                    f"Continuity frontier completeness gate failed: {frontier_contract['reason']}"
                )
                report["failure_reason"] = fail_reason
                print(json.dumps({"status": "fail", "reason": fail_reason}, indent=2))
                exit_code = 1
            if ns.require_response_quality_gate:
                fail_reason = "Continuity response quality gate failed: lifecycle disabled"
                report["failure_reason"] = fail_reason
                print(json.dumps({"status": "fail", "reason": fail_reason}, indent=2))
                exit_code = 1

        # Always persist harness artifacts for evidence and debugging, even on fail.
        report["completed_at"] = datetime.now(UTC).isoformat()
        out_path = Path(ns.out)
        await asyncio.to_thread(out_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(
            out_path.write_text,
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        status_payload = {"status": "ok", "path": str(out_path)}
        if exit_code:
            status_payload = {"status": "fail", "path": str(out_path)}
            if failure_reason := report.get("failure_reason"):
                status_payload["reason"] = failure_reason
        print(json.dumps(status_payload, indent=2))
        return exit_code

    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_harness()))
