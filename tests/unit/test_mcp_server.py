"""Unit tests for the MapU MCP server tool functions."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mapu.mcp import server as mcp_server


def _mock_session():
    """Create a mock async session that works as an async context manager."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


def _patch_factory(session):
    """Patch _get_session_factory to return a callable that yields our mock session."""
    factory = MagicMock(return_value=session)
    return patch("mapu.mcp.server._get_session_factory", return_value=factory)


class TestMCPRuntimePreload:
    def test_preload_imports_runtime_modules(self, monkeypatch: pytest.MonkeyPatch) -> None:
        imported: list[str] = []

        def fake_import_module(name: str) -> object:
            imported.append(name)
            return object()

        monkeypatch.setattr(mcp_server.importlib, "import_module", fake_import_module)

        mcp_server._preload_mcp_runtime_modules()

        assert imported == list(mcp_server._MCP_RUNTIME_PRELOAD_MODULES)
        assert "mapu.models" in imported
        assert "mapu.query.service" in imported
        assert "mapu.evidence.ingest" in imported


class TestQueryTool:
    @pytest.mark.asyncio
    async def test_query_returns_structured_result(self) -> None:
        from mapu.query.types import PropositionHit, QueryIntent, QueryRequest, QueryResult, Tier

        hit = PropositionHit(
            proposition_id=uuid.uuid4(),
            normalized_text="X defines Y",
            frame_type="definition",
            predicate="defines",
            subject_name="X",
            subject_kind="org",
            object_name="Y",
            object_kind="concept",
            truth_status=None,
            extraction_confidence=0.95,
            authority_score=0.8,
            source_span_text=None,
            relevance_score=1.0,
        )
        cid = uuid.uuid4()
        mock_result = QueryResult(
            request=QueryRequest(corpus_id=cid, question="What is X?"),
            intent=QueryIntent.IDENTITY,
            tier_used=Tier.DIRECT,
            synthesis="X defines Y",
            hits=(hit,),
            gaps=(),
            metadata={},
        )

        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
        ):
            from mapu.mcp.server import query

            result = await query(
                corpus_id=str(cid),
                question="What is X?",
            )

        assert result["intent"] == "identity"
        assert result["answer"] == "X defines Y"
        assert result["synthesis"] == "X defines Y"
        assert len(result["hits"]) == 1
        assert result["hits"][0]["predicate"] == "defines"
        assert result["hits"][0]["confidence"] == 0.95
        assert result["next_steps"] == []

    @pytest.mark.asyncio
    async def test_query_with_empty_results(self) -> None:
        from mapu.query.types import QueryIntent, QueryRequest, QueryResult, Tier

        cid = uuid.uuid4()
        mock_result = QueryResult(
            request=QueryRequest(corpus_id=cid, question="Unknown?"),
            intent=QueryIntent.IDENTITY,
            tier_used=Tier.DIRECT,
            synthesis=None,
            hits=(),
            gaps=("no data",),
            metadata={},
        )

        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
        ):
            from mapu.mcp.server import query

            result = await query(
                corpus_id=str(cid),
                question="Unknown?",
            )

        assert result["synthesis"] is None
        assert result["gaps"] == ["no data"]
        assert result["hits"] == []
        assert result["next_steps"] == []


class TestIngestDocumentTool:
    @pytest.mark.asyncio
    async def test_ingest_returns_ids_and_counts(self) -> None:
        doc_id = uuid.uuid4()
        expr_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.document_id = doc_id
        mock_result.expression_id = expr_id
        mock_result.span_count = 5
        mock_result.chunk_count = 3
        mock_result.embedding_count = 3

        mock_svc = AsyncMock()
        mock_svc.ingest = AsyncMock(return_value=mock_result)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.evidence.chunking.SpanAwareChunker"),
            patch("mapu.evidence.ingest.IngestionService", return_value=mock_svc),
            patch("mapu.evidence.parsers.ParserRegistry"),
        ):
            from mapu.mcp.server import ingest_document

            result = await ingest_document(
                corpus_id=str(uuid.uuid4()),
                content="Test document content",
            )

        assert result["document_id"] == str(doc_id)
        assert result["spans"] == 5
        assert result["chunks"] == 3
        assert result["embeddings"] == 3


