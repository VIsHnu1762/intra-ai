"""Live transport reuse does not leak clients across workers or event loops."""

import asyncio

import httpx
import pytest

from app.integrations import aicredits_transport as transport


@pytest.mark.asyncio
async def test_lifespan_pool_is_reused_and_explicitly_closed():
    first = await transport.initialize_aicredits_client()
    try:
        assert await transport.initialize_aicredits_client() is first
        async with transport.aicredits_http_client(timeout=5) as client:
            assert client is first
        assert not first.is_closed
    finally:
        await transport.close_aicredits_client()
    assert first.is_closed
    assert asyncio.get_running_loop() not in transport._clients
    await transport.close_aicredits_client()


@pytest.mark.asyncio
async def test_report_worker_and_explicit_test_transport_bypass_live_pool():
    pooled = await transport.initialize_aicredits_client()
    try:
        async with transport.aicredits_http_client(timeout=5, use_pool=False) as owned:
            assert owned is not pooled
        assert owned.is_closed and not pooled.is_closed
        mock = httpx.MockTransport(lambda request: httpx.Response(200))
        async with transport.aicredits_http_client(timeout=5, transport=mock) as isolated:
            assert isolated is not pooled
            assert (await isolated.get("https://test.invalid")).status_code == 200
        assert isolated.is_closed
    finally:
        await transport.close_aicredits_client()


def test_temporary_event_loops_never_cache_or_share_clients():
    async def run():
        async with transport.aicredits_http_client(timeout=5) as client:
            assert asyncio.get_running_loop() not in transport._clients
        assert client.is_closed
        return client
    assert asyncio.run(run()) is not asyncio.run(run())
