"""HTTP pool ownership, request isolation, and safe Groq latency evidence."""

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest

from app.integrations import groq_client


def response_payload():
    return {
        "id": "chatcmpl-provider-1", "model": "openai/gpt-oss-20b",
        "choices": [{"message": {"content": '{"answer": "ok"}'}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60,
                  "queue_time": 0.01, "completion_time": 0.1, "private_field": "never-log"},
    }


@pytest.fixture
def transport(monkeypatch):
    original = httpx.AsyncClient
    clients, requests = [], []

    async def handler(request):
        requests.append(request)
        await asyncio.sleep(0)
        return httpx.Response(200, json=response_payload())

    def factory(**kwargs):
        client = original(transport=httpx.MockTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", factory)
    return clients, requests


@pytest.mark.asyncio
async def test_managed_loop_reuses_one_client_and_keeps_request_credentials_local(transport):
    clients, requests = transport
    client = await groq_client.initialize_groq_client()
    try:
        assert await groq_client.initialize_groq_client() is client
        results = await asyncio.gather(
            groq_client.call_groq("openai/gpt-oss-20b", [{"role": "user", "content": "private-a"}], api_key="key-a", timeout_seconds=7),
            groq_client.call_groq("openai/gpt-oss-20b", [{"role": "user", "content": "private-b"}], api_key="key-b", timeout_seconds=11),
        )
        assert len(clients) == 1
        assert not client.is_closed
        assert {request.headers["authorization"] for request in requests} == {"Bearer key-a", "Bearer key-b"}
        assert {request.extensions["timeout"]["read"] for request in requests} == {7, 11}
        assert all(result["content"] == '{"answer": "ok"}' for result in results)
    finally:
        await groq_client.close_groq_client()
    assert client.is_closed
    assert asyncio.get_running_loop() not in groq_client._clients


def test_standalone_asyncio_run_closes_each_client_and_does_not_cache_loop(transport):
    clients, _ = transport
    for _ in range(2):
        asyncio.run(groq_client.call_groq("model", [], api_key="test-key"))
    assert len(clients) == 2
    assert all(client.is_closed for client in clients)
    assert not groq_client._clients


def test_two_application_loops_never_share_a_client(transport):
    clients, _ = transport

    async def lifecycle():
        await groq_client.initialize_groq_client()
        try:
            await groq_client.call_groq("model", [], api_key="test-key")
        finally:
            await groq_client.close_groq_client()

    asyncio.run(lifecycle())
    asyncio.run(lifecycle())
    assert len(clients) == 2
    assert clients[0] is not clients[1]
    assert all(client.is_closed for client in clients)
    assert not groq_client._clients


@pytest.mark.asyncio
async def test_http_success_log_is_correlated_numeric_and_contains_no_content(transport, monkeypatch):
    logs = MagicMock()
    monkeypatch.setattr(groq_client, "logger", logs)
    await groq_client.call_groq(
        "openai/gpt-oss-20b", [{"role": "user", "content": "PRIVATE_CANDIDATE_ANSWER"}],
        api_key="SECRET_API_KEY", context_id="interview-turn-3", response_format={"type": "json_object"},
    )
    event = logs.info.call_args
    assert event.args == ("[GROQ_HTTP_COMPLETE]",)
    assert event.kwargs["context_id"] == "interview-turn-3"
    assert event.kwargs["provider_response_id"] == "chatcmpl-provider-1"
    assert event.kwargs["total_tokens"] == 60
    assert event.kwargs["duration_ms"] >= 0
    assert event.kwargs["status_code"] == 200
    assert "SECRET_API_KEY" not in str(event)
    assert "PRIVATE_CANDIDATE_ANSWER" not in str(event)
    assert "never-log" not in str(event)


@pytest.mark.asyncio
async def test_http_error_does_not_produce_success_evidence(monkeypatch):
    logs = MagicMock()
    monkeypatch.setattr(groq_client, "logger", logs)
    original = httpx.AsyncClient
    monkeypatch.setattr(groq_client.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(429, json={"error": "quota"})), **kwargs,
    ))
    with pytest.raises(groq_client.GroqAPIError, match="RESOURCE_EXHAUSTED"):
        await groq_client.call_groq("model", [], api_key="test-key")
    logs.info.assert_not_called()


@pytest.mark.asyncio
async def test_close_is_idempotent_and_next_lifespan_gets_new_pool(transport):
    first = await groq_client.initialize_groq_client()
    await groq_client.close_groq_client()
    await groq_client.close_groq_client()
    second = await groq_client.initialize_groq_client()
    try:
        assert first is not second
        assert first.is_closed and not second.is_closed
    finally:
        await groq_client.close_groq_client()


@pytest.mark.asyncio
async def test_application_shutdown_drains_work_before_pool_close_even_on_error(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.main import lifespan
    from app.custom_llm.adapter import custom_llm_adapter

    order = []
    monkeypatch.setattr("app.main._configure_logging", lambda: None)
    monkeypatch.setattr("supabase.create_client", MagicMock())
    monkeypatch.setattr("app.main.Redis.from_url", MagicMock(return_value=SimpleNamespace(
        ping=AsyncMock(), aclose=AsyncMock(),
    )))
    monkeypatch.setattr(groq_client, "initialize_groq_client", AsyncMock(side_effect=lambda: order.append("initialize")))
    monkeypatch.setattr(groq_client, "close_groq_client", AsyncMock(side_effect=lambda: order.append("close")))
    monkeypatch.setattr(custom_llm_adapter, "drain_background_tasks", AsyncMock(side_effect=lambda: order.append("drain")))
    with pytest.raises(RuntimeError, match="application failed"):
        async with lifespan(SimpleNamespace(state=SimpleNamespace())):
            order.append("running")
            raise RuntimeError("application failed")
    assert order == ["initialize", "running", "drain", "close"]
