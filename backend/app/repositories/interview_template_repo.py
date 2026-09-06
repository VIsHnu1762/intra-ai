"""Supabase-only template persistence, scoped in every read and update."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import AppError
from app.voice.authorization import Actor


class InterviewTemplatesUnavailable(AppError):
    status_code = 503
    code = "INTERVIEW_TEMPLATES_UNAVAILABLE"
    message = "Interview templates are temporarily unavailable"


class InterviewTemplateRepo:
    def __init__(self, supabase: Any):
        self._sb = supabase

    @staticmethod
    def _scope(query: Any, actor: Actor) -> Any:
        if actor.tenant_id is not None:
            return query.eq("tenant_id", str(actor.tenant_id))
        return query.is_("tenant_id", "null").eq("created_by", actor.user_id)

    @staticmethod
    def _execute(query: Any) -> list[dict[str, Any]]:
        try:
            return query.execute().data or []
        except Exception as exc:
            # PostgREST error bodies can contain database internals. Never
            # return them, and never silently replace persistence with memory.
            raise InterviewTemplatesUnavailable() from exc

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        rows = self._execute(self._sb.table("interview_templates").insert(data))
        if not rows:
            raise InterviewTemplatesUnavailable()
        return rows[0]

    async def list(self, actor: Actor, *, include_archived: bool = False) -> list[dict[str, Any]]:
        query = self._scope(self._sb.table("interview_templates").select("*"), actor)
        if not include_archived:
            query = query.is_("archived_at", "null")
        # Fetch successive pages so a workspace is not silently truncated by
        # Supabase's default maximum rows.
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._execute(query.order("created_at", desc=True).order("id").range(offset, offset + 99))
            rows.extend(page)
            if len(page) < 100:
                return rows
            offset += 100

    async def get(self, actor: Actor, template_id: str) -> dict[str, Any] | None:
        query = self._scope(self._sb.table("interview_templates").select("*").eq("id", template_id), actor)
        rows = self._execute(query.limit(1))
        return rows[0] if rows else None

    async def update(self, actor: Actor, template_id: str, version: int, data: dict[str, Any]) -> dict[str, Any] | None:
        query = self._scope(
            self._sb.table("interview_templates").update(data).eq("id", template_id)
            .eq("version", version).is_("archived_at", "null"), actor,
        )
        rows = self._execute(query)
        return rows[0] if rows else None
