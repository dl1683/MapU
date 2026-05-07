"""Unit tests for the MapU MCP server tool functions."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
        assert result["synthesis"] == "X defines Y"
        assert len(result["hits"]) == 1
        assert result["hits"][0]["predicate"] == "defines"
        assert result["hits"][0]["confidence"] == 0.95

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
