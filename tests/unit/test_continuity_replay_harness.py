"""Unit tests for continuity replay harness action parsing and execution."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from tools.continuity_replay_harness import (
    SessionRecord,
    _coerce_seq_of_strings,
    _execute_handoff_action,
    _parse_action_step,
    _response_quality_summary,
    _session_resume,
)


class TestActionParsing:
    def test_parse_query_action(self) -> None:
        corpus_id = str(uuid4())
        step = f"query(corpus_id='{corpus_id}', question='What is ACME?', max_results=12)"

        action_type, params = _parse_action_step(step)

        assert action_type == "query"
        assert params["corpus_id"] == corpus_id
        assert params["question"] == "What is ACME?"
        assert params["max_results"] == 12

    def test_parse_investigate_action(self) -> None:
        corpus_id = str(uuid4())
        step = (
            f"investigate(corpus_id='{corpus_id}', question='Trace ACME supplier links', "
            "initial_predicates=('supplier','owns'), max_actions=7)"
        )

        action_type, params = _parse_action_step(step)

        assert action_type == "investigate"
        assert params["initial_predicates"] == ("supplier", "owns")
        assert _coerce_seq_of_strings(params["initial_predicates"]) == ["supplier", "owns"]

    def test_rejects_unsupported_action(self) -> None:
        corpus_id = str(uuid4())
        with pytest.raises(ValueError, match="Unsupported action type"):
            _parse_action_step(f"delete(corpus_id='{corpus_id}')")


class TestActionExecution:
    @pytest.mark.asyncio
    async def test_execute_query_action(self) -> None:
        corpus_id = str(uuid4())
        client = AsyncMock()
        client.query = AsyncMock(
            return_value={
                "answer": "Risk is concentrated in the renewal clause.",
                "hits": [1, 2],
                "next_steps": ["A", "B"],
            }
        )

        result = await _execute_handoff_action(
            client,
            corpus_id,
            f"query(corpus_id='{corpus_id}', question='Summarize risk', max_results=6)",
        )

        assert result.success is True
        assert result.action_type == "query"
        assert result.estimated_read_calls == 1.0
        assert result.result_count == 4
        assert result.quality["passed"] is True
        client.query.assert_awaited_once()
        _, kwargs = client.query.call_args
        assert kwargs["question"] == "Summarize risk"
        assert kwargs["max_results"] == 6

    @pytest.mark.asyncio
    async def test_execute_rejects_cross_corpus_action(self) -> None:
        corpus_id = str(uuid4())
        other_corpus_id = str(uuid4())
        client = AsyncMock()
        client.query = AsyncMock(return_value={"hits": [1]})

        result = await _execute_handoff_action(
            client,
            corpus_id,
            f"query(corpus_id='{other_corpus_id}', question='Summarize risk')",
        )

        assert result.success is False
        assert result.action_type == "query"
        assert result.estimated_read_calls == 0.0
        assert "does not match harness corpus" in str(result.error)
        client.query.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_investigate_action(self) -> None:
        corpus_id = str(uuid4())
        client = AsyncMock()
        client.investigate = AsyncMock(return_value={"gaps": [1], "evidence": [1], "findings": [1]})

        result = await _execute_handoff_action(
            client,
            corpus_id,
            (
                f"investigate(corpus_id='{corpus_id}', question='Trace missing chain', "
                "initial_predicates=('dependency', 'trace'), max_actions=4)"
            ),
        )

        assert result.success is True
        assert result.action_type == "investigate"
        _, kwargs = client.investigate.call_args
        assert kwargs["initial_predicates"] == ["dependency", "trace"]

    @pytest.mark.asyncio
    async def test_execute_list_actions(self) -> None:
        corpus_id = str(uuid4())
        client = AsyncMock()
        client.list_gaps = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])
        client.list_activity = AsyncMock(return_value=[{"id": "a1"}])

        gap_result = await _execute_handoff_action(
            client,
            corpus_id,
            f"list_gaps(corpus_id='{corpus_id}', status='open', limit=2)",
        )
        activity_result = await _execute_handoff_action(
            client,
            corpus_id,
            f"list_activity(corpus_id='{corpus_id}', event_type='supersession', limit=10)",
        )

        assert gap_result.success is True
        assert gap_result.result_count == 2
        assert activity_result.success is True
        assert activity_result.result_count == 1
        client.list_gaps.assert_awaited_once()
        client.list_activity.assert_awaited_once()


class TestSessionReplay:
    @pytest.mark.asyncio
    async def test_session_resume_runs_priority_actions(self) -> None:
        corpus_id = str(uuid4())
        client = AsyncMock()
        client.query = AsyncMock(return_value={"hits": [1], "next_steps": []})
        handoff = {
            "continuity_frontier": {
                "open_gap_count": 2,
                "unresolved_conflict_count": 1,
            },
            "priority_next_actions": [
                {"step": f"query(corpus_id='{corpus_id}', question='first')"},
                {"step": f"query(corpus_id='{corpus_id}', question='second')"},
            ],
        }

        record = await _session_resume(
            client,
            handoff,
            corpus_id,
            resume_question="",
            max_actions=1,
        )

        assert record.api_calls == 1
        assert record.handoff_action_count == 2
        assert len(record.executed_actions) == 1
        assert record.executed_actions[0]["success"] is True

    def test_response_quality_summary_counts_failed_response_actions(self) -> None:
        record = SessionRecord(
            label="session2_resumed",
            wall_ms=1.0,
            handoff_action_count=1,
            api_calls=1,
            estimated_read_calls=0.0,
            top_actions=[],
            executed_actions=[
                {
                    "action_type": "investigate",
                    "step": "investigate(corpus_id='x', question='q')",
                    "success": False,
                    "error": "HTTP 422",
                    "quality": {},
                }
            ],
            frontier_action_count=1,
            open_gap_count=1,
            unresolved_conflict_count=0,
            resumed_from_handoff=True,
        )

        summary = _response_quality_summary(record, 1.0)

        assert summary["passed"] is False
        assert summary["required_action_count"] == 1
        assert summary["failing_actions"][0]["reason"] == "HTTP 422"


class TestHarnessRun:
    @pytest.mark.asyncio
    async def test_run_harness_no_lifecycle_query_outputs_consistent_metrics(
        self,
        tmp_path,
    ) -> None:
        from tools.continuity_replay_harness import run_harness

        async def _fake_read_handoff(*_args, **_kwargs):
            return {
                "protocol": "mapu-resume-handoff",
                "protocol_version": "1.1.0",
                "continuity_frontier": {
                    "open_gap_count": 2,
                    "unresolved_conflict_count": 1,
                },
                "priority_next_actions": [
                    {
                        "step": (
                            "query(corpus_id='00000000-0000-0000-0000-000000000001', question='q')"
                        )
                    },
                ],
            }

        out_file = tmp_path / "harness.json"
        args = SimpleNamespace(
            corpus_id="00000000-0000-0000-0000-000000000001",
            base_url="http://127.0.0.1:8000",
            session1_questions=[
                "resume baseline 1",
                "resume baseline 2",
            ],
            session2_question="",
            max_gaps=10,
            max_activity=20,
            max_actions=8,
            max_executed_actions=4,
            out=str(out_file),
            require_frontier_completeness_gate=False,
            require_response_quality_gate=False,
            min_quality_pass_rate=1.0,
            no_lifecycle_query=True,
        )

        fake_engine = AsyncMock()
        fake_engine.dispose = AsyncMock()

        with (
            patch("tools.continuity_replay_harness._parse_args", return_value=args),
            patch(
                "tools.continuity_replay_harness.build_engine",
                return_value=(fake_engine, object()),
            ),
            patch("tools.continuity_replay_harness._read_handoff", _fake_read_handoff),
        ):
            rc = await run_harness()

        assert rc == 0
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        handoff_effect = payload["handoff_effect"]
        assert handoff_effect["api_calls_delta"] == 0
        assert handoff_effect["estimated_read_delta"] == 0.0
        assert isinstance(handoff_effect["top_action_count_delta"], int)
        assert handoff_effect["resumed_with_handoff"] is True
        assert handoff_effect["unresolved_gaps_carried"] == 2
        assert handoff_effect["unresolved_conflicts_carried"] == 1
        assert handoff_effect["read_reduction_gate"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_run_harness_with_read_reduction_gate_fails_when_not_improved(
        self,
        tmp_path,
    ) -> None:
        from tools.continuity_replay_harness import run_harness

        async def _fake_read_handoff(*_args, **_kwargs):
            return {
                "protocol": "mapu-resume-handoff",
                "protocol_version": "1.1.0",
                "continuity_frontier": {
                    "open_gap_count": 1,
                    "unresolved_conflict_count": 0,
                },
                "priority_next_actions": [
                    {
                        "step": (
                            "query(corpus_id='00000000-0000-0000-0000-000000000001', question='q1')"
                        )
                    },
                ],
            }

        out_file = tmp_path / "harness.json"
        args = SimpleNamespace(
            corpus_id="00000000-0000-0000-0000-000000000001",
            base_url="http://127.0.0.1:8000",
            session1_questions=[
                "resume baseline 1",
                "resume baseline 2",
            ],
            session2_question="",
            max_gaps=10,
            max_activity=20,
            max_actions=8,
            max_executed_actions=4,
            out=str(out_file),
            min_estimated_read_delta=2.5,
            require_read_reduction_gate=True,
            require_frontier_completeness_gate=False,
            require_response_quality_gate=False,
            min_quality_pass_rate=1.0,
            no_lifecycle_query=False,
        )

        fake_engine = AsyncMock()
        fake_engine.dispose = AsyncMock()
        client = AsyncMock()
        client.query = AsyncMock(
            return_value={
                "answer": "Replay answer",
                "next_steps": ["Inspect supporting evidence"],
                "chunk_hits": [{"id": "c1"}],
            }
        )
        client.investigate = AsyncMock(return_value={})
        client.list_gaps = AsyncMock(return_value=[])
        client.list_activity = AsyncMock(return_value=[])

        class _ClientContextManager:
            async def __aenter__(self):
                return client

            async def __aexit__(self, *_args):
                return None

        with (
            patch("tools.continuity_replay_harness._parse_args", return_value=args),
            patch(
                "tools.continuity_replay_harness.build_engine",
                return_value=(fake_engine, object()),
            ),
            patch("tools.continuity_replay_harness._read_handoff", _fake_read_handoff),
            patch(
                "tools.continuity_replay_harness.AsyncMapUClient",
                return_value=_ClientContextManager(),
            ),
        ):
            rc = await run_harness()

        assert rc == 1
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        handoff_effect = payload["handoff_effect"]
        assert handoff_effect["estimated_read_delta"] > 0.0
        assert handoff_effect["estimated_read_delta"] < 2.5
        assert handoff_effect["handoff_passed_read_reduction_gate"] is False
        assert handoff_effect["read_reduction_gate"]["enabled"] is True
        assert payload["failure_reason"].startswith("Continuity replay read-reduction gate failed:")

    @pytest.mark.asyncio
    async def test_run_harness_frontier_gate_fails_on_partial_contract(
        self,
        tmp_path,
    ) -> None:
        from tools.continuity_replay_harness import run_harness

        async def _fake_read_handoff(*_args, **_kwargs):
            return {
                "protocol": "mapu-resume-handoff",
                "protocol_version": "1.1.0",
                "continuity_frontier": {
                    "open_gap_count": 1,
                    "unresolved_conflict_count": 0,
                    "frontier_completeness": "partial",
                    "continuity_status": "attention_required",
                    "missing_gap_contract_count": 1,
                    "evidence_anchor_count": 0,
                },
                "priority_next_actions": [],
            }

        out_file = tmp_path / "harness.json"
        args = SimpleNamespace(
            corpus_id="00000000-0000-0000-0000-000000000001",
            base_url="http://127.0.0.1:8000",
            session1_questions=[],
            session2_question="",
            max_gaps=10,
            max_activity=20,
            max_actions=8,
            max_executed_actions=4,
            out=str(out_file),
            min_estimated_read_delta=0.0,
            require_read_reduction_gate=False,
            require_frontier_completeness_gate=True,
            require_response_quality_gate=False,
            min_quality_pass_rate=1.0,
            no_lifecycle_query=True,
        )

        fake_engine = AsyncMock()
        fake_engine.dispose = AsyncMock()

        with (
            patch("tools.continuity_replay_harness._parse_args", return_value=args),
            patch(
                "tools.continuity_replay_harness.build_engine",
                return_value=(fake_engine, object()),
            ),
            patch("tools.continuity_replay_harness._read_handoff", _fake_read_handoff),
        ):
            rc = await run_harness()

        assert rc == 1
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        assert payload["handoff_effect"]["handoff_passed_frontier_completeness_gate"] is False
        assert payload["handoff_effect"]["frontier_completeness_gate"]["enabled"] is True
        assert payload["failure_reason"].startswith("Continuity frontier completeness gate failed:")

    @pytest.mark.asyncio
    async def test_run_harness_response_quality_gate_fails_on_empty_resumed_query(
        self,
        tmp_path,
    ) -> None:
        from tools.continuity_replay_harness import run_harness

        async def _fake_read_handoff(*_args, **_kwargs):
            return {
                "protocol": "mapu-resume-handoff",
                "protocol_version": "1.1.0",
                "continuity_frontier": {
                    "open_gap_count": 0,
                    "unresolved_conflict_count": 0,
                    "frontier_completeness": "complete",
                    "continuity_status": "ready",
                    "missing_gap_contract_count": 0,
                    "evidence_anchor_count": 1,
                },
                "priority_next_actions": [
                    {
                        "step": (
                            "query(corpus_id='00000000-0000-0000-0000-000000000001', "
                            "question='What changed?')"
                        )
                    },
                ],
            }

        out_file = tmp_path / "harness.json"
        args = SimpleNamespace(
            corpus_id="00000000-0000-0000-0000-000000000001",
            base_url="http://127.0.0.1:8000",
            session1_questions=[],
            session2_question="",
            max_gaps=10,
            max_activity=20,
            max_actions=8,
            max_executed_actions=4,
            out=str(out_file),
            min_estimated_read_delta=0.0,
            require_read_reduction_gate=False,
            require_frontier_completeness_gate=False,
            require_response_quality_gate=True,
            min_quality_pass_rate=1.0,
            no_lifecycle_query=False,
        )

        fake_engine = AsyncMock()
        fake_engine.dispose = AsyncMock()
        client = AsyncMock()
        client.query = AsyncMock(return_value={"answer": "", "next_steps": [], "chunk_hits": []})

        class _ClientContextManager:
            async def __aenter__(self):
                return client

            async def __aexit__(self, *_args):
                return None

        with (
            patch("tools.continuity_replay_harness._parse_args", return_value=args),
            patch(
                "tools.continuity_replay_harness.build_engine",
                return_value=(fake_engine, object()),
            ),
            patch("tools.continuity_replay_harness._read_handoff", _fake_read_handoff),
            patch(
                "tools.continuity_replay_harness.AsyncMapUClient",
                return_value=_ClientContextManager(),
            ),
        ):
            rc = await run_harness()

        assert rc == 1
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        quality_gate = payload["handoff_effect"]["response_quality_gate"]
        assert quality_gate["enabled"] is True
        assert quality_gate["passed"] is False
        assert quality_gate["required_action_count"] == 1
        assert "answer_nonempty" in quality_gate["failing_actions"][0]["reason"]
        assert payload["failure_reason"].startswith("Continuity response quality gate failed:")
