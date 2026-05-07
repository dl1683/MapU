"""Unit tests for the MapU Python SDK client."""

from __future__ import annotations

import uuid

import httpx
import pytest

from mapu.client import AsyncMapUClient, MapUClient


class TestAsyncClientConstruction:
    def test_default_base_url(self) -> None:
        client = AsyncMapUClient()
        assert str(client._client.base_url) == "http://127.0.0.1:8000"

    def test_custom_base_url(self) -> None:
        client = AsyncMapUClient(base_url="http://example.com:9000")
        assert "example.com" in str(client._client.base_url)

    def test_api_key_header(self) -> None:
        client = AsyncMapUClient(api_key="secret-key")
        assert client._client.headers.get("x-api-key") == "secret-key"

    def test_no_api_key_no_header(self) -> None:
        client = AsyncMapUClient()
        assert "x-api-key" not in client._client.headers


class TestAsyncClientMethods:
    @pytest.mark.asyncio
    async def test_health(self, httpx_mock) -> None:
        httpx_mock.add_response(json={"status": "ok", "version": "0.1.0"})
        async with AsyncMapUClient(base_url="http://test") as client:
            result = await client.health()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_create_corpus(self, httpx_mock) -> None:
        cid = str(uuid.uuid4())
        httpx_mock.add_response(json={"id": cid, "name": "test", "description": ""})
        async with AsyncMapUClient(base_url="http://test") as client:
            result = await client.create_corpus("test")
        assert result["id"] == cid

    @pytest.mark.asyncio
    async def test_query(self, httpx_mock) -> None:
        httpx_mock.add_response(json={
            "intent": "identity",
            "tier_used": "DIRECT",
            "epistemic_status": "sufficient",
            "synthesis": "X is Y",
            "hits": [],
            "gaps": [],
            "metadata": {},
        })
        async with AsyncMapUClient(base_url="http://test") as client:
            result = await client.query(uuid.uuid4(), "What is X?")
        assert result["epistemic_status"] == "sufficient"

    @pytest.mark.asyncio
    async def test_investigate(self, httpx_mock) -> None:
        httpx_mock.add_response(json={
            "answer": "result",
            "evidence": [],
            "gaps": [],
            "findings": [],
            "persisted_proposition_ids": [],
            "termination_reason": "coverage_met",
            "metadata": {},
        })
        async with AsyncMapUClient(base_url="http://test") as client:
            result = await client.investigate(uuid.uuid4(), "Why?")
        assert result["answer"] == "result"

    @pytest.mark.asyncio
    async def test_list_gaps(self, httpx_mock) -> None:
        httpx_mock.add_response(json=[])
        async with AsyncMapUClient(base_url="http://test") as client:
            result = await client.list_gaps(uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_list_activity(self, httpx_mock) -> None:
        httpx_mock.add_response(json=[])
        async with AsyncMapUClient(base_url="http://test") as client:
            result = await client.list_activity(uuid.uuid4())
        assert result == []


class TestSyncClient:
    def test_sync_wrapper_has_all_methods(self) -> None:
        async_methods = {
            m for m in dir(AsyncMapUClient)
            if not m.startswith("_") and callable(getattr(AsyncMapUClient, m))
            and m not in ("close",)
        }
        sync_methods = {
            m for m in dir(MapUClient)
            if not m.startswith("_") and callable(getattr(MapUClient, m))
            and m not in ("close",)
        }
        missing = async_methods - sync_methods
        assert not missing, f"Sync client missing methods: {missing}"

    def test_sync_client_uses_httpx_client(self) -> None:
        client = MapUClient()
        assert isinstance(client._client, httpx.Client)
        client.close()

    def test_sync_client_context_manager(self) -> None:
        with MapUClient() as client:
            assert isinstance(client._client, httpx.Client)


@pytest.fixture
def httpx_mock(monkeypatch):
    """Simple httpx mock that records and replays responses."""
    responses: list[httpx.Response] = []

    class _Mock:
        def add_response(self, **kwargs):
            responses.append(httpx.Response(200, **kwargs))

    mock = _Mock()

    original_send = httpx.AsyncClient.send

    async def mock_send(self, request, **kwargs):
        if responses:
            resp = responses.pop(0)
            resp.request = request
            return resp
        return await original_send(self, request, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)
    return mock
