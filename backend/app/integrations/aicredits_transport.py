"""Loop-owned HTTP reuse for live intelligence; temporary workers own their sockets."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}


async def initialize_aicredits_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(follow_redirects=False, limits=httpx.Limits(keepalive_expiry=60))
        _clients[loop] = client
    return client


async def close_aicredits_client() -> None:
    client = _clients.pop(asyncio.get_running_loop(), None)
    if client is not None:
        await client.aclose()


@asynccontextmanager
async def aicredits_http_client(
    *, timeout: float, transport: httpx.AsyncBaseTransport | None = None, use_pool: bool = True,
) -> AsyncIterator[httpx.AsyncClient]:
    # Only the explicitly initialized application loop may retain sockets.
    # Report workers and synchronous asyncio.run callers close their own clients.
    client = _clients.get(asyncio.get_running_loop()) if use_pool and transport is None else None
    if client is not None and not client.is_closed:
        yield client
    else:
        async with httpx.AsyncClient(transport=transport, timeout=timeout, follow_redirects=False) as owned:
            yield owned
