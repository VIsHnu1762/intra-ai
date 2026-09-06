"""Separate Redis namespace for assistant lifecycle and confirmation records."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.voice.models import VoiceSession


class VoiceSessionStore:
    PREFIX = "intra:auxiliary_voice:"

    def __init__(self, redis):
        self.redis = redis

    async def get(self, session_id: str) -> VoiceSession | None:
        raw = await self.redis.get(self.PREFIX + "session:" + session_id)
        return VoiceSession.model_validate_json(raw) if raw else None

    async def put(self, session: VoiceSession) -> None:
        # Keep the safe ended record briefly for idempotent end/result polling.
        await self.redis.set(self.PREFIX + "session:" + session.session_id,
                             session.model_dump_json(), ex=86400)
        if session.status == "DISCONNECTED" or (session.status == "ERROR" and not session.cloud_agent_id):
            await self.redis.srem(self.PREFIX + "active", session.session_id)
        else:
            await self.redis.sadd(self.PREFIX + "active", session.session_id)

    async def active_ids(self) -> list[str]:
        return list(await self.redis.smembers(self.PREFIX + "active"))

    async def begin_execution(self, sid: str, confirmation_id: str, owner: str) -> bool:
        claimed = await self.redis.set(self.PREFIX + "execution:" + confirmation_id, owner, nx=True, ex=90)
        if claimed:
            await self.redis.sadd(self.PREFIX + "executing_sessions", sid)
        return bool(claimed)

    async def execution_owner(self, confirmation_id: str) -> str | None:
        return await self.redis.get(self.PREFIX + "execution:" + confirmation_id)

    async def renew_execution(self, confirmation_id: str, owner: str) -> bool:
        async with self.lock("execution:" + confirmation_id):
            if await self.execution_owner(confirmation_id) != owner:
                return False
            await self.redis.set(self.PREFIX + "execution:" + confirmation_id, owner, ex=90)
            return True

    async def finish_execution(self, sid: str, confirmation_id: str) -> None:
        # Caller holds the execution lock. Keep a tombstone against dispatch
        # replay; the tool's separate durable claim is the mutation boundary.
        await self.redis.set(self.PREFIX + "execution:" + confirmation_id, "finished", ex=86400)
        await self.redis.srem(self.PREFIX + "executing_sessions", sid)

    async def executing_ids(self) -> list[str]:
        return list(await self.redis.smembers(self.PREFIX + "executing_sessions"))

    @asynccontextmanager
    async def lock(self, key: str) -> AsyncIterator[None]:
        # Cross-worker serialization: starts, confirmation, and end cannot race.
        async with self.redis.lock(self.PREFIX + "lock:" + key, timeout=60,
                                   blocking_timeout=8):
            yield


class RedisPendingStore:
    """Durable confirmation payload plus a one-time execution claim."""
    def __init__(self, redis):
        self.redis = redis

    async def get(self, key: str) -> dict | None:
        import json
        raw = await self.redis.get(VoiceSessionStore.PREFIX + "confirmation:" + key)
        return json.loads(raw) if raw else None

    async def put(self, key: str, value: dict, ttl: int) -> None:
        import json
        await self.redis.set(VoiceSessionStore.PREFIX + "confirmation:" + key,
                             json.dumps(value, default=str), ex=max(1, int(ttl)))

    async def claim(self, key: str) -> bool:
        return bool(await self.redis.set(VoiceSessionStore.PREFIX + "claimed:" + key,
                                         "1", nx=True, ex=86400))
