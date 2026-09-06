"""Repository for candidate table operations."""

from __future__ import annotations

from typing import Any

import structlog
from supabase import Client

logger = structlog.stdlib.get_logger("intra_ai.repo.candidate")


class CandidateRepo:
    """Encapsulates all Supabase queries against the ``candidates`` table."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert a new candidate record."""
        result = self._sb.table("candidates").insert(data).execute()
        return result.data[0]

    async def get_by_email(self, email: str) -> dict[str, Any] | None:
        """Look up a candidate by email."""
        result = (
            self._sb.table("candidates")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_by_id(self, candidate_id: str) -> dict[str, Any] | None:
        """Fetch a single candidate with parsed resume."""
        result = (
            self._sb.table("candidates")
            .select("*, parsed_resumes(*)")
            .eq("id", candidate_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List candidates with pagination."""
        query = self._sb.table("candidates").select("*", count="exact")

        if filters:
            if "candidate_ids" in filters:
                if not filters["candidate_ids"]:
                    return [], 0
                query = query.in_("id", filters["candidate_ids"])
            if search := filters.get("search"):
                query = query.or_(f"name.ilike.%{search}%,email.ilike.%{search}%")

        offset = (page - 1) * per_page
        if filters is not None and "tenant_id" in filters:
            # Tenant is optional on legacy hosted candidate rows. Read only
            # already-authorized candidate IDs, then filter tags before user
            # pagination/counts; never request a possibly absent SQL column.
            allowed = []
            scan = 0
            query = query.order("created_at", desc=True).order("id")
            while True:
                rows = query.range(scan, scan + 99).execute().data or []
                allowed.extend(row for row in rows if row.get("tenant_id") is None or (
                    filters["tenant_id"] is not None and str(row["tenant_id"]) == str(filters["tenant_id"])
                ))
                if len(rows) < 100:
                    return allowed[offset:offset + per_page], len(allowed)
                scan += 100
        query = query.order("created_at", desc=True).range(offset, offset + per_page - 1)

        result = query.execute()
        total = result.count if result.count is not None else len(result.data)
        return result.data, total

    async def list_applications(self, candidate_id: str) -> list[dict[str, Any]]:
        """Get all applications for a candidate."""
        result = (
            self._sb.table("applications")
            .select("*, jobs(*), scheduled_interviews(*)")
            .eq("candidate_id", candidate_id)
            .order("created_at", desc=True)
            .execute()
        )
        rows = result.data
        # Keep the candidate-facing contract flat while exposing the scheduled
        # interview identifiers needed by the portal after recruiter booking.
        for row in rows:
            interviews = row.pop("scheduled_interviews", None) or []
            if interviews:
                interview = sorted(
                    interviews,
                    key=lambda item: item.get("created_at", ""),
                    reverse=True,
                )[0]
                row["interview_id"] = interview.get("id")
                row["scheduled_at"] = interview.get("scheduled_at")
                row["meeting_mode"] = (
                    "instant" if interview.get("status", "").startswith("instant_") else "scheduled"
                )
                row["instant_status"] = interview.get("status")
                row["room_token"] = interview.get("room_token")
                if interview.get("status") == "instant_pending":
                    # Instant invitations use scheduled_at as their ten-minute
                    # response deadline until the candidate accepts them.
                    row["instant_deadline"] = interview.get("scheduled_at")
        return rows