class TestCreateCorpusTool:
    @pytest.mark.asyncio
    async def test_create_corpus_returns_id(self) -> None:
        corpus_id = uuid.uuid4()

        session = _mock_session()

        def capture_add(obj: object) -> None:
            obj.id = corpus_id  # type: ignore[attr-defined]
            obj.name = "test"  # type: ignore[attr-defined]

        session.add = MagicMock(side_effect=capture_add)

        with _patch_factory(session):
            from mapu.mcp.server import create_corpus

            result = await create_corpus(name="test", description="A test")

        assert result["id"] == str(corpus_id)
        assert result["name"] == "test"


class TestListCorporaTool:
    @pytest.mark.asyncio
    async def test_list_corpora_returns_list(self) -> None:
        c1_id = uuid.uuid4()
        c2_id = uuid.uuid4()

        mock_corpus_1 = MagicMock()
        mock_corpus_1.id = c1_id
        mock_corpus_1.name = "Corpus 1"
        mock_corpus_1.description = "First"

        mock_corpus_2 = MagicMock()
        mock_corpus_2.id = c2_id
        mock_corpus_2.name = "Corpus 2"
        mock_corpus_2.description = None

        session = _mock_session()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [mock_corpus_1, mock_corpus_2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        with _patch_factory(session):
            from mapu.mcp.server import list_corpora

            result = await list_corpora()

        assert len(result["corpora"]) == 2
        assert result["corpora"][0]["name"] == "Corpus 1"
        assert result["corpora"][1]["description"] is None

    @pytest.mark.asyncio
    async def test_list_corpora_empty(self) -> None:
        session = _mock_session()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result_mock)

        with _patch_factory(session):
            from mapu.mcp.server import list_corpora

            result = await list_corpora()

        assert result["corpora"] == []


class TestDestructiveCorpusToolGuards:
    @pytest.mark.asyncio
    async def test_delete_corpus_requires_confirm(self) -> None:
        from mapu.mcp.server import delete_corpus

        with patch("mapu.mcp.server._get_session_factory") as mock_factory:
            result = await delete_corpus(corpus_id=str(uuid.uuid4()))

        assert result == {"error": "Refusing delete without confirm=true"}
        mock_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_all_corpora_requires_confirm(self) -> None:
        from mapu.mcp.server import reset_all_corpora

        with patch("mapu.mcp.server._get_session_factory") as mock_factory:
            result = await reset_all_corpora()

        assert result == {"error": "Refusing reset without confirm=true"}
        mock_factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_corpus_uses_dependency_aware_cleanup(self) -> None:
        from mapu.mcp.server import delete_corpus

        cid = uuid.uuid4()
        session = _mock_session()
        session.get = AsyncMock(return_value=object())
        cleanup = AsyncMock()

        with (
            _patch_factory(session),
            patch("mapu.repos.corpus_cleanup.delete_corpus_rows", cleanup),
        ):
            result = await delete_corpus(corpus_id=str(cid), confirm=True)

        assert result == {"deleted_corpus_id": str(cid)}
        cleanup.assert_awaited_once_with(session, cid)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reset_all_corpora_uses_dependency_aware_cleanup(self) -> None:
        from mapu.mcp.server import reset_all_corpora

        cid1 = uuid.uuid4()
        cid2 = uuid.uuid4()
        result_mock = MagicMock()
        result_mock.all.return_value = [(cid1,), (cid2,)]
        session = _mock_session()
        session.execute = AsyncMock(return_value=result_mock)
        cleanup = AsyncMock()

        with (
            _patch_factory(session),
            patch("mapu.repos.corpus_cleanup.delete_corpus_rows", cleanup),
        ):
            result = await reset_all_corpora(confirm=True)

        assert result == {
            "deleted_count": 2,
            "deleted_corpus_ids": [str(cid1), str(cid2)],
        }
        assert cleanup.await_args_list[0].args == (session, cid1)
        assert cleanup.await_args_list[1].args == (session, cid2)
        session.commit.assert_awaited_once()


class TestIngestContentLimit:
    @pytest.mark.asyncio
    async def test_ingest_rejects_oversized_content(self) -> None:
        from mapu.mcp.server import ingest_document

        result = await ingest_document(
            corpus_id=str(uuid.uuid4()),
            content="x" * 10_000_001,
        )
        assert "error" in result


