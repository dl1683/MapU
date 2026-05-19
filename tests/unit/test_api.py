"""Unit tests for API DTOs and controller logic."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from mapu.api.app import create_app
from mapu.api.dtos import (
    CorpusCreate,
    CorpusResponse,
    HandleResponse,
    HealthResponse,
    HitResponse,
    IngestRequestDTO,
    IngestResponse,
    LearningFeedbackRequest,
    LearningFeedbackResponse,
    QueryRequestDTO,
    QueryResponse,
    RepairApplyResponse,
    RepairPreviewResponse,
    RepairProposeRequest,
    ResumeHandoffResponse,
)
from mapu.config import ServerSettings, Settings


class TestDTOSerialization:
    def test_corpus_create_minimal(self) -> None:
        dto = CorpusCreate(name="test")
        assert dto.name == "test"
        assert dto.description == ""

    def test_corpus_create_with_description(self) -> None:
        dto = CorpusCreate(name="test", description="A test corpus")
        assert dto.description == "A test corpus"

    def test_corpus_response_roundtrip(self) -> None:
        cid = uuid.uuid4()
        resp = CorpusResponse(id=cid, name="test", description="desc")
        data = resp.model_dump()
        assert data["id"] == cid
        assert data["name"] == "test"

    def test_corpus_response_optional_description(self) -> None:
        resp = CorpusResponse(id=uuid.uuid4(), name="test")
        assert resp.description is None

    def test_query_request_defaults(self) -> None:
        dto = QueryRequestDTO(question="What is X?")
        assert dto.max_results == 20
        assert dto.situation_id is None

    def test_query_request_with_situation(self) -> None:
        sid = uuid.uuid4()
        dto = QueryRequestDTO(question="What?", situation_id=sid)
        assert dto.situation_id == sid

    def test_hit_response_fields(self) -> None:
        pid = uuid.uuid4()
        hit = HitResponse(
            proposition_id=pid,
            normalized_text="X defines Y",
            predicate="defines",
            subject_name="X",
            object_name="Y",
            confidence=0.95,
            authority_score=0.8,
        )
        data = hit.model_dump()
        assert data["proposition_id"] == pid
        assert data["confidence"] == 0.95
        assert data["object_name"] == "Y"

    def test_hit_response_optional_object(self) -> None:
        hit = HitResponse(
            proposition_id=uuid.uuid4(),
            normalized_text="X exists",
            predicate="exists",
            subject_name="X",
            confidence=0.9,
        )
        assert hit.object_name is None
        assert hit.authority_score is None

    def test_query_response_structure(self) -> None:
        resp = QueryResponse(
            intent="factual",
            tier_used="DIRECT",
            answer="Answer",
            synthesis="Answer",
            hits=[],
            gaps=["missing"],
            next_steps=["Investigate with focused entity query"],
        )
        data = resp.model_dump()
        assert data["answer"] == "Answer"
        assert data["synthesis"] == "Answer"
        assert data["intent"] == "factual"
        assert data["gaps"] == ["missing"]
        assert data["hits"] == []
        assert data["next_steps"] == ["Investigate with focused entity query"]

    def test_ingest_request_defaults(self) -> None:
        dto = IngestRequestDTO(content="Hello world")
        assert dto.mime_type == "text/plain"
        assert dto.source_uri == ""

    def test_learning_feedback_request(self) -> None:
        event_id = uuid.uuid4()
        req = LearningFeedbackRequest(
            question="What is X?",
            step="Run entity deep-dive",
            outcome="helpful",
            actor="agent",
            source_event_type="query",
            source_event_id=event_id,
        )
        data = req.model_dump()
        assert data["question"] == "What is X?"
        assert data["outcome"] == "helpful"
        assert data["step"] == "Run entity deep-dive"
        assert data["source_event_id"] == event_id

    def test_learning_feedback_response(self) -> None:
        resp = LearningFeedbackResponse(success=True, event_id=uuid.uuid4())
        assert resp.success is True
        assert isinstance(resp.event_id, uuid.UUID)

    def test_ingest_response(self) -> None:
        doc_id = uuid.uuid4()
        expr_id = uuid.uuid4()
        resp = IngestResponse(
            document_id=doc_id,
            expression_id=expr_id,
            spans=5,
            chunks=3,
            embeddings=3,
        )
        assert resp.spans == 5
        assert resp.chunks == 3
        assert resp.embeddings == 3

    def test_handle_response(self) -> None:
        hid = uuid.uuid4()
        resp = HandleResponse(
            id=hid,
            canonical_name="Entity",
            kind="org",
            aliases=["E", "Ent"],
        )
        assert resp.canonical_name == "Entity"
        assert len(resp.aliases) == 2

    def test_repair_preview_response(self) -> None:
        resp = RepairPreviewResponse(
            root_proposition_id=uuid.uuid4(),
            affected_count=3,
            recompute_only_count=1,
            risk_level="medium",
            max_depth=2,
            depth_limited=False,
        )
        assert resp.affected_count == 3
        assert resp.risk_level == "medium"

    def test_repair_apply_response(self) -> None:
        resp = RepairApplyResponse(
            changeset_id=uuid.uuid4(),
            success=True,
            operations_executed=2,
            recomputed_propositions=1,
            gaps_created=0,
            errors=[],
        )
        assert resp.success is True
        assert resp.errors == []

    def test_repair_apply_response_with_errors(self) -> None:
        resp = RepairApplyResponse(
            changeset_id=uuid.uuid4(),
            success=False,
            operations_executed=0,
            recomputed_propositions=0,
            gaps_created=0,
            errors=["Operation failed"],
        )
        assert resp.success is False
        assert len(resp.errors) == 1

    def test_health_response(self) -> None:
        resp = HealthResponse(status="ok", version="0.1.0")
        assert resp.status == "ok"


class TestDTOValidation:
    def test_corpus_create_requires_name(self) -> None:
        with pytest.raises(ValueError):
            CorpusCreate.model_validate({})

    def test_query_request_requires_question(self) -> None:
        with pytest.raises(ValueError):
            QueryRequestDTO.model_validate({})

    def test_ingest_request_requires_content(self) -> None:
        with pytest.raises(ValueError):
            IngestRequestDTO.model_validate({})

    def test_hit_response_json_roundtrip(self) -> None:
        hit = HitResponse(
            proposition_id=uuid.uuid4(),
            normalized_text="test",
            predicate="defines",
            subject_name="X",
            confidence=0.9,
        )
        json_str = hit.model_dump_json()
        restored = HitResponse.model_validate_json(json_str)
        assert restored.proposition_id == hit.proposition_id
        assert restored.confidence == hit.confidence

    def test_max_results_bounds(self) -> None:
        with pytest.raises(ValueError):
            QueryRequestDTO(question="test", max_results=0)
        with pytest.raises(ValueError):
            QueryRequestDTO(question="test", max_results=501)

    def test_corpus_name_max_length(self) -> None:
        with pytest.raises(ValueError):
            CorpusCreate(name="x" * 501)

    def test_ingest_content_max_length(self) -> None:
        with pytest.raises(ValueError):
            IngestRequestDTO(content="x" * 10_000_001)

    def test_ingest_content_byte_length_check(self) -> None:
        multibyte = "\U0001f600" * 2_500_001  # 4 bytes each = 10,000,004 bytes
        with pytest.raises(ValueError, match="UTF-8"):
            IngestRequestDTO(content=multibyte)

    def test_repair_propose_request_defaults(self) -> None:
        pid = uuid.uuid4()
        dto = RepairProposeRequest(proposition_id=pid)
        assert dto.operation == "retract"
        assert dto.reason == ""
        assert dto.actor == "user"

    def test_repair_propose_rejects_invalid_operation(self) -> None:
        with pytest.raises(ValueError):
            RepairProposeRequest(proposition_id=uuid.uuid4(), operation="delete")

    def test_learning_feedback_outcome_validation(self) -> None:
        with pytest.raises(ValueError):
            LearningFeedbackRequest(
                question="What is X?",
                step="Test",
                outcome="bad",
            )


class TestAppConfiguration:
    def test_api_key_is_stored_for_guard(self) -> None:
        app = create_app(Settings(server=ServerSettings(api_key="secret-key")))

        assert app.state["api_key"] == "secret-key"

    def test_empty_cors_origins_disable_cors_config(self) -> None:
        app = create_app(Settings(server=ServerSettings(cors_origins="")))

        assert app.cors_config is None

    def test_cors_origins_are_parsed_from_settings(self) -> None:
        app = create_app(
            Settings(
                server=ServerSettings(
                    cors_origins="https://one.example, https://two.example",
                )
            )
        )

        assert app.cors_config is not None
        assert app.cors_config.allow_origins == [
            "https://one.example",
            "https://two.example",
        ]
        assert "x-api-key" in app.cors_config.allow_headers

    def test_health_endpoint_handles_http_request(self) -> None:
        from litestar.testing import TestClient

        app = create_app(Settings())

        with TestClient(app=app) as client:
            response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "version": "0.1.0"}

    def test_api_key_guard_rejects_missing_key_on_http_request(self) -> None:
        from litestar.testing import TestClient

        app = create_app(Settings(server=ServerSettings(api_key="secret-key")))

        with TestClient(app=app) as client:
            response = client.get("/health")

        assert response.status_code == 401

    def test_api_key_guard_accepts_matching_key_on_http_request(self) -> None:
        from litestar.testing import TestClient

        app = create_app(Settings(server=ServerSettings(api_key="secret-key")))

        with TestClient(app=app) as client:
            response = client.get("/health", headers={"x-api-key": "secret-key"})

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "version": "0.1.0"}

    def test_resume_route_is_registered(self) -> None:
        app = create_app(Settings())
        paths = [route.path for route in app.routes]
        assert "/corpora/{corpus_id:uuid}/resume" in paths


class TestResumeEndpoint:
    @pytest.mark.asyncio
    async def test_resume_controller_returns_structured_handoff_bundle(self) -> None:
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from mapu.api.controllers import ResumeController

        corpus_id = uuid.uuid4()
        gap = SimpleNamespace(
            id=uuid.uuid4(),
            kind="dependency",
            description="Missing source lineage for ACME claims",
            severity="critical",
            status="open",
            detected_by="query",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            resolved_at=None,
        )
        activity = SimpleNamespace(
            id=uuid.uuid4(),
            event_type="supersession",
            actor="agent",
            entity_type="proposition",
            entity_id=uuid.uuid4(),
            details={"proposition_id": "old-1", "new_proposition_id": "new-1"},
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )

        mock_gap_repo = AsyncMock()
        mock_gap_repo.list = AsyncMock(return_value=[gap])
        mock_activity_repo = AsyncMock()
        mock_activity_repo.list = AsyncMock(return_value=[activity])

        with (
            patch("mapu.api.controllers._require_corpus", return_value=None),
            patch("mapu.repos.gap.GapRepo", return_value=mock_gap_repo),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_activity_repo),
        ):
            result = await ResumeController.__dict__["resume"].fn(
                ResumeController(owner=object()),
                corpus_id=corpus_id,
                db_session=AsyncMock(),
                max_gaps=10,
                max_activity=20,
                max_actions=12,
            )

        handoff = ResumeHandoffResponse.model_validate(result)
        assert handoff.protocol_version == "1.1.0"
        assert handoff.protocol == "mapu-resume-handoff"
        assert handoff.corpus_id == str(corpus_id)
        assert handoff.continuity_frontier.open_gap_count == 1
        assert handoff.continuity_frontier.unresolved_conflict_count == 1
        assert len(handoff.open_gaps) == 1
        assert handoff.priority_next_actions
        assert len(handoff.continuity_governance.guaranteed_fields) >= 1
        assert isinstance(handoff.continuity_governance.provisional_fields, list)
        assert isinstance(handoff.continuity_governance.stale_fields, list)

    @pytest.mark.asyncio
    async def test_resume_controller_clamps_max_actions(self) -> None:
        from mapu.api.controllers import ResumeController

        mock_gap_repo = AsyncMock()
        mock_gap_repo.list = AsyncMock(return_value=[])
        mock_activity_repo = AsyncMock()
        mock_activity_repo.list = AsyncMock(return_value=[])

        corpus_id = uuid.uuid4()
        with (
            patch("mapu.api.controllers._require_corpus", return_value=None),
            patch(
                "mapu.context_learning.build_handoff_bundle",
                return_value={
                    "protocol_version": "1.1.0",
                    "protocol": "mapu-resume-handoff",
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "continuity_role": "claude-style handoff",
                    "corpus_id": str(corpus_id),
                    "open_gaps": [],
                    "recent_activity": [],
                    "continuity_frontier": {
                        "open_gap_count": 0,
                        "critical_open_gap_count": 0,
                        "unresolved_conflict_count": 0,
                        "unresolved_gap_ids": [],
                        "unresolved_conflicts": [],
                        "action_count": 1,
                    },
                    "continuity_governance": {
                        "guaranteed_fields": ["protocol_version", "protocol"],
                        "provisional_fields": ["query(corpus_id='...')"],
                        "stale_fields": [],
                    },
                    "priority_next_actions": [
                        {
                            "action_type": "query",
                            "step": "query(...)",
                            "rationale": "fallback",
                            "target": {},
                            "expected_signal_target": {},
                            "uncertainty_reason": "no_open_gaps",
                            "gap_ids": [],
                            "activity_ids": [],
                            "confidence": 0.1,
                        }
                    ],
                },
            ) as mock_build_bundle,
            patch("mapu.repos.gap.GapRepo", return_value=mock_gap_repo),
            patch("mapu.repos.audit.ActivityRepo", return_value=mock_activity_repo),
        ):
            await ResumeController.__dict__["resume"].fn(
                ResumeController(owner=object()),
                corpus_id=corpus_id,
                db_session=AsyncMock(),
                max_gaps=10,
                max_activity=20,
                max_actions=999,
            )

        call_kwargs = mock_build_bundle.call_args[1]
        assert call_kwargs["max_actions"] == 30
        assert call_kwargs["max_gaps"] == 10
        assert call_kwargs["max_activity"] == 20
