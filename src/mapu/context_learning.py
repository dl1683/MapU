"""Helpers for persistent guidance learning in the context map."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from mapu.models.audit import Activity
from mapu.models.gap import Gap
from mapu.types import GapSeverity

HANDOFF_SCHEMA_VERSION = "1.1.0"
GOVERNANCE_TIER_GUARANTEED = "guaranteed"
GOVERNANCE_TIER_PROVISIONAL = "provisional"
GOVERNANCE_TIER_STALE = "stale"
VALID_GOVERNANCE_TIERS = {
    GOVERNANCE_TIER_GUARANTEED,
    GOVERNANCE_TIER_PROVISIONAL,
    GOVERNANCE_TIER_STALE,
}
HANDOFF_MAX_EVENTS_FOR_RANKING = 240
HANDOFF_ACTIVITY_EVENT_TYPES = {
    "supersession",
    "retraction",
    "attestation_rejection",
    "repair_apply",
    "repair_rollback",
    "attestation_review",
}
HANDOFF_CONFLICT_EVENT_TYPES = {"supersession", "retraction", "attestation_rejection"}
HANDOFF_CONFLICT_KEYWORDS = {
    "conflict",
    "contradiction",
    "superseded",
    "supersession",
    "retracted",
    "invalid",
}
HANDOFF_ACTION_ORDER = ("investigate", "query", "list_activity", "list_gaps")
HANDOFF_REQUIRED_GAP_CONTRACT_FIELDS = (
    "uncertainty_reason",
    "evidence_hypothesis",
    "next_action",
    "expected_resolution",
)

POSITIVE_OUTCOMES = {
    "helpful": 2.5,
    "applied": 2.0,
    "partially_helpful": 1.0,
}
NEGATIVE_OUTCOMES = {
    "not_helpful": -2.0,
    "stale": -1.5,
}
VALID_FEEDBACK_OUTCOMES = set(POSITIVE_OUTCOMES) | set(NEGATIVE_OUTCOMES) | {"unknown"}
GAP_SIZE_LIMIT = 6
GAP_SEVERITY_WEIGHT = {
    GapSeverity.CRITICAL: 3.0,
    GapSeverity.MODERATE: 1.5,
    GapSeverity.MINOR: 0.75,
}
GAP_SEVERITY_WEIGHT_BY_TEXT = {
    str(GapSeverity.CRITICAL): 3.0,
    str(GapSeverity.MODERATE): 1.5,
    str(GapSeverity.MINOR): 0.75,
}


def _normalize_severity(severity: str) -> str:
    normalized = (severity or "").strip().lower() or str(GapSeverity.MODERATE)
    if normalized in GAP_SEVERITY_WEIGHT_BY_TEXT:
        return normalized
    return str(GapSeverity.MODERATE)


def _normalize_step(step: str) -> str:
    return " ".join(step.strip().lower().split())


def _normalize_payload_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _payload_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _payload_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _coerce_action_type(value: object, fallback: str = "query") -> str:
    action_type = _normalize_payload_text(value)
    if action_type in HANDOFF_ACTION_ORDER:
        return action_type
    return fallback


def _gap_text_attr(gap: Gap, name: str, default: str = "") -> str:
    value = getattr(gap, name, default)
    if value is None:
        return default
    return " ".join(str(value).strip().split())


def _gap_json_attr(gap: Gap, name: str) -> dict[str, object]:
    return _payload_dict(getattr(gap, name, None))


def _gap_priority_score(gap: Gap) -> float | None:
    value = getattr(gap, "priority_score", None)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _count_evidence_anchors(evidence_hypothesis: Mapping[str, object]) -> int:
    anchors = evidence_hypothesis.get("anchors")
    if isinstance(anchors, list):
        return len([anchor for anchor in anchors if anchor])
    count = 0
    for key in (
        "document_id",
        "span_id",
        "chunk_id",
        "proposition_id",
        "activity_id",
        "changeset_id",
    ):
        if evidence_hypothesis.get(key):
            count += 1
    return count


def _gap_contract_snapshot(gap: Gap) -> dict[str, object]:
    uncertainty_reason = _gap_text_attr(gap, "uncertainty_reason")
    evidence_hypothesis = _gap_json_attr(gap, "evidence_hypothesis")
    next_action = _gap_json_attr(gap, "next_action")
    expected_resolution = _gap_text_attr(gap, "expected_resolution")
    governance_tier = _gap_text_attr(gap, "governance_tier", GOVERNANCE_TIER_PROVISIONAL)
    if governance_tier not in VALID_GOVERNANCE_TIERS:
        governance_tier = GOVERNANCE_TIER_PROVISIONAL

    missing: list[str] = []
    if not uncertainty_reason:
        missing.append("uncertainty_reason")
    if not evidence_hypothesis:
        missing.append("evidence_hypothesis")
    if not next_action:
        missing.append("next_action")
    if not expected_resolution:
        missing.append("expected_resolution")

    last_evaluated_at = getattr(gap, "last_evaluated_at", None)
    return {
        "uncertainty_reason": uncertainty_reason or "missing_evidence",
        "evidence_hypothesis": evidence_hypothesis,
        "next_action": next_action,
        "expected_resolution": expected_resolution,
        "governance_tier": governance_tier,
        "priority_score": _gap_priority_score(gap),
        "missing_contract_fields": missing,
        "is_contract_complete": not missing,
        "evidence_anchor_count": _count_evidence_anchors(evidence_hypothesis),
        "last_evaluated_at": last_evaluated_at.isoformat() if last_evaluated_at else None,
    }


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9_]+", text.lower()))
    return {token for token in tokens if len(token) > 2}


def _question_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a_tokens = _tokenize(a)
    b_tokens = _tokenize(b)
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    if not union:
        return 0.0
    return inter / union


def _recency_weight(event_time: datetime | None) -> float:
    if event_time is None:
        return 1.0
    age_seconds = max((datetime.now(UTC) - event_time).total_seconds(), 0.0)
    age_days = age_seconds / 86_400
    return 1.0 / (1.0 + age_days)


def _to_feedback_signal(details: object) -> tuple[str, float]:
    if not isinstance(details, dict):
        return "", 0.0
    step = _normalize_step(str(details.get("step", "")))
    if not step:
        return "", 0.0
    outcome = str(details.get("outcome", "unknown")).strip().lower()
    if outcome not in VALID_FEEDBACK_OUTCOMES:
        return "", 0.0
    if outcome in POSITIVE_OUTCOMES:
        return step, POSITIVE_OUTCOMES[outcome]
    if outcome in NEGATIVE_OUTCOMES:
        return step, NEGATIVE_OUTCOMES[outcome]
    return step, 0.0


def _normalize_gap_description(description: str) -> str:
    return " ".join(str(description).strip().split())


def _build_gap_step(gap: Gap) -> str:
    desc = _normalize_gap_description(gap.description)
    if not desc:
        return ""
    severity = _normalize_severity(str(gap.severity))
    return f"Investigate open {severity} gap ({gap.kind}): {desc}"


def _score_gap_for_question(gap: Gap, question: str) -> float:
    desc = _normalize_gap_description(gap.description)
    if not desc:
        return 0.0
    similarity = _question_similarity(question, desc)
    severity_norm = _normalize_severity(str(gap.severity))
    severity_weight = GAP_SEVERITY_WEIGHT_BY_TEXT.get(
        severity_norm,
        GAP_SEVERITY_WEIGHT[GapSeverity.MODERATE],
    )
    age_weight = _recency_weight(gap.created_at)
    return severity_weight + (2.0 * similarity) + (0.35 * age_weight)


def suggest_gap_based_next_steps(
    question: str,
    gaps: Sequence[Gap],
    *,
    limit: int = 3,
) -> tuple[str, ...]:
    if not question or not gaps:
        return ()

    scored: list[tuple[float, str]] = []
    for gap in gaps:
        if str(gap.status).lower() != "open":
            continue
        step = _build_gap_step(gap)
        if not step:
            continue
        scored.append((_score_gap_for_question(gap, question), step))

    if not scored:
        return ()

    scored.sort(key=lambda item: item[0], reverse=True)
    dedup: list[str] = []
    seen: set[str] = set()
    for _score, step in scored[: max(GAP_SIZE_LIMIT, limit)]:
        norm = _normalize_step(step)
        if norm in seen:
            continue
        seen.add(norm)
        dedup.append(step)
        if len(dedup) >= limit:
            break
    return tuple(dedup)


def build_structured_next_steps(
    corpus_id: uuid.UUID | str,
    next_steps: Sequence[str],
    *,
    question: str = "",
    gaps: Sequence[str] = (),
    source: str = "query",
) -> tuple[dict[str, object], ...]:
    corpus_id_str = str(corpus_id)
    structured: list[dict[str, object]] = []
    for index, step in enumerate(next_steps):
        step_text = " ".join(str(step or "").strip().split())
        if not step_text:
            continue
        step_lower = step_text.lower()
        if (
            "investigat" in step_lower
            or "coverage stalled" in step_lower
            or "higher budget" in step_lower
        ):
            action_type = "investigate"
        elif step_lower.startswith("list_gaps") or "list gaps" in step_lower:
            action_type = "list_gaps"
        elif step_lower.startswith("list_activity") or "list activity" in step_lower:
            action_type = "list_activity"
        else:
            action_type = "query"

        if (
            "conflict" in step_lower
            or "contradiction" in step_lower
            or "supersession" in step_lower
        ):
            uncertainty_reason = "contradiction_or_supersession"
            governance_tier = GOVERNANCE_TIER_STALE
        elif "no evidence" in step_lower or "missing" in step_lower or "gap" in step_lower:
            uncertainty_reason = "missing_evidence"
            governance_tier = GOVERNANCE_TIER_PROVISIONAL
        elif "budget" in step_lower or "stalled" in step_lower:
            uncertainty_reason = "insufficient_budget"
            governance_tier = GOVERNANCE_TIER_PROVISIONAL
        else:
            uncertainty_reason = "follow_up_quality"
            governance_tier = GOVERNANCE_TIER_PROVISIONAL

        if action_type == "investigate":
            tool_step = _build_tool_step(
                action_type,
                corpus_id_str,
                question=step_text,
                gap_kind="next_step",
            )
            expected_reduction = 0.55
        elif action_type == "list_gaps":
            tool_step = f"list_gaps(corpus_id='{corpus_id_str}', status='open', limit=10)"
            expected_reduction = 0.25
        elif action_type == "list_activity":
            tool_step = f"list_activity(corpus_id='{corpus_id_str}', limit=50)"
            expected_reduction = 0.25
        else:
            tool_step = _build_tool_step(
                action_type,
                corpus_id_str,
                question=step_text,
            )
            expected_reduction = 0.35

        structured.append(
            {
                "action_type": action_type,
                "step": tool_step,
                "rationale": step_text,
                "target": {
                    "source": source,
                    "original_step": step_text,
                    "question": question,
                    "ordinal": index,
                },
                "expected_signal_target": {
                    "source": source,
                    "gaps": list(gaps),
                },
                "expected_resolution": (
                    "Reduce uncertainty identified by this next-step recommendation."
                ),
                "expected_uncertainty_reduction": expected_reduction,
                "uncertainty_reason": uncertainty_reason,
                "governance_tier": governance_tier,
                "source_contract": {
                    "generated_from": "next_steps",
                    "generation_source": source,
                },
            }
        )
    return tuple(structured)


def _collect_historical_steps(details: dict[str, object] | None) -> list[str]:
    raw_steps = []
    if not isinstance(details, dict):
        return raw_steps

    next_steps = details.get("next_steps")
    if isinstance(next_steps, list):
        for step in next_steps:
            if isinstance(step, str):
                raw_steps.append(step)
    return raw_steps


async def prioritize_next_steps(
    next_steps: Sequence[str],
    question: str,
    activities: list[Activity],
    max_events: int = 200,
) -> tuple[str, ...]:
    if not next_steps:
        return ()

    # Keep first-seen copy per normalized step text.
    canonical: dict[str, str] = {}
    base_order: list[str] = []
    for step in next_steps:
        norm = _normalize_step(step)
        if not norm:
            continue
        if norm in canonical:
            continue
        canonical[norm] = step
        base_order.append(norm)

    if not base_order:
        return ()

    scores: dict[str, float] = {}
    for index, norm in enumerate(base_order):
        # Bias toward first-listed local recommendation when history is weak.
        scores[norm] = float(len(base_order) - index)

    if not activities:
        return tuple(
            canonical[norm] for norm in sorted(base_order, key=lambda n: scores[n], reverse=True)
        )

    for activity in activities[:max_events]:
        details = activity.details
        event_type = (activity.event_type or "").lower()

        if event_type == "learning_feedback":
            step_norm, signal = _to_feedback_signal(details)
            if step_norm and step_norm in scores:
                question_signal = (
                    _question_similarity(question, str(details.get("question", "")))
                    if isinstance(details, dict)
                    else 0.0
                )
                decay = _recency_weight(getattr(activity, "created_at", None))
                scores[step_norm] += signal * (0.6 + 0.4 * question_signal) * decay
            continue

        if event_type not in {"query", "investigation"}:
            continue

        if not isinstance(details, dict):
            continue

        event_question = str(details.get("question", ""))
        similarity = _question_similarity(event_question, question)
        if similarity == 0.0 and event_type == "query":
            similarity = 0.05

        history_weight = 0.35 + 0.65 * similarity
        decay = _recency_weight(getattr(activity, "created_at", None))
        for prior_step in _collect_historical_steps(details):
            prior_norm = _normalize_step(prior_step)
            if prior_norm not in scores:
                continue

            if event_type == "query":
                epistemic = str(details.get("epistemic_status", "")).lower()
                if epistemic in {"insufficient", "unknown", "conflicting"}:
                    history_weight += 0.15
                elif epistemic == "sufficient":
                    history_weight -= 0.05

            if event_type == "investigation":
                evidence_count = (
                    int(details.get("evidence_count") or 0)
                    if isinstance(details.get("evidence_count"), int)
                    else 0
                )
                if evidence_count:
                    history_weight += min(0.2, evidence_count / 25)

            scores[prior_norm] += history_weight * decay

    ordered = sorted(base_order, key=lambda norm: scores.get(norm, 0.0), reverse=True)
    return tuple(canonical[norm] for norm in ordered)


def _serialize_gap(gap: Gap) -> dict[str, object]:
    contract = _gap_contract_snapshot(gap)
    return {
        "id": str(gap.id),
        "kind": gap.kind,
        "description": _normalize_gap_description(gap.description),
        "severity": _normalize_severity(str(gap.severity)),
        "status": gap.status,
        "detected_by": gap.detected_by,
        "uncertainty_reason": contract["uncertainty_reason"],
        "evidence_hypothesis": contract["evidence_hypothesis"],
        "next_action": contract["next_action"],
        "expected_resolution": contract["expected_resolution"],
        "governance_tier": contract["governance_tier"],
        "priority_score": contract["priority_score"],
        "contract_status": ("complete" if contract["is_contract_complete"] else "partial"),
        "missing_contract_fields": contract["missing_contract_fields"],
        "evidence_anchor_count": contract["evidence_anchor_count"],
        "last_evaluated_at": contract["last_evaluated_at"],
        "resolution_summary": getattr(gap, "resolution_summary", None),
        "created_at": gap.created_at.isoformat() if getattr(gap, "created_at", None) else None,
        "resolved_at": gap.resolved_at.isoformat() if getattr(gap, "resolved_at", None) else None,
    }


def _serialize_activity(activity: Activity) -> dict[str, object]:
    return {
        "id": str(activity.id),
        "event_type": activity.event_type,
        "actor": activity.actor,
        "entity_type": activity.entity_type,
        "entity_id": str(activity.entity_id) if activity.entity_id else None,
        "details": activity.details if activity.details is not None else {},
        "created_at": activity.created_at.isoformat()
        if getattr(activity, "created_at", None)
        else None,
    }


def _is_conflict_signal(gap: Gap) -> bool:
    kind = str(gap.kind).lower()
    desc = _normalize_gap_description(gap.description).lower()
    if "conflict" in kind or "contradiction" in kind:
        return True
    return any(token in desc for token in HANDOFF_CONFLICT_KEYWORDS)


def _build_tool_step(
    action_type: str,
    corpus_id: str,
    *,
    question: str = "",
    gap_kind: str = "",
    explicit_step: str = "",
) -> str:
    if explicit_step.strip():
        return explicit_step.strip()
    if action_type == "investigate":
        escaped_question = _escape_prompt(question[:170])
        escaped_kind = _escape_prompt(gap_kind)
        return (
            f"investigate(corpus_id='{corpus_id}', question='"
            f"{escaped_question}', initial_predicates=('{escaped_kind}',))"
        )
    if action_type == "list_activity":
        return f"list_activity(corpus_id='{corpus_id}', limit=100)"
    if action_type == "list_gaps":
        return f"list_gaps(corpus_id='{corpus_id}', status='open', limit=10)"
    return f"query(corpus_id='{corpus_id}', question='{_escape_prompt(question[:170])}')"


def _float_payload(value: object, default: float = 0.35) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))
    return default


def _build_handoff_gap_actions(
    gaps: Sequence[Gap],
    corpus_id: str,
    unresolved_conflicts: list[dict[str, object]],
) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for gap in gaps:
        if str(gap.status).lower() != "open":
            continue

        desc = _normalize_gap_description(gap.description)
        if not desc:
            continue

        contract = _gap_contract_snapshot(gap)
        persisted_next_action = _payload_dict(contract.get("next_action"))
        evidence_hypothesis = _payload_dict(contract.get("evidence_hypothesis"))
        is_conflict_gap = _is_conflict_signal(gap)
        if is_conflict_gap:
            inferred_action_type = "investigate"
            inferred_reason = "contradiction_or_supersession"
            verb = "resolve"
            prompt = f"{verb} conflict/supersession evidence for: {desc}"
        elif "relation" in gap.kind.lower() or "dependency" in gap.kind.lower():
            inferred_action_type = "investigate"
            inferred_reason = "relation_dependency"
            verb = "trace"
            prompt = f"{verb} relations for: {desc}"
        else:
            inferred_action_type = "query"
            inferred_reason = "missing_evidence"
            verb = "find"
            prompt = f"{verb} direct evidence for: {desc}"

        severity = _normalize_severity(str(gap.severity))
        action_type = _coerce_action_type(
            persisted_next_action.get("action_type"),
            fallback=inferred_action_type,
        )
        question = str(persisted_next_action.get("question") or prompt)
        action_step = _build_tool_step(
            action_type,
            corpus_id,
            question=question,
            gap_kind=str(gap.kind),
            explicit_step=str(persisted_next_action.get("step") or ""),
        )
        uncertainty_reason = str(contract.get("uncertainty_reason") or inferred_reason)
        if uncertainty_reason == "missing_evidence" and inferred_reason != "missing_evidence":
            uncertainty_reason = inferred_reason
        expected_signal_target = evidence_hypothesis or {
            "source": "gap",
            "kind": gap.kind,
            "evidence_needed": "proposition_or_activity_confirmation",
        }
        target = {
            "gap_id": str(gap.id),
            "kind": gap.kind,
            **_payload_dict(persisted_next_action.get("target")),
        }
        rationale = str(
            persisted_next_action.get("rationale")
            or f"{verb.capitalize()} unresolved {severity} gap {gap.kind}."
        )

        actions.append(
            {
                "action_type": action_type,
                "step": action_step,
                "rationale": rationale,
                "target": target,
                "expected_signal_target": expected_signal_target,
                "expected_resolution": contract.get("expected_resolution") or "",
                "expected_uncertainty_reduction": _float_payload(
                    persisted_next_action.get("expected_uncertainty_reduction"),
                ),
                "evidence_anchors": _payload_list(evidence_hypothesis.get("anchors")),
                "uncertainty_reason": uncertainty_reason,
                "governance_tier": contract["governance_tier"],
                "gap_ids": [str(gap.id)],
                "activity_ids": [],
                "source_contract": {
                    "gap_contract_status": (
                        "complete" if contract["is_contract_complete"] else "partial"
                    ),
                    "missing_contract_fields": contract["missing_contract_fields"],
                    "last_evaluated_at": contract["last_evaluated_at"],
                },
                "priority_score": contract.get("priority_score"),
            }
        )

    conflict_gap_actions: list[dict[str, object]] = []
    for event in unresolved_conflicts:
        old_id = event.get("old_proposition_id")
        new_id = event.get("new_proposition_id")
        if not (old_id or new_id):
            continue
        prop_ids = [v for v in [old_id, new_id] if v]
        action_question = f"Check whether proposition chain {old_id} is still valid after rework"
        action_step = f"investigate(corpus_id='{corpus_id}', question='{action_question}')"
        conflict_gap_actions.append(
            {
                "action_type": "investigate",
                "step": action_step,
                "rationale": "Validate unresolved conflict / supersession before reuse.",
                "target": {
                    "conflict_type": event.get("conflict_type"),
                    "old_proposition_id": old_id,
                    "new_proposition_id": new_id,
                    "changeset_id": event.get("changeset_id"),
                    "reason": event.get("reason"),
                },
                "expected_signal_target": {
                    "source": "activity",
                    "proposition_ids": [str(v) for v in prop_ids],
                    "changeset_id": event.get("changeset_id"),
                },
                "expected_resolution": (
                    "Determine whether the old proposition is superseded, retracted, "
                    "or still safe to reuse."
                ),
                "expected_uncertainty_reduction": 0.8,
                "evidence_anchors": [
                    {
                        "target_type": "activity",
                        "target_id": event.get("activity_id"),
                    }
                ]
                if event.get("activity_id")
                else [],
                "uncertainty_reason": "stale_or_conflicted_memory",
                "gap_ids": [],
                "activity_ids": [event.get("activity_id", "")] if event.get("activity_id") else [],
                "conflict_priority": True,
                "source_contract": {
                    "gap_contract_status": "activity_conflict",
                    "missing_contract_fields": [],
                    "last_evaluated_at": event.get("event_at"),
                },
                "priority_score": 1.0,
            }
        )

    return actions + conflict_gap_actions


def _extract_conflict_events(activities: Sequence[Activity]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for activity in activities:
        if not getattr(activity, "event_type", ""):
            continue
        event_type = str(activity.event_type).lower()
        if (
            event_type not in HANDOFF_CONFLICT_EVENT_TYPES
            and event_type not in HANDOFF_ACTIVITY_EVENT_TYPES
        ):
            continue

        details = activity.details or {}
        old_id = _normalize_payload_text(
            details.get("old_proposition_id") if isinstance(details, Mapping) else "",
        )
        if not old_id:
            old_id = _normalize_payload_text(
                details.get("proposition_id") if isinstance(details, Mapping) else "",
            )
        if not old_id and getattr(activity, "entity_id", None):
            old_id = str(activity.entity_id)
        new_id = ""
        if event_type == "supersession":
            new_id = _normalize_payload_text(details.get("new_proposition_id"))
        elif event_type == "retraction":
            retraction_id = _normalize_payload_text(details.get("retraction_proposition_id"))
            if retraction_id:
                new_id = retraction_id

        elif event_type == "attestation_rejection":
            old_id = _normalize_payload_text(details.get("proposition_id", ""))
        elif event_type in {"repair_apply", "repair_rollback", "attestation_review"}:
            continue

        event_id = str(activity.id)
        changeset_id = _normalize_payload_text(
            details.get("changeset_id") if isinstance(details, Mapping) else ""
        )
        reason = _normalize_payload_text(
            details.get("reason") if isinstance(details, Mapping) else ""
        )
        conflict_key = (event_id, old_id, new_id, event_type)
        if conflict_key in seen:
            continue
        seen.add(conflict_key)

        if old_id or new_id:
            events.append(
                {
                    "activity_id": event_id,
                    "conflict_type": event_type,
                    "old_proposition_id": old_id or None,
                    "new_proposition_id": new_id or None,
                    "event_at": activity.created_at.isoformat()
                    if getattr(activity, "created_at", None)
                    else None,
                    "actor": activity.actor,
                    "resolved": False,
                    "changeset_id": changeset_id or None,
                    "reason": reason or None,
                }
            )

    return events


def _build_current_truth_candidates(
    unresolved_conflicts: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for event in unresolved_conflicts:
        new_id = event.get("new_proposition_id")
        if not new_id:
            continue
        proposition_id = str(new_id)
        if proposition_id in seen:
            continue
        seen.add(proposition_id)
        old_id = event.get("old_proposition_id")
        activity_id = event.get("activity_id")
        candidates.append(
            {
                "proposition_id": proposition_id,
                "candidate_status": "requires_review",
                "safe_to_reuse": False,
                "reason": (
                    "Newer proposition appears in a supersession/retraction chain, "
                    "but the handoff still marks the conflict unresolved."
                ),
                "supersedes": str(old_id) if old_id else None,
                "supersession_chain": [str(value) for value in (old_id, new_id) if value],
                "source_anchors": [{"target_type": "activity", "target_id": str(activity_id)}]
                if activity_id
                else [],
                "changeset_id": event.get("changeset_id"),
                "event_at": event.get("event_at"),
            }
        )
    return candidates


def _build_avoid_or_revalidate(
    unresolved_conflicts: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    stale: list[dict[str, object]] = []
    seen: set[str] = set()
    for event in unresolved_conflicts:
        old_id = event.get("old_proposition_id")
        if not old_id:
            continue
        proposition_id = str(old_id)
        if proposition_id in seen:
            continue
        seen.add(proposition_id)
        activity_id = event.get("activity_id")
        stale.append(
            {
                "proposition_id": proposition_id,
                "reuse_policy": "avoid_or_revalidate_before_use",
                "reason": str(
                    event.get("reason") or event.get("conflict_type") or "unresolved_conflict"
                ),
                "candidate_replacement_id": (
                    str(event.get("new_proposition_id"))
                    if event.get("new_proposition_id")
                    else None
                ),
                "source_anchors": [{"target_type": "activity", "target_id": str(activity_id)}]
                if activity_id
                else [],
                "changeset_id": event.get("changeset_id"),
                "event_at": event.get("event_at"),
            }
        )
    return stale


def _escape_prompt(text: str) -> str:
    return text.replace("'", "\\'").replace("\n", " ").replace("\r", " ")


def _is_conflict_related_action(
    action: dict[str, object], unresolved_conflicts: list[dict[str, object]]
) -> bool:
    if action.get("conflict_priority"):
        return True
    return action.get("uncertainty_reason") in {
        "contradiction_or_supersession",
        "stale_or_conflicted_memory",
    }


def _governance_tier(action: dict[str, object]) -> str:
    reason = str(action.get("uncertainty_reason", "")).lower()
    if reason in {"contradiction_or_supersession", "stale_or_conflicted_memory", "frontier_audit"}:
        return GOVERNANCE_TIER_STALE
    existing = str(action.get("governance_tier", "")).lower()
    if existing in VALID_GOVERNANCE_TIERS:
        return existing
    if action.get("action_type") in {"list_activity", "list_gaps"}:
        return GOVERNANCE_TIER_GUARANTEED
    if (
        str(action.get("action_type")).lower() == "query"
        and str(action.get("target", {}).get("type", "")).lower() == "continuity"
    ):
        return GOVERNANCE_TIER_PROVISIONAL
    return GOVERNANCE_TIER_PROVISIONAL


def _build_governance_snapshot(
    actions: Sequence[dict[str, object]],
    frontier: dict[str, object],
) -> dict[str, list[str]]:
    governance: dict[str, list[str]] = {
        "guaranteed_fields": [
            "protocol_version",
            "protocol",
            "generated_at",
            "continuity_role",
            "corpus_id",
            "open_gaps",
            "recent_activity",
            "continuity_frontier",
            "current_truth_candidates",
            "avoid_or_revalidate_before_use",
        ],
        "provisional_fields": [],
        "stale_fields": [],
    }
    for action in actions:
        tier = str(action.get("governance_tier", GOVERNANCE_TIER_PROVISIONAL))
        if tier not in VALID_GOVERNANCE_TIERS:
            continue
        key = str(action.get("step", ""))
        if tier == GOVERNANCE_TIER_GUARANTEED:
            governance["guaranteed_fields"].append(key)
        elif tier == GOVERNANCE_TIER_STALE:
            governance["stale_fields"].append(key)
        else:
            governance["provisional_fields"].append(key)

    if frontier.get("unresolved_conflict_count", 0):
        conflict_count = int(frontier.get("unresolved_conflict_count", 0))
        for index in range(conflict_count):
            governance["stale_fields"].append(f"frontier.unresolved_conflict[{index}]")
    if frontier.get("frontier_completeness") != "complete":
        governance["provisional_fields"].append("continuity_frontier.frontier_completeness")
    for gap_id in frontier.get("missing_gap_contract_ids", []):
        governance["stale_fields"].append(f"open_gaps.contract[{gap_id}]")
    return governance


def _score_action(
    action: dict[str, object],
    unresolved_conflicts: list[dict[str, object]],
    activities: list[Activity],
) -> float:
    action_type = str(action.get("action_type", "query"))
    action_text = str(action.get("step", ""))
    base_score = (
        HANDOFF_ACTION_ORDER.index(action_type)
        if action_type in HANDOFF_ACTION_ORDER
        else len(HANDOFF_ACTION_ORDER)
    )
    # Lower index means higher priority for deterministic sort.
    score = 10.0 - base_score

    # Prioritize high-severity gaps when available.
    for gap_id in action.get("gap_ids", []):
        if not isinstance(gap_id, str):
            continue
        # score contribution from known severity terms in rationale/uncertainty.
        if "critical" in _normalize_payload_text(action.get("rationale", "")):
            score += 2.5
        elif "moderate" in _normalize_payload_text(action.get("rationale", "")):
            score += 1.2
        else:
            score += 0.75

    if isinstance(action.get("priority_score"), (int, float)):
        score += min(max(float(action["priority_score"]), 0.0), 10.0)
    if isinstance(action.get("expected_uncertainty_reduction"), (int, float)):
        score += min(max(float(action["expected_uncertainty_reduction"]), 0.0), 1.0)

    # Penalize generic query paths if unresolved conflicts remain and this
    # action is not conflict-focused.
    if unresolved_conflicts and not _is_conflict_related_action(action, unresolved_conflicts):
        score -= 0.7

    # Apply persisted learning feedback adjustment.
    feedback_norm, feedback_signal = "", 0.0
    for activity in activities:
        if activity.event_type != "learning_feedback":
            continue
        f_norm, f_signal = _to_feedback_signal(activity.details)
        feedback_norm = f_norm or feedback_norm
        if f_norm == _normalize_step(action_text):
            feedback_signal = f_signal
            break

    if feedback_norm == _normalize_step(action_text):
        score += feedback_signal * 0.8

    if _is_conflict_related_action(action, unresolved_conflicts):
        score += 1.5
    if action.get("uncertainty_reason") == "missing_evidence_anchors":
        score += 0.75
    return score


def _select_frontier(
    open_gaps: Sequence[Gap],
    unresolved_conflicts: list[dict[str, object]],
    recent_activity_count: int = 0,
) -> dict[str, object]:
    critical_count = 0
    unresolved_gap_ids: list[str] = []
    missing_gap_contract_ids: list[str] = []
    evidence_anchor_count = 0
    structured_gap_count = 0
    for gap in open_gaps:
        if str(gap.status).lower() != "open":
            continue
        gap_id = str(gap.id)
        unresolved_gap_ids.append(gap_id)
        if _normalize_severity(str(gap.severity)) == str(GapSeverity.CRITICAL):
            critical_count += 1
        contract = _gap_contract_snapshot(gap)
        evidence_anchor_count += int(contract["evidence_anchor_count"])
        if contract["is_contract_complete"]:
            structured_gap_count += 1
        else:
            missing_gap_contract_ids.append(gap_id)

    incomplete_reasons: list[str] = []
    if missing_gap_contract_ids:
        incomplete_reasons.append("open_gaps_missing_continuity_contract")
    if unresolved_gap_ids and evidence_anchor_count == 0:
        incomplete_reasons.append("open_gaps_lack_evidence_anchors")
    if unresolved_conflicts:
        incomplete_reasons.append("unresolved_conflicts_require_review")
    if not unresolved_gap_ids and recent_activity_count == 0:
        incomplete_reasons.append("no_memory_activity_to_resume_from")

    if not unresolved_gap_ids and recent_activity_count == 0:
        completeness = "bootstrap_required"
        status = "needs_bootstrap"
    elif incomplete_reasons:
        completeness = "partial"
        status = "attention_required"
    else:
        completeness = "complete"
        status = "ready"

    if not unresolved_gap_ids:
        anchor_sufficiency = "not_applicable"
    elif evidence_anchor_count == 0:
        anchor_sufficiency = "none"
    elif evidence_anchor_count < len(unresolved_gap_ids):
        anchor_sufficiency = "partial"
    else:
        anchor_sufficiency = "sufficient"

    if status == "ready":
        readiness_reason = (
            "Open continuity gaps have complete contracts, evidence anchors, "
            "and no unresolved conflict events."
        )
    elif status == "needs_bootstrap":
        readiness_reason = (
            "No open gaps or recent activity were available; bootstrap memory "
            "before relying on the handoff."
        )
    else:
        readiness_reason = "; ".join(incomplete_reasons)

    return {
        "open_gap_count": len(unresolved_gap_ids),
        "critical_open_gap_count": critical_count,
        "unresolved_conflict_count": len(unresolved_conflicts),
        "unresolved_gap_ids": unresolved_gap_ids,
        "unresolved_conflicts": unresolved_conflicts,
        "structured_gap_count": structured_gap_count,
        "missing_gap_contract_count": len(missing_gap_contract_ids),
        "missing_gap_contract_ids": missing_gap_contract_ids,
        "evidence_anchor_count": evidence_anchor_count,
        "frontier_completeness": completeness,
        "continuity_status": status,
        "anchor_sufficiency": anchor_sufficiency,
        "readiness_reason": readiness_reason,
        "incomplete_reasons": incomplete_reasons,
    }


def build_handoff_bundle(
    corpus_id: uuid.UUID | str,
    gaps: Sequence[Gap],
    activities: Sequence[Activity],
    *,
    max_gaps: int = 10,
    max_activity: int = 20,
    max_actions: int = 10,
) -> dict[str, object]:
    max_gaps = max(1, min(max_gaps, 50))
    max_activity = max(1, min(max_activity, 200))
    max_actions = max(1, min(max_actions, 30))

    corpus_id_str = str(corpus_id)
    open_gaps = [g for g in gaps if str(getattr(g, "status", "")).lower() == "open"][:max_gaps]
    recent_activity = list(activities)[:max_activity]
    unresolved_conflicts = _extract_conflict_events(recent_activity)
    raw_actions = _build_handoff_gap_actions(open_gaps, corpus_id_str, unresolved_conflicts)
    anchorless_gap_ids = [
        str(gap.id)
        for gap in open_gaps
        if int(_gap_contract_snapshot(gap)["evidence_anchor_count"]) == 0
    ]
    if anchorless_gap_ids:
        raw_actions.append(
            {
                "action_type": "list_gaps",
                "step": f"list_gaps(corpus_id='{corpus_id_str}', status='open', limit={max_gaps})",
                "rationale": "Collect stable evidence anchors before relying on open gap memory.",
                "target": {
                    "type": "gap_anchor_collection",
                    "gap_ids": anchorless_gap_ids,
                },
                "expected_signal_target": {
                    "source": "gaps",
                    "goal": "attach_document_span_or_activity_anchors",
                },
                "expected_resolution": (
                    "Each open gap has at least one stable document/span/proposition/"
                    "activity anchor or is explicitly marked rediscovery-required."
                ),
                "expected_uncertainty_reduction": 0.7,
                "evidence_anchors": [],
                "uncertainty_reason": "missing_evidence_anchors",
                "governance_tier": GOVERNANCE_TIER_PROVISIONAL,
                "gap_ids": anchorless_gap_ids,
                "activity_ids": [],
                "source_contract": {
                    "gap_contract_status": "anchor_audit",
                    "missing_contract_fields": ["evidence_hypothesis.anchors"],
                    "last_evaluated_at": None,
                },
                "priority_score": 0.5,
            }
        )
    if not raw_actions:
        raw_actions.append(
            {
                "action_type": "query",
                "step": (
                    f"query(corpus_id='{corpus_id_str}', "
                    "question='Run targeted investigation for objective context.')"
                ),
                "rationale": (
                    "No open gaps were found; verify whether objective assumptions remain stable."
                ),
                "target": {"type": "continuity"},
                "expected_signal_target": {"source": "state", "goal": "assumption_revalidation"},
                "expected_resolution": (
                    "Confirm that the corpus has no unresolved continuity obligations "
                    "before relying on it."
                ),
                "expected_uncertainty_reduction": 0.25,
                "evidence_anchors": [],
                "uncertainty_reason": "no_open_gaps",
                "gap_ids": [],
                "activity_ids": [str(activity.id) for activity in recent_activity[:2]],
                "source_contract": {
                    "gap_contract_status": "no_open_gaps",
                    "missing_contract_fields": [],
                    "last_evaluated_at": None,
                },
            }
        )

    # Add explicit visibility actions for open conflicts.
    if unresolved_conflicts:
        raw_actions.append(
            {
                "action_type": "list_activity",
                "step": (
                    f"list_activity(corpus_id='{corpus_id_str}', limit=100, "
                    "event_type='supersession')"
                ),
                "rationale": (
                    "Review open supersession/retraction chain before relying on prior claims."
                ),
                "target": {"type": "activity"},
                "expected_signal_target": {"source": "activity", "goal": "conflict_visibility"},
                "expected_resolution": (
                    "Expose the complete supersession/retraction lineage before "
                    "resuming dependent work."
                ),
                "expected_uncertainty_reduction": 0.65,
                "evidence_anchors": [
                    {"target_type": "activity", "target_id": e.get("activity_id")}
                    for e in unresolved_conflicts
                    if e.get("activity_id")
                ],
                "uncertainty_reason": "stale_or_conflicted_memory",
                "gap_ids": [],
                "activity_ids": [
                    e.get("activity_id") for e in unresolved_conflicts if e.get("activity_id")
                ],
                "source_contract": {
                    "gap_contract_status": "activity_conflict",
                    "missing_contract_fields": [],
                    "last_evaluated_at": None,
                },
            }
        )
        if len(raw_actions) < max_actions:
            raw_actions.append(
                {
                    "action_type": "list_gaps",
                    "step": (
                        f"list_gaps(corpus_id='{corpus_id_str}', status='open', limit={max_gaps})"
                    ),
                    "rationale": (
                        "Re-scan unresolved gap frontier with stable IDs and severity tags."
                    ),
                    "target": {"type": "gap", "status": "open"},
                    "expected_signal_target": {"source": "gaps", "goal": "frontier_visibility"},
                    "expected_resolution": (
                        "Reload the current open frontier before picking the next evidence action."
                    ),
                    "expected_uncertainty_reduction": 0.35,
                    "evidence_anchors": [],
                    "uncertainty_reason": "frontier_audit",
                    "gap_ids": [str(g.id) for g in open_gaps],
                    "activity_ids": [],
                    "source_contract": {
                        "gap_contract_status": "frontier_audit",
                        "missing_contract_fields": [],
                        "last_evaluated_at": None,
                    },
                }
            )

    # Score and rank for deterministic next-step output.
    scored = []
    for action in raw_actions:
        score = _score_action(action, unresolved_conflicts, list(recent_activity))
        action["governance_tier"] = _governance_tier(action)
        action["confidence"] = round(min(max(score / 6.0, 0.0), 1.0), 3)
        scored.append((score, action))
    scored.sort(
        key=lambda item: (
            -float(item[0]),
            item[1].get("action_type") in HANDOFF_ACTION_ORDER,
            _normalize_step(str(item[1].get("step", ""))),
        ),
    )

    # Remove redundant actions that differ only by step formatting.
    deduped_actions: list[dict[str, object]] = []
    seen_step_keys: set[str] = set()
    for _score, action in scored:
        step_key = _normalize_step(str(action.get("step", "")))
        if not step_key or step_key in seen_step_keys:
            continue
        seen_step_keys.add(step_key)
        deduped_actions.append(action)

    priority_next_actions = deduped_actions[:max_actions]
    continuity_frontier = _select_frontier(
        open_gaps,
        unresolved_conflicts,
        recent_activity_count=len(recent_activity),
    )
    continuity_frontier["action_count"] = len(priority_next_actions)

    return {
        "protocol_version": HANDOFF_SCHEMA_VERSION,
        "protocol": "mapu-resume-handoff",
        "generated_at": datetime.now(UTC).isoformat(),
        "continuity_role": "claude-style handoff",
        "corpus_id": corpus_id_str,
        "open_gaps": [_serialize_gap(gap) for gap in open_gaps],
        "recent_activity": [_serialize_activity(activity) for activity in recent_activity],
        "current_truth_candidates": _build_current_truth_candidates(unresolved_conflicts),
        "avoid_or_revalidate_before_use": _build_avoid_or_revalidate(unresolved_conflicts),
        "continuity_frontier": continuity_frontier,
        "continuity_governance": _build_governance_snapshot(
            priority_next_actions,
            continuity_frontier,
        ),
        "priority_next_actions": priority_next_actions,
    }