class TestQueryMaxResultsClamp:
    @pytest.mark.asyncio
    async def test_query_clamps_max_results(self) -> None:
        from mapu.query.types import QueryIntent, QueryRequest, QueryResult, Tier

        cid = uuid.uuid4()
        mock_result = QueryResult(
            request=QueryRequest(corpus_id=cid, question="test"),
            intent=QueryIntent.IDENTITY,
            tier_used=Tier.DIRECT,
            synthesis=None,
            hits=(),
            gaps=(),
            metadata={},
        )

        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
        ):
            from mapu.mcp.server import query

            await query(corpus_id=str(cid), question="test", max_results=9999)

        call_args = mock_svc.query.call_args[0][0]
        assert call_args.max_results == 500


class TestRepairPreviewTool:
    @pytest.mark.asyncio
    async def test_repair_preview_returns_blast_radius(self) -> None:
        pid = uuid.uuid4()
        blast_dict = {
            "root_proposition_id": str(pid),
            "affected_proposition_ids": [],
            "recompute_only_proposition_ids": [],
            "affected_handle_ids": [],
            "affected_gap_ids": [],
            "max_depth_seen": 0,
            "depth_limited": False,
            "risk_level": "low",
            "total_affected": 0,
        }

        mock_report = MagicMock()
        mock_report.to_dict.return_value = blast_dict
        session = _mock_session()

        with (
            _patch_factory(session),
            patch(
                "mapu.repair.blast_radius.compute_blast_radius",
                new_callable=AsyncMock,
                return_value=mock_report,
            ),
        ):
            from mapu.mcp.server import repair_preview

            result = await repair_preview(
                corpus_id=str(uuid.uuid4()),
                proposition_id=str(pid),
            )

        assert result["risk_level"] == "low"
        assert result["root_proposition_id"] == str(pid)


class TestRepairApplyTool:
    @pytest.mark.asyncio
    async def test_repair_apply_returns_result(self) -> None:
        csid = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.changeset_id = csid
        mock_result.success = True
        mock_result.operations_executed = 2
        mock_result.recomputed_propositions = 1
        mock_result.gaps_created = 0
        mock_result.errors = []

        mock_svc = AsyncMock()
        mock_svc.approve_and_apply = AsyncMock(return_value=mock_result)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.repair.service.RepairService", return_value=mock_svc),
        ):
            from mapu.mcp.server import repair_apply

            result = await repair_apply(
                corpus_id=str(uuid.uuid4()),
                changeset_id=str(csid),
            )

        assert result["success"] is True
        assert result["operations_executed"] == 2


