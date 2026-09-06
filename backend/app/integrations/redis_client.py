"""Async Redis wrapper with cache-aside pattern."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

import structlog
from redis.asyncio import Redis

logger = structlog.stdlib.get_logger("intra_ai.redis")


class RedisClient:
    """Thin wrapper around an async Redis connection."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        """Get a value by key."""
        value = await self._redis.get(key)
        if value is not None:
            return value.decode() if isinstance(value, bytes) else value
        return None

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        """Set a value with TTL in seconds."""
        await self._redis.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        await self._redis.delete(key)

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: int = 3600,
    ) -> Any:
        """Cache-aside: return cached value or call *factory*, cache, and return."""
        cached = await self.get(key)
        if cached is not None:
            return json.loads(cached)

        value = await factory()
        await self.set(key, json.dumps(value, default=str), ttl=ttl)
        return value
