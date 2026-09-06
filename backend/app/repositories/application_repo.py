"""Repository for application table operations."""

from __future__ import annotations

from typing import Any

import structlog
from supabase import Client

logger = structlog.stdlib.get_logger("intra_ai.repo.application")


class ApplicationRepo:
    """Encapsulates all Supabase queries against the ``applications`` table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new application."""
        result = self._sb.table("applications").insert(data).execute()
        return result.data[0]

    async def get_by_id(self, app_id: str) -> dict[str, Any] | None:
        """Fetch a single application with candidate and job data."""
        result = (
            self._sb.table("applications")
            .select("*, candidates(*, parsed_resumes(*)), jobs(*, job_rounds(*))")
            .eq("id", app_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_by_job_and_candidate(
        self, job_id: str, candidate_id: str
    ) -> dict[str, Any] | None:
        """Return the existing application for a candidate/job pair, if any."""
        result = (
            self._sb.table("applications")
            .select("*, candidates(*, parsed_resumes(*)), jobs(*, job_rounds(*))")
            .eq("job_id", job_id)
            .eq("candidate_id", candidate_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def list_by_job(
        self,
        job_id: str,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List applications for a job with pagination."""
        query = (
            self._sb.table("applications")
            .select("*, candidates(*)", count="exact")
            .eq("job_id", job_id)
        )

        if filters:
            if status := filters.get("status"):
                query = query.eq("status", status)

        offset = (page - 1) * per_page
        query = query.order("created_at", desc=True).range(offset, offset + per_page - 1)

        result = query.execute()
        total = result.count if result.count is not None else len(result.data)
        return result.data, total

    async def update_status(
        self,
        app_id: str,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update application status and optional extra fields."""
        data: dict[str, Any] = {"status": status}
        if extra:
            data.update(extra)
        result = (
            self._sb.table("applications")
            .update(data)
            .eq("id", app_id)
            .execute()
        )
        return result.data[0]

    async def get_parsed_resume(self, app_id: str) -> dict[str, Any] | None:
        """Get the parsed resume for an application."""
        result = (
            self._sb.table("parsed_resumes")
            .select("*")
            .eq("application_id", app_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
