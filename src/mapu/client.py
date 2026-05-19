"""MapU Python SDK — async and sync HTTP clients for the MapU REST API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import httpx


class AsyncMapUClient:
    """Async HTTP client for the MapU REST API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url, headers=headers, timeout=timeout,
        )

    async def __aenter__(self) -> AsyncMapUClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(
        self, method: str, path: str, **kwargs: Any,
    ) -> Any:
        resp = await self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def create_corpus(
        self, name: str, description: str = "",
    ) -> dict[str, Any]:
        return await self._request(
            "POST", "/corpora", json={"name": name, "description": description},
        )

    async def list_corpora(self, limit: int = 100) -> list[dict[str, Any]]:
        return await self._request("GET", "/corpora", params={"limit": limit})

    async def get_corpus(self, corpus_id: uuid.UUID) -> dict[str, Any]:
        return await self._request("GET", f"/corpora/{corpus_id}")

    async def query(
        self,
        corpus_id: uuid.UUID,
        question: str,
        max_results: int = 20,
        situation_id: uuid.UUID | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "question": question,
            "max_results": max_results,
        }
        if situation_id:
            body["situation_id"] = str(situation_id)
        if as_of:
            body["as_of"] = as_of.isoformat()
        return await self._request(
            "POST", f"/corpora/{corpus_id}/query", json=body,
        )

    async def ingest_document(
        self,
        corpus_id: uuid.UUID,
        content: str,
        mime_type: str = "text/plain",
        source_uri: str = "",
        document_type: str | None = None,
        publication_context: str | None = None,
        source_identity: str | None = None,
        independence_group: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "content": content,
            "mime_type": mime_type,
            "source_uri": source_uri,
        }
        if document_type:
            body["document_type"] = document_type
        if publication_context:
            body["publication_context"] = publication_context
        if source_identity:
            body["source_identity"] = source_identity
        if independence_group:
            body["independence_group"] = independence_group
        return await self._request(
            "POST", f"/corpora/{corpus_id}/documents", json=body,
        )

    async def lookup_entities(
        self, corpus_id: uuid.UUID, name: str, limit: int = 20,
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET", f"/corpora/{corpus_id}/entities",
            params={"name": name, "limit": limit},
        )

    async def investigate(
        self,
        corpus_id: uuid.UUID,
        question: str,
        initial_entities: list[str] | None = None,
        initial_predicates: list[str] | None = None,
        situation_id: uuid.UUID | None = None,
        max_llm_calls: int = 10,
        max_actions: int = 25,
        max_documents_read: int = 50,
        target_coverage: float = 0.9,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "question": question,
            "initial_entities": initial_entities or [],
            "initial_predicates": initial_predicates or [],
            "budget": {
                "max_llm_calls": max_llm_calls,
                "max_actions": max_actions,
                "max_documents_read": max_documents_read,
                "target_coverage": target_coverage,
            },
        }
        if situation_id:
            body["situation_id"] = str(situation_id)
        return await self._request(
            "POST", f"/corpora/{corpus_id}/investigations", json=body,
        )

    async def repair_preview(
        self, corpus_id: uuid.UUID, proposition_id: uuid.UUID,
    ) -> dict[str, Any]:
        return await self._request(
            "POST", f"/corpora/{corpus_id}/repair/preview",
            params={"proposition_id": str(proposition_id)},
        )

    async def repair_propose(
        self,
        corpus_id: uuid.UUID,
        proposition_id: uuid.UUID,
        reason: str = "",
        actor: str = "sdk",
    ) -> dict[str, Any]:
        return await self._request(
            "POST", f"/corpora/{corpus_id}/repair/propose",
            json={
                "proposition_id": str(proposition_id),
                "reason": reason,
                "actor": actor,
            },
        )

    async def repair_apply(
        self, corpus_id: uuid.UUID, changeset_id: uuid.UUID,
    ) -> dict[str, Any]:
        return await self._request(
            "POST", f"/corpora/{corpus_id}/repair/apply/{changeset_id}",
        )

    async def repair_approve(
        self, corpus_id: uuid.UUID, changeset_id: uuid.UUID,
    ) -> dict[str, Any]:
        return await self._request(
            "POST", f"/corpora/{corpus_id}/repair/approve/{changeset_id}",
        )

    async def repair_rollback(
        self, corpus_id: uuid.UUID, changeset_id: uuid.UUID,
    ) -> dict[str, Any]:
        return await self._request(
            "POST", f"/corpora/{corpus_id}/repair/rollback/{changeset_id}",
        )

    async def contribute_proposition(
        self,
        corpus_id: uuid.UUID,
        subject_name: str,
        predicate: str,
        normalized_text: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "subject_name": subject_name,
            "predicate": predicate,
            "normalized_text": normalized_text,
            **kwargs,
        }
        return await self._request(
            "POST", f"/corpora/{corpus_id}/contributions", json=body,
        )

    async def review_attestation(
        self,
        corpus_id: uuid.UUID,
        attestation_id: uuid.UUID,
        decision: str,
        actor: str = "sdk",
        reason: str = "",
    ) -> dict[str, Any]:
        return await self._request(
            "POST", f"/corpora/{corpus_id}/contributions/review",
            json={
                "attestation_id": str(attestation_id),
                "decision": decision,
                "actor": actor,
                "reason": reason,
            },
        )

    async def list_gaps(
        self,
        corpus_id: uuid.UUID,
        status: str = "open",
        kind: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"status": status, "limit": limit}
        if kind:
            params["kind"] = kind
        if severity:
            params["severity"] = severity
        return await self._request(
            "GET", f"/corpora/{corpus_id}/gaps", params=params,
        )

    async def list_activity(
        self,
        corpus_id: uuid.UUID,
        limit: int = 50,
        event_type: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if event_type:
            params["event_type"] = event_type
        if entity_type:
            params["entity_type"] = entity_type
        if entity_id:
            params["entity_id"] = str(entity_id)
        return await self._request(
            "GET", f"/corpora/{corpus_id}/activity", params=params,
        )

    async def resume(
        self,
        corpus_id: uuid.UUID,
        max_gaps: int = 10,
        max_activity: int = 20,
        max_actions: int = 10,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/corpora/{corpus_id}/resume",
            params={
                "max_gaps": max_gaps,
                "max_activity": max_activity,
                "max_actions": max_actions,
            },
        )

    async def list_situations(
        self, corpus_id: uuid.UUID, limit: int = 100,
    ) -> list[dict[str, Any]]:
        return await self._request(
            "GET", f"/corpora/{corpus_id}/situations",
            params={"limit": limit},
        )

    async def log_learning_feedback(
        self,
        corpus_id: uuid.UUID,
        question: str,
        step: str,
        outcome: str,
        actor: str = "sdk",
        source_event_type: str = "query",
        source_event_id: uuid.UUID | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "question": question,
            "step": step,
            "outcome": outcome,
            "actor": actor,
            "source_event_type": source_event_type,
            "notes": notes,
        }
        if source_event_id:
            body["source_event_id"] = str(source_event_id)
        return await self._request(
            "POST", f"/corpora/{corpus_id}/activity/feedback", json=body,
        )

    async def create_situation(
        self,
        corpus_id: uuid.UUID,
        name: str,
        kind: str = "user",
        parent_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        assumptions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "kind": kind}
        if parent_id:
            body["parent_id"] = str(parent_id)
        if document_id:
            body["document_id"] = str(document_id)
        if assumptions:
            body["assumptions"] = assumptions
        return await self._request(
            "POST", f"/corpora/{corpus_id}/situations", json=body,
        )

    async def get_situation(
        self, corpus_id: uuid.UUID, situation_id: uuid.UUID,
    ) -> dict[str, Any]:
        return await self._request(
            "GET", f"/corpora/{corpus_id}/situations/{situation_id}",
        )


class MapUClient:
    """Sync HTTP client for the MapU REST API.

    Uses httpx.Client directly — safe to use inside or outside async contexts.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.Client(
            base_url=base_url, headers=headers, timeout=timeout,
        )

    def __enter__(self) -> MapUClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_corpus(self, name: str, description: str = "") -> dict[str, Any]:
        return self._request(
            "POST", "/corpora", json={"name": name, "description": description},
        )

    def list_corpora(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", "/corpora", params={"limit": limit})

    def get_corpus(self, corpus_id: uuid.UUID) -> dict[str, Any]:
        return self._request("GET", f"/corpora/{corpus_id}")

    def query(
        self,
        corpus_id: uuid.UUID,
        question: str,
        max_results: int = 20,
        situation_id: uuid.UUID | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"question": question, "max_results": max_results}
        if situation_id:
            body["situation_id"] = str(situation_id)
        if as_of:
            body["as_of"] = as_of.isoformat()
        return self._request("POST", f"/corpora/{corpus_id}/query", json=body)

    def ingest_document(
        self,
        corpus_id: uuid.UUID,
        content: str,
        mime_type: str = "text/plain",
        source_uri: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "content": content, "mime_type": mime_type,
            "source_uri": source_uri, **kwargs,
        }
        return self._request("POST", f"/corpora/{corpus_id}/documents", json=body)

    def lookup_entities(
        self, corpus_id: uuid.UUID, name: str, limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET", f"/corpora/{corpus_id}/entities",
            params={"name": name, "limit": limit},
        )

    def investigate(
        self,
        corpus_id: uuid.UUID,
        question: str,
        initial_entities: list[str] | None = None,
        initial_predicates: list[str] | None = None,
        situation_id: uuid.UUID | None = None,
        max_llm_calls: int = 10,
        max_actions: int = 25,
        max_documents_read: int = 50,
        target_coverage: float = 0.9,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "question": question,
            "initial_entities": initial_entities or [],
            "initial_predicates": initial_predicates or [],
            "budget": {
                "max_llm_calls": max_llm_calls,
                "max_actions": max_actions,
                "max_documents_read": max_documents_read,
                "target_coverage": target_coverage,
            },
        }
        if situation_id:
            body["situation_id"] = str(situation_id)
        return self._request("POST", f"/corpora/{corpus_id}/investigations", json=body)

    def repair_preview(
        self, corpus_id: uuid.UUID, proposition_id: uuid.UUID,
    ) -> dict[str, Any]:
        return self._request(
            "POST", f"/corpora/{corpus_id}/repair/preview",
            params={"proposition_id": str(proposition_id)},
        )

    def repair_propose(
        self, corpus_id: uuid.UUID, proposition_id: uuid.UUID,
        reason: str = "", actor: str = "sdk",
    ) -> dict[str, Any]:
        return self._request(
            "POST", f"/corpora/{corpus_id}/repair/propose",
            json={
                "proposition_id": str(proposition_id),
                "reason": reason,
                "actor": actor,
            },
        )

    def repair_apply(
        self, corpus_id: uuid.UUID, changeset_id: uuid.UUID,
    ) -> dict[str, Any]:
        return self._request(
            "POST", f"/corpora/{corpus_id}/repair/apply/{changeset_id}",
        )

    def repair_approve(
        self, corpus_id: uuid.UUID, changeset_id: uuid.UUID,
    ) -> dict[str, Any]:
        return self._request(
            "POST", f"/corpora/{corpus_id}/repair/approve/{changeset_id}",
        )

    def repair_rollback(
        self, corpus_id: uuid.UUID, changeset_id: uuid.UUID,
    ) -> dict[str, Any]:
        return self._request(
            "POST", f"/corpora/{corpus_id}/repair/rollback/{changeset_id}",
        )

    def contribute_proposition(
        self, corpus_id: uuid.UUID,
        subject_name: str, predicate: str, normalized_text: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "subject_name": subject_name,
            "predicate": predicate,
            "normalized_text": normalized_text,
            **kwargs,
        }
        return self._request("POST", f"/corpora/{corpus_id}/contributions", json=body)

    def review_attestation(
        self,
        corpus_id: uuid.UUID,
        attestation_id: uuid.UUID,
        decision: str,
        actor: str = "sdk",
        reason: str = "",
    ) -> dict[str, Any]:
        return self._request(
            "POST", f"/corpora/{corpus_id}/contributions/review",
            json={
                "attestation_id": str(attestation_id),
                "decision": decision,
                "actor": actor,
                "reason": reason,
            },
        )

    def list_gaps(
        self, corpus_id: uuid.UUID, status: str = "open", **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET", f"/corpora/{corpus_id}/gaps",
            params={"status": status, **kwargs},
        )

    def list_activity(
        self, corpus_id: uuid.UUID, limit: int = 50, **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET", f"/corpora/{corpus_id}/activity",
            params={"limit": limit, **kwargs},
        )

    def resume(
        self,
        corpus_id: uuid.UUID,
        max_gaps: int = 10,
        max_activity: int = 20,
        max_actions: int = 10,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/corpora/{corpus_id}/resume",
            params={
                "max_gaps": max_gaps,
                "max_activity": max_activity,
                "max_actions": max_actions,
            },
        )

    def list_situations(
        self, corpus_id: uuid.UUID, limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET", f"/corpora/{corpus_id}/situations", params={"limit": limit},
        )

    def log_learning_feedback(
        self,
        corpus_id: uuid.UUID,
        question: str,
        step: str,
        outcome: str,
        actor: str = "sdk",
        source_event_type: str = "query",
        source_event_id: uuid.UUID | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "question": question,
            "step": step,
            "outcome": outcome,
            "actor": actor,
            "source_event_type": source_event_type,
            "notes": notes,
        }
        if source_event_id:
            body["source_event_id"] = str(source_event_id)
        return self._request(
            "POST", f"/corpora/{corpus_id}/activity/feedback", json=body,
        )

    def create_situation(
        self,
        corpus_id: uuid.UUID,
        name: str,
        kind: str = "user",
        parent_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        assumptions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "kind": kind}
        if parent_id:
            body["parent_id"] = str(parent_id)
        if document_id:
            body["document_id"] = str(document_id)
        if assumptions:
            body["assumptions"] = assumptions
        return self._request("POST", f"/corpora/{corpus_id}/situations", json=body)

    def get_situation(
        self, corpus_id: uuid.UUID, situation_id: uuid.UUID,
    ) -> dict[str, Any]:
        return self._request(
            "GET", f"/corpora/{corpus_id}/situations/{situation_id}",
        )
