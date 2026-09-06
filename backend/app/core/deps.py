"""FastAPI dependency injection providers."""

from typing import Any

from fastapi import Depends, Request
from redis.asyncio import Redis
from supabase import Client as SupabaseClient

from app.core.security import get_current_user as _get_current_user


async def get_supabase(request: Request) -> SupabaseClient:
    """Return the Supabase client initialised during app lifespan."""
    return request.app.state.supabase


async def get_redis(request: Request) -> Redis:
    """Return the async Redis connection initialised during app lifespan."""
    return request.app.state.redis


async def get_current_user(
    user: dict[str, Any] = Depends(_get_current_user),
) -> dict[str, Any]:
    """Re-export the security dependency so routes import only from deps."""
    return user
