"""Repository for user table operations."""

from __future__ import annotations

from typing import Any

import structlog
from supabase import Client

logger = structlog.stdlib.get_logger("intra_ai.repo.user")


class UserRepo:
    """Encapsulates all Supabase queries against the ``users`` table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    async def create_user(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new user row and return it."""
        result = self._sb.table("users").insert(data).execute()
        return result.data[0]

    async def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Look up a user by email address."""
        result = (
            self._sb.table("users")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_user_by_id(self, user_id: str) -> dict[str, Any] | None:
        """Look up a user by primary key."""
        result = (
            self._sb.table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
