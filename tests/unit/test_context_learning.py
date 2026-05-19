"""Unit tests for persistent next-step ranking."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from mapu.context_learning import (
    build_handoff_bundle,
    prioritize_next_steps,
    suggest_gap_based_next_steps,
)


def _gap(
    description: str,
    *,
    severity: str = "moderate",
    status: str = "open",
    kind: str = "knowledge",
    detected_by: str = "query",
    uncertainty_reason: str = "missing_evidence",
    evidence_hypothesis: dict | None = None,
    next_action: dict | None = None,
    expected_resolution: str | None = None,
    governance_tier: str = "provisional",
    priority_score: float | None = None,
) -> object:
    return SimpleNamespace(
        id=uuid.uuid4(),
        kind=kind,
        description=description,
        severity=severity,
        status=status,
        detected_by=detected_by,
        uncertainty_reason=uncertainty_reason,
        evidence_hypothesis=evidence_hypothesis or {},
        next_action=next_action or {},
        expected_resolution=expected_resolution,
        governance_tier=governance_tier,
        priority_score=priority_score,
        resolution_summary=None,
        last_evaluated_at=None,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        resolved_at=None,
    )


def _activity(event_type: str, *, details: dict, age_seconds: float = 0.0) -> object:
    return SimpleNamespace(
        event_type=event_type,
        details=details,
        created_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
        id=uuid.uuid4(),
        actor="test-agent",
        entity_type="proposition",
        entity_id=uuid.uuid4(),
        details_id=None,
    )


class TestPrioritizeNextSteps:
    async def test_prefers_helpful_feedback_step(self) -> None:
        activities = [
            _activity(
                "learning_feedback",
                details={
                    "question": "What is the revenue trend?",
                    "step": "Run entity-focused pass on ACME",
                    "outcome": "helpful",
                },
            ),
            _activity(
                "learning_feedback",
                details={
                    "question": "What is the revenue trend?",
                    "step": "Open a broad corpus scan",
                    "outcome": "not_helpful",
                },
            ),
        ]
        ranked = await prioritize_next_steps(
            ("Run entity-focused pass on ACME", "Open a broad corpus scan"),
            "What is the revenue trend in 2025?",
            activities,
        )
        assert ranked == (
            "Run entity-focused pass on ACME",
            "Open a broad corpus scan",
        )

    async def test_negatives_can_deprioritize(self) -> None:
        activities = [
            _activity(
                "learning_feedback",
                details={
                    "question": "Why did the project delay?",
                    "step": "Retry with higher budget",
                    "outcome": "not_helpful",
                },
            ),
        ]
        ranked = await prioritize_next_steps(
            ("Retry with higher budget",),
            "Why did the project delay?",
            activities,
        )
        assert ranked[0] == "Retry with higher budget"

    async def test_prefers_local_when_no_history(self) -> None:
        ranked = await prioritize_next_steps(
            ("A", "B", "A"),
            "unrelated",
            [],
        )
        assert ranked == ("A", "B")


class TestGapBasedSuggestions:
    def test_suggests_gaps_matching_question(self) -> None:
        steps = suggest_gap_based_next_steps(
            "Show me financial performance for 2024",
            (
                _gap("Track annual revenue trend from financial statements"),
                _gap("Missing definitions of entities"),
            ),
            limit=2,
        )

        assert len(steps) == 2
        assert "Investigate open moderate gap" in steps[0]
        assert "financial statements" in steps[0]

    def test_ignores_resolved_gaps(self) -> None:
        steps = suggest_gap_based_next_steps(
            "Tell me about ACME liabilities",
            (
                _gap("Resolved gap", status="resolved"),
                _gap("Open gap about liabilities"),
            ),
            limit=3,
        )
        assert len(steps) == 1
        assert "liabilities" in steps[0].lower()

    def test_unknown_severity_defaults_to_moderate_weight(self) -> None:
        steps = suggest_gap_based_next_steps(
            "How should we model risk?",
            (_gap("Risk model gap", severity="unknown"),),
            limit=1,
        )
        assert steps
        assert steps[0].startswith("Investigate open moderate gap")


class TestHandoffBundle:
    def test_build_bundle_includes_structured_actions_and_frontier(self) -> None:
        gap_open = _gap(
            "Conflicting evidence around liability treatment",
            kind="analysis_conflict",
            severity="critical",
        )
        gap_relation = _gap(
            "missing relation between ACME and supplier",
            kind="dependency",
            severity="moderate",
        )
        gap_resolved = _gap(
            "resolved example",
            status="resolved",
            severity="minor",
        )

        conflict_activity = _activity(
            "supersession",
            details={
                "proposition_id": "old-1",
                "new_proposition_id": "new-1",
            },
        )
        research_activity = _activity(
            "query",
            details={
                "question": "What is ACME liability trend?",
                "next_steps": ["Resolve contradiction chain A"],
                "epistemic_status": "unknown",
            },
        )

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000042",
            (gap_open, gap_relation, gap_resolved),
            (conflict_activity, research_activity),
            max_gaps=5,
            max_activity=10,
            max_actions=8,
        )

        assert handoff["protocol_version"] == "1.1.0"
        assert handoff["protocol"] == "mapu-resume-handoff"
        assert handoff["corpus_id"] == "00000000-0000-0000-0000-000000000042"
        assert handoff["continuity_frontier"]["open_gap_count"] == 2
        assert handoff["continuity_frontier"]["critical_open_gap_count"] == 1
        assert handoff["continuity_frontier"]["unresolved_conflict_count"] == 1
        assert set(handoff["continuity_frontier"]["unresolved_gap_ids"]) == {
            str(gap_open.id),
            str(gap_relation.id),
        }
        assert handoff["continuity_frontier"]["action_count"] == len(
            handoff["priority_next_actions"]
        )

        actions = handoff["priority_next_actions"]
        assert actions
        assert len(actions) <= 8
        assert isinstance(actions[0], dict)
        assert all(
            isinstance(action.get("gap_ids"), list)
            and isinstance(action.get("activity_ids"), list)
            and isinstance(action.get("step"), str)
            and isinstance(action.get("confidence"), float)
            for action in actions
        )

        conflict_actions = [
            a for a in actions if a.get("uncertainty_reason") == "stale_or_conflicted_memory"
        ]
        assert conflict_actions
        assert any(a["target"].get("conflict_type") == "supersession" for a in conflict_actions)

        expected_types = {"investigate", "query", "list_activity", "list_gaps"}
        assert {a["action_type"] for a in actions} <= expected_types

        governance = handoff["continuity_governance"]
        assert set(governance.keys()) == {
            "guaranteed_fields",
            "provisional_fields",
            "stale_fields",
        }
        assert governance["stale_fields"]
        assert any(a["governance_tier"] == "stale" for a in actions)
        assert "open_gaps" in governance["guaranteed_fields"]
        assert "frontier.unresolved_conflict[0]" in governance["stale_fields"]
        assert all(
            action["governance_tier"] in {"guaranteed", "provisional", "stale"}
            for action in actions
        )

    def test_build_bundle_falls_back_to_query_action_when_no_open_gaps(self) -> None:
        resolved_gap = _gap("already known", status="resolved")

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000043",
            (resolved_gap,),
            [],
            max_actions=5,
        )

        assert handoff["open_gaps"] == []
        assert handoff["priority_next_actions"]
        first_action = handoff["priority_next_actions"][0]
        assert first_action["action_type"] == "query"
        assert first_action["uncertainty_reason"] == "no_open_gaps"
        assert first_action["activity_ids"] == []

    def test_build_bundle_uses_persisted_gap_contract(self) -> None:
        gap = _gap(
            "Supplier dependency needs source-level confirmation",
            kind="dependency",
            severity="minor",
            uncertainty_reason="relation_dependency",
            evidence_hypothesis={
                "source": "span",
                "span_id": "span-1",
                "anchors": [{"target_type": "span", "target_id": "span-1"}],
            },
            next_action={
                "action_type": "investigate",
                "question": "Trace supplier dependency from source span",
                "target": {"span_id": "span-1"},
                "rationale": "Use the cited source span before broad rediscovery.",
                "expected_uncertainty_reduction": 0.9,
            },
            expected_resolution="Confirm or dismiss the dependency with source-linked evidence.",
            priority_score=9.0,
        )

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000049",
            (gap,),
            (),
            max_actions=3,
        )

        first_action = handoff["priority_next_actions"][0]
        assert first_action["action_type"] == "investigate"
        assert "Trace supplier dependency" in first_action["step"]
        assert first_action["target"]["span_id"] == "span-1"
        assert first_action["expected_uncertainty_reduction"] == 0.9
        assert (
            first_action["expected_resolution"]
            == "Confirm or dismiss the dependency with source-linked evidence."
        )
        assert first_action["source_contract"]["gap_contract_status"] == "complete"
        assert handoff["open_gaps"][0]["contract_status"] == "complete"
        assert handoff["continuity_frontier"]["frontier_completeness"] == "complete"
        assert handoff["continuity_frontier"]["structured_gap_count"] == 1
        assert handoff["continuity_frontier"]["evidence_anchor_count"] == 1
        assert handoff["continuity_frontier"]["anchor_sufficiency"] == "sufficient"

    def test_zero_anchor_open_gap_is_not_ready(self) -> None:
        gap = _gap(
            "Investigate missing terminal-agent evidence",
            evidence_hypothesis={
                "target": {"type": "corpus"},
                "confidence": 0.4,
            },
            next_action={
                "action_type": "investigate",
                "question": "Find source-linked terminal-agent evidence",
            },
            expected_resolution="Attach bounded source evidence before relying on this memory.",
        )

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000050",
            (gap,),
            (_activity("query", details={"question": "resume context"}),),
            max_actions=3,
        )

        frontier = handoff["continuity_frontier"]
        assert frontier["frontier_completeness"] == "partial"
        assert frontier["continuity_status"] == "attention_required"
        assert frontier["evidence_anchor_count"] == 0
        assert frontier["anchor_sufficiency"] == "none"
        assert "open_gaps_lack_evidence_anchors" in frontier["incomplete_reasons"]
        assert "open_gaps_lack_evidence_anchors" in frontier["readiness_reason"]

    def test_build_bundle_is_deterministic_for_same_inputs(self) -> None:
        gap_open = _gap("Track ACME quarterly trend", severity="critical")
        conflict_activity = _activity(
            "supersession",
            details={"proposition_id": "old", "new_proposition_id": "new"},
        )

        first = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000044",
            (gap_open,),
            (conflict_activity,),
            max_actions=10,
        )
        second = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000044",
            (gap_open,),
            (conflict_activity,),
            max_actions=10,
        )

        assert first["priority_next_actions"] == second["priority_next_actions"]
        assert first["continuity_frontier"] == second["continuity_frontier"]

    def test_conflict_gap_actions_are_prioritized(self) -> None:
        critical_conflict = _gap(
            "Conflict around revenue policy",
            kind="analysis_conflict",
            severity="critical",
        )
        moderate_gap = _gap(
            "Missing supplier dependency",
            kind="dependency",
            severity="moderate",
        )
        low_gap = _gap(
            "Missing filing source",
            kind="knowledge",
            severity="minor",
        )
        conflict_activity = _activity(
            "supersession",
            details={"proposition_id": "old", "new_proposition_id": "new"},
        )

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000045",
            (low_gap, moderate_gap, critical_conflict),
            (conflict_activity,),
            max_actions=6,
        )

        first = handoff["priority_next_actions"][0]
        assert first["action_type"] == "investigate"
        assert first["uncertainty_reason"] == "contradiction_or_supersession"
        assert "critical" in first["rationale"]

    def test_severity_influences_gap_action_ranking(self) -> None:
        high = _gap("High impact missing claim", severity="critical", kind="knowledge")
        medium = _gap("Medium claim", severity="moderate", kind="knowledge")
        low = _gap("Low claim", severity="minor", kind="knowledge")

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000046",
            (low, medium, high),
            (),
            max_actions=3,
        )

        actions = handoff["priority_next_actions"]
        assert "critical" in actions[0]["rationale"]
        assert actions[0]["gap_ids"] == [str(high.id)]

    def test_conflict_events_include_changeset_id_and_reason(self) -> None:
        gap = _gap(
            "Conflicting policy change",
            kind="analysis_conflict",
            severity="critical",
        )
        conflict_activity = _activity(
            "supersession",
            details={
                "old_proposition_id": "old-1",
                "new_proposition_id": "new-1",
                "changeset_id": "cs-99",
                "reason": "reworked source",
            },
        )

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000047",
            (gap,),
            (conflict_activity,),
            max_actions=5,
        )

        conflict_actions = [
            a
            for a in handoff["priority_next_actions"]
            if a.get("uncertainty_reason") == "stale_or_conflicted_memory"
        ]
        assert conflict_actions
        action = conflict_actions[0]
        assert action["target"]["old_proposition_id"] == "old-1"
        assert action["target"]["new_proposition_id"] == "new-1"
        assert action["target"]["changeset_id"] == "cs-99"
        assert action["target"]["reason"] == "reworked source"
        assert action["expected_signal_target"]["changeset_id"] == "cs-99"
        assert (
            "old-1"
            in handoff["continuity_frontier"]["unresolved_conflicts"][0]["old_proposition_id"]
        )

    def test_build_bundle_deduplicates_redundant_actions(self) -> None:
        gap = _gap(
            "Conflict resolution missing evidence",
            kind="analysis_conflict",
            severity="critical",
        )
        conflict_activity_one = _activity(
            "supersession",
            details={
                "proposition_id": "old-a",
                "new_proposition_id": "new-a",
                "changeset_id": "cs-a",
            },
        )
        conflict_activity_two = _activity(
            "supersession",
            details={
                "proposition_id": "old-a",
                "new_proposition_id": "new-a",
                "changeset_id": "cs-a",
            },
        )

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000048",
            (gap,),
            (conflict_activity_one, conflict_activity_two),
            max_actions=10,
        )

        action_steps = [
            action["step"]
            for action in handoff["priority_next_actions"]
            if isinstance(action, dict)
        ]
        assert len(action_steps) == len(set(action_steps))

    def test_handoff_exposes_current_candidates_and_stale_reuse_lane(self) -> None:
        gap = _gap(
            "Architecture decision changed after source correction",
            kind="analysis_conflict",
            severity="critical",
        )
        conflict_activity = _activity(
            "supersession",
            details={
                "old_proposition_id": "decision-v1",
                "new_proposition_id": "decision-v2",
                "changeset_id": "cs-42",
                "reason": "source corrected old architecture decision",
            },
        )

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000051",
            (gap,),
            (conflict_activity,),
            max_actions=8,
        )

        candidates = handoff["current_truth_candidates"]
        assert candidates
        assert candidates[0]["proposition_id"] == "decision-v2"
        assert candidates[0]["safe_to_reuse"] is False
        assert candidates[0]["candidate_status"] == "requires_review"
        assert candidates[0]["supersession_chain"] == ["decision-v1", "decision-v2"]

        stale = handoff["avoid_or_revalidate_before_use"]
        assert stale
        assert stale[0]["proposition_id"] == "decision-v1"
        assert stale[0]["candidate_replacement_id"] == "decision-v2"
        assert stale[0]["reuse_policy"] == "avoid_or_revalidate_before_use"

    def test_anchorless_gaps_prioritize_anchor_collection(self) -> None:
        gap = _gap(
            "Need durable evidence anchor for resumed coding work",
            evidence_hypothesis={},
            next_action={},
            expected_resolution="Attach source anchors before relying on this gap.",
        )

        handoff = build_handoff_bundle(
            "00000000-0000-0000-0000-000000000052",
            (gap,),
            (_activity("query", details={"question": "resume"}),),
            max_actions=5,
        )

        anchor_actions = [
            action
            for action in handoff["priority_next_actions"]
            if action.get("uncertainty_reason") == "missing_evidence_anchors"
        ]
        assert anchor_actions
        assert anchor_actions[0]["gap_ids"] == [str(gap.id)]