class TestContributePropositionValidation:
    @pytest.mark.asyncio
    async def test_rejects_out_of_range_confidence(self) -> None:
        from mapu.mcp.server import contribute_proposition

        result = await contribute_proposition(
            corpus_id=str(uuid.uuid4()),
            subject_name="X",
            predicate="links",
            normalized_text="X links Y",
            confidence=1.5,
        )
        assert "error" in result
        assert "confidence" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_negative_confidence(self) -> None:
        from mapu.mcp.server import contribute_proposition

        result = await contribute_proposition(
            corpus_id=str(uuid.uuid4()),
            subject_name="X",
            predicate="links",
            normalized_text="X links Y",
            confidence=-0.1,
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_rejects_empty_subject(self) -> None:
        from mapu.mcp.server import contribute_proposition

        result = await contribute_proposition(
            corpus_id=str(uuid.uuid4()),
            subject_name="   ",
            predicate="links",
            normalized_text="X links Y",
        )
        assert "error" in result
        assert "empty" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_empty_predicate(self) -> None:
        from mapu.mcp.server import contribute_proposition

        result = await contribute_proposition(
            corpus_id=str(uuid.uuid4()),
            subject_name="X",
            predicate="   ",
            normalized_text="X links Y",
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_rejects_invalid_stance(self) -> None:
        from mapu.mcp.server import contribute_proposition

        result = await contribute_proposition(
            corpus_id=str(uuid.uuid4()),
            subject_name="X",
            predicate="links",
            normalized_text="X links Y",
            stance="invalid",
        )
        assert "error" in result
        assert "stance" in result["error"]


class TestQueryEpistemicStatus:
    @pytest.mark.asyncio
    async def test_query_includes_epistemic_status(self) -> None:
        from mapu.query.types import (
            EpistemicStatus,
            QueryIntent,
            QueryRequest,
            QueryResult,
            Tier,
        )

        cid = uuid.uuid4()
        mock_result = QueryResult(
            request=QueryRequest(corpus_id=cid, question="test"),
            intent=QueryIntent.IDENTITY,
            tier_used=Tier.DIRECT,
            synthesis=None,
            hits=(),
            gaps=(),
            metadata={"test": True},
            epistemic_status=EpistemicStatus.INSUFFICIENT,
        )

        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
        ):
            from mapu.mcp.server import query

            result = await query(corpus_id=str(cid), question="test")

        assert result["epistemic_status"] == "insufficient"
        assert result["metadata"] == {"test": True}


class TestInvestigateTool:
    @pytest.mark.asyncio
    async def test_investigate_returns_answer_and_evidence(self) -> None:
        from mapu.investigation.types import (
            InvestigationEvidence,
            InvestigationResult,
            TerminationReason,
        )

        ev = InvestigationEvidence(
            proposition_id=uuid.uuid4(),
            normalized_text="X causes Y",
            source_span="from doc",
            authority_score=0.8,
            document_id=uuid.uuid4(),
        )
        mock_result = InvestigationResult(
            answer="X causes Y based on evidence",
            evidence=(ev,),
            gaps=("missing context",),
            findings=(),
            metadata={"actions_executed": 3},
            termination_reason=TerminationReason.COVERAGE_MET,
        )

        mock_svc = AsyncMock()
        mock_svc.investigate = AsyncMock(return_value=mock_result)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.investigation.service.InvestigationService", return_value=mock_svc),
            patch("mapu.providers.llms.get_default_llm_provider", return_value=MagicMock()),
            patch("mapu.providers.embeddings.get_default_embedding_provider"),
        ):
            from mapu.mcp.server import investigate

            result = await investigate(
                corpus_id=str(uuid.uuid4()),
                question="What causes Y?",
            )

        assert result["answer"] == "X causes Y based on evidence"
        assert len(result["evidence"]) == 1
        assert result["gaps"] == ["missing context"]
        assert result["termination_reason"] == "coverage_met"
        assert "next_steps" in result

    @pytest.mark.asyncio
    async def test_investigate_without_llm_returns_error(self) -> None:
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.providers.llms.get_default_llm_provider", return_value=None),
            patch("mapu.providers.embeddings.get_default_embedding_provider"),
        ):
            from mapu.mcp.server import investigate

            result = await investigate(
                corpus_id=str(uuid.uuid4()),
                question="What causes Y?",
            )

        assert "error" in result

    @pytest.mark.asyncio
    async def test_investigate_clamps_budget(self) -> None:
        from mapu.investigation.types import (
            InvestigationResult,
            TerminationReason,
        )

        mock_result = InvestigationResult(
            answer="answer",
            evidence=(),
            gaps=(),
            findings=(),
            metadata={},
            termination_reason=TerminationReason.PLANNER_STOP,
        )
        mock_svc = AsyncMock()
        mock_svc.investigate = AsyncMock(return_value=mock_result)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.investigation.service.InvestigationService", return_value=mock_svc),
            patch("mapu.investigation.types.InvestigationBudget") as mock_budget_cls,
            patch("mapu.providers.llms.get_default_llm_provider", return_value=MagicMock()),
            patch("mapu.providers.embeddings.get_default_embedding_provider"),
        ):
            from mapu.mcp.server import investigate

            await investigate(
                corpus_id=str(uuid.uuid4()),
                question="test",
                max_llm_calls=999,
                max_actions=999,
            )

        call_kwargs = mock_budget_cls.call_args[1]
        assert call_kwargs["max_llm_calls"] == 50
        assert call_kwargs["max_actions"] == 100


class TestListGapsTool:
    @pytest.mark.asyncio
    async def test_list_gaps_returns_gaps(self) -> None:
        from datetime import UTC, datetime

        gap = MagicMock()
        gap.id = uuid.uuid4()
        gap.kind = "missing_evidence"
        gap.description = "No data for entity X"
        gap.severity = "moderate"
        gap.status = "open"
        gap.detected_by = "investigation"
        gap.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        gap.resolved_at = None

        mock_repo = AsyncMock()
        mock_repo.list = AsyncMock(return_value=[gap])
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.repos.gap.GapRepo", return_value=mock_repo),
        ):
            from mapu.mcp.server import list_gaps

            result = await list_gaps(corpus_id=str(uuid.uuid4()))

        assert len(result["gaps"]) == 1
        assert result["gaps"][0]["kind"] == "missing_evidence"
        assert result["gaps"][0]["status"] == "open"


