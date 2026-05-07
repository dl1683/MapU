"""Unit tests for API DTOs and controller logic."""

from __future__ import annotations

import uuid

import pytest

from mapu.api.dtos import (
    CorpusCreate,
    CorpusResponse,
    HandleResponse,
    HealthResponse,
    HitResponse,
    IngestRequestDTO,
    IngestResponse,
    QueryRequestDTO,
    QueryResponse,
    RepairApplyResponse,
    RepairPreviewResponse,
    RepairProposeRequest,
)


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
            synthesis="Answer",
            hits=[],
            gaps=["missing"],
        )
        data = resp.model_dump()
        assert data["intent"] == "factual"
        assert data["gaps"] == ["missing"]
        assert data["hits"] == []

    def test_ingest_request_defaults(self) -> None:
        dto = IngestRequestDTO(content="Hello world")
        assert dto.mime_type == "text/plain"
        assert dto.source_uri == ""

    def test_ingest_response(self) -> None:
        doc_id = uuid.uuid4()
        expr_id = uuid.uuid4()
        resp = IngestResponse(
            document_id=doc_id, expression_id=expr_id,
            spans=5, chunks=3, embeddings=3,
        )
        assert resp.spans == 5
        assert resp.chunks == 3
        assert resp.embeddings == 3

    def test_handle_response(self) -> None:
        hid = uuid.uuid4()
        resp = HandleResponse(
            id=hid, canonical_name="Entity", kind="org", aliases=["E", "Ent"],
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