class TestListActivityTool:
    @pytest.mark.asyncio
    async def test_list_activity_returns_events(self) -> None:
        from datetime import UTC, datetime

        activity = MagicMock()
        activity.id = uuid.uuid4()
        activity.event_type = "ingestion"
        activity.actor = "system"
        activity.entity_type = "document"
        activity.entity_id = uuid.uuid4()
        activity.details = {"doc": "test.pdf"}
        activity.created_at = datetime(2026, 1, 1, tzinfo=UTC)

        mock_repo = AsyncMock()
        mock_repo.list = AsyncMock(return_value=[activity])
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_repo),
        ):
            from mapu.mcp.server import list_activity

            result = await list_activity(corpus_id=str(uuid.uuid4()))

        assert len(result["activities"]) == 1
        assert result["activities"][0]["event_type"] == "ingestion"
        assert result["activities"][0]["actor"] == "system"


class TestHandoffContextTool:
    @pytest.mark.asyncio
    async def test_handoff_context_returns_structured_bundle(self) -> None:
        from datetime import UTC, datetime

        gap = MagicMock()
        gap.id = uuid.uuid4()
        gap.kind = "dependency"
        gap.description = "Missing dependency mapping for ACME"
        gap.severity = "critical"
        gap.status = "open"
        gap.detected_by = "investigation"
        gap.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        gap.resolved_at = None

        activity = MagicMock()
        activity.id = uuid.uuid4()
        activity.event_type = "supersession"
        activity.actor = "agent"
        activity.entity_type = "proposition"
        activity.entity_id = uuid.uuid4()
        activity.details = {"proposition_id": "old-1", "new_proposition_id": "new-1"}
        activity.created_at = datetime(2026, 1, 2, tzinfo=UTC)

        mock_gap_repo = MagicMock()
        mock_gap_repo.list = AsyncMock(return_value=[gap])
        mock_activity_repo = MagicMock()
        mock_activity_repo.list = AsyncMock(return_value=[activity])

        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.repos.gap.GapRepo", return_value=mock_gap_repo),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_activity_repo),
        ):
            from mapu.mcp.server import handoff_context

            corpus_id = str(uuid.uuid4())
            result = await handoff_context(
                corpus_id=corpus_id,
                max_gaps=10,
                max_activity=20,
            )

        assert result["protocol_version"] == "1.1.0"
        assert result["protocol"] == "mapu-resume-handoff"
        assert result["corpus_id"] == corpus_id
        assert len(result["open_gaps"]) == 1
        assert result["continuity_frontier"]["open_gap_count"] == 1
        assert result["continuity_frontier"]["unresolved_conflict_count"] == 1
        assert result["priority_next_actions"]
        assert "continuity_governance" in result
        assert set(result["continuity_governance"].keys()) == {
            "guaranteed_fields",
            "provisional_fields",
            "stale_fields",
        }
        assert any(
            action["action_type"] == "list_activity" for action in result["priority_next_actions"]
        )

    @pytest.mark.asyncio
    async def test_handoff_context_clamps_max_actions(self) -> None:
        from datetime import UTC, datetime

        gap = MagicMock()
        gap.id = uuid.uuid4()
        gap.kind = "knowledge"
        gap.description = "Missing context"
        gap.severity = "minor"
        gap.status = "open"
        gap.detected_by = "query"
        gap.created_at = datetime(2026, 1, 1, tzinfo=UTC)
        gap.resolved_at = None

        mock_gap_repo = MagicMock()
        mock_gap_repo.list = AsyncMock(return_value=[gap])
        mock_activity_repo = MagicMock()
        mock_activity_repo.list = AsyncMock(return_value=[])

        session = _mock_session()
        with (
            _patch_factory(session),
            patch("mapu.repos.gap.GapRepo", return_value=mock_gap_repo),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_activity_repo),
            patch(
                "mapu.context_learning.build_handoff_bundle",
                return_value={
                    "protocol_version": "1.1.0",
                    "protocol": "mapu-resume-handoff",
                    "continuity_governance": {
                        "guaranteed_fields": ["protocol_version", "protocol"],
                        "provisional_fields": ["query(corpus_id='...')"],
                        "stale_fields": [],
                    },
                },
            ) as mock_build_bundle,
        ):
            from mapu.mcp.server import handoff_context

            await handoff_context(
                corpus_id=str(uuid.uuid4()),
                max_gaps=6,
                max_activity=8,
                max_actions=999,
            )

        call_kwargs = mock_build_bundle.call_args[1]
        assert call_kwargs["max_actions"] == 30
        assert call_kwargs["max_gaps"] == 6
        assert call_kwargs["max_activity"] == 8


class TestLearningFeedbackTool:
    @pytest.mark.asyncio
    async def test_log_learning_feedback_records_event(self) -> None:
        activity = MagicMock()
        activity.id = uuid.uuid4()
        mock_repo = AsyncMock()
        mock_repo.log = AsyncMock(return_value=activity)
        session = _mock_session()

        with (
            _patch_factory(session),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_repo),
        ):
            from mapu.mcp.server import log_learning_feedback

            result = await log_learning_feedback(
                corpus_id=str(uuid.uuid4()),
                question="What is X?",
                step="Open a focused query",
                outcome="helpful",
            )

        assert result["success"] is True
        assert result["event_id"] == str(activity.id)

    @pytest.mark.asyncio
    async def test_log_learning_feedback_validates_outcome(self) -> None:
        with (
            _patch_factory(_mock_session()),
            patch("mapu.repos.audit.ActivityRepo"),
        ):
            from mapu.mcp.server import log_learning_feedback

            result = await log_learning_feedback(
                corpus_id=str(uuid.uuid4()),
                question="What is X?",
                step="Open a focused query",
                outcome="invalid",
            )

        assert "error" in result
        assert "outcome" in result["error"]


class TestBadUUIDHandling:
    @pytest.mark.asyncio
    async def test_investigate_bad_corpus_id(self) -> None:
        from mapu.mcp.server import investigate

        result = await investigate(corpus_id="not-a-uuid", question="Why?")
        assert "error" in result
        assert "corpus_id" in result["error"]

    @pytest.mark.asyncio
    async def test_investigate_bad_situation_id(self) -> None:
        from mapu.mcp.server import investigate

        result = await investigate(
            corpus_id=str(uuid.uuid4()),
            question="Why?",
            situation_id="bad",
        )
        assert "error" in result
        assert "situation_id" in result["error"]

    @pytest.mark.asyncio
    async def test_list_gaps_bad_corpus_id(self) -> None:
        from mapu.mcp.server import list_gaps

        result = await list_gaps(corpus_id="bad-uuid")
        assert "error" in result
        assert "corpus_id" in result["error"]

    @pytest.mark.asyncio
    async def test_list_activity_bad_corpus_id(self) -> None:
        from mapu.mcp.server import list_activity

        result = await list_activity(corpus_id="bad-uuid")
        assert "error" in result
        assert "corpus_id" in result["error"]

    @pytest.mark.asyncio
    async def test_list_activity_bad_entity_id(self) -> None:
        from mapu.mcp.server import list_activity

        result = await list_activity(
            corpus_id=str(uuid.uuid4()),
            entity_id="bad",
        )
        assert "error" in result
        assert "entity_id" in result["error"]


class TestAgentSurfaceContracts:
    @pytest.mark.asyncio
    async def test_query_commits_learned_gaps_and_activity(self) -> None:
        from mapu.query.types import QueryIntent, QueryRequest, QueryResult, Tier

        cid = uuid.uuid4()
        mock_result = QueryResult(
            request=QueryRequest(corpus_id=cid, question="What changed?"),
            intent=QueryIntent.IDENTITY,
            tier_used=Tier.DIRECT,
            synthesis="Answer",
            hits=(),
            gaps=(),
            metadata={},
        )
        mock_svc = AsyncMock()
        mock_svc.query = AsyncMock(return_value=mock_result)
        session = _mock_session()
        session.get = AsyncMock(return_value=object())

        with (
            _patch_factory(session),
            patch("mapu.query.intent.HeuristicIntentClassifier"),
            patch("mapu.query.service.QueryService", return_value=mock_svc),
        ):
            from mapu.mcp.server import query

            result = await query(corpus_id=str(cid), question="What changed?")

        assert result["synthesis"] == "Answer"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handoff_context_rejects_missing_corpus(self) -> None:
        session = _mock_session()
        session.get = AsyncMock(return_value=None)

        with _patch_factory(session):
            from mapu.mcp.server import handoff_context

            result = await handoff_context(corpus_id=str(uuid.uuid4()))

        assert result["code"] == "corpus_not_found"
        assert "not found" in result["error"]
