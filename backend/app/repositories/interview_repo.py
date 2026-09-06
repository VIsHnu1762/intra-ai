"""Repository for interview, slot, question, answer, evaluation, and proctoring operations."""

from __future__ import annotations

from typing import Any

import structlog
from supabase import Client

from app.core.exceptions import ConflictError

logger = structlog.stdlib.get_logger("intra_ai.repo.interview")


class InterviewRepo:
    """Encapsulates all Supabase queries for interviews and related tables."""

    def __init__(self, supabase: Client) -> None:
        self._sb = supabase

    # ── Slots ────────────────────────────────────────────────

    async def create_slot(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._sb.table("interview_slots").insert(data).execute()
        return result.data[0]

    async def create_slots_batch(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = self._sb.table("interview_slots").insert(rows).execute()
        return result.data

    async def get_available_slots(self, job_id: str) -> list[dict[str, Any]]:
        result = (
            self._sb.table("interview_slots")
            .select("*")
            .eq("job_id", job_id)
            .eq("is_booked", False)
            .order("date")
            .order("start_time")
            .execute()
        )
        return result.data

    async def get_slot_by_id(self, slot_id: str) -> dict[str, Any] | None:
        result = (
            self._sb.table("interview_slots")
            .select("*")
            .eq("id", slot_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def book_slot(self, slot_id: str) -> dict[str, Any]:
        result = (
            self._sb.table("interview_slots")
            .update({"is_booked": True})
            .eq("id", slot_id)
            .eq("is_booked", False)
            .execute()
        )
        if not result.data:
            raise ConflictError("This slot is already booked or no longer available")
        return result.data[0]

    async def release_slot(self, slot_id: str) -> dict[str, Any] | None:
        """Release a slot when an interview is moved to another time."""
        result = (
            self._sb.table("interview_slots")
            .update({"is_booked": False})
            .eq("id", slot_id)
            .execute()
        )
        return result.data[0] if result.data else None

    # ── Scheduled Interviews ─────────────────────────────────

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._sb.table("scheduled_interviews").insert(data).execute()
        return result.data[0]

    async def get_by_id(self, interview_id: str) -> dict[str, Any] | None:
        result = (
            self._sb.table("scheduled_interviews")
            .select("*, candidates(*, parsed_resumes(*)), jobs(*, job_rounds(*)), applications(*)")
            .eq("id", interview_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_latest_by_application_id(
        self, application_id: str
    ) -> dict[str, Any] | None:
        """Return the most recently created interview for an application."""
        result = (
            self._sb.table("scheduled_interviews")
            .select("*")
            .eq("application_id", application_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def update(self, interview_id: str, data: dict[str, Any]) -> dict[str, Any]:
        result = (
            self._sb.table("scheduled_interviews")
            .update(data)
            .eq("id", interview_id)
            .execute()
        )
        return result.data[0]

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        query = (
            self._sb.table("scheduled_interviews")
            .select("*, candidates(*, parsed_resumes(*)), jobs(*, job_rounds(*))", count="exact")
        )

        if filters:
            if "job_ids" in filters:
                if not filters["job_ids"]:
                    return [], 0
                query = query.in_("job_id", filters["job_ids"])
            if status := filters.get("status"):
                query = query.eq("status", status)
            if job_id := filters.get("job_id"):
                query = query.eq("job_id", job_id)

        offset = (page - 1) * per_page
        query = query.order("scheduled_at", desc=True).range(offset, offset + per_page - 1)

        result = query.execute()
        total = result.count if result.count is not None else len(result.data)
        return result.data, total

    # ── Questions ────────────────────────────────────────────

    async def create_questions(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = self._sb.table("interview_questions").insert(rows).execute()
        return result.data

    async def get_questions(
        self,
        interview_id: str,
        round_type: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self._sb.table("interview_questions")
            .select("*")
            .eq("interview_id", interview_id)
        )
        if round_type:
            query = query.eq("round_type", round_type)
        query = query.order("order")
        result = query.execute()
        return result.data

    async def get_question_by_id(self, question_id: str) -> dict[str, Any] | None:
        result = (
            self._sb.table("interview_questions")
            .select("*")
            .eq("id", question_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    # ── Answers ──────────────────────────────────────────────

    async def create_answer(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._sb.table("candidate_answers").insert(data).execute()
        return result.data[0]

    async def get_answers(self, interview_id: str) -> list[dict[str, Any]]:
        result = (
            self._sb.table("candidate_answers")
            .select("*, interview_questions(*)")
            .eq("interview_id", interview_id)
            .order("created_at")
            .execute()
        )
        return result.data

    async def get_answer_by_id(self, answer_id: str) -> dict[str, Any] | None:
        result = (
            self._sb.table("candidate_answers")
            .select("*, interview_questions(*)")
            .eq("id", answer_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    # ── Evaluations ──────────────────────────────────────────

    async def create_evaluation(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._sb.table("evaluations").insert(data).execute()
        return result.data[0]

    async def get_evaluations(self, interview_id: str) -> list[dict[str, Any]]:
        result = (
            self._sb.table("evaluations")
            .select("*, candidate_answers(*, interview_questions(*))")
            .eq("interview_id", interview_id)
            .order("created_at")
            .execute()
        )
        return result.data

    # ── Proctoring ───────────────────────────────────────────

    async def create_proctoring_event(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._sb.table("proctoring_events").insert(data).execute()
        return result.data[0]

    async def get_proctoring_events(self, interview_id: str) -> list[dict[str, Any]]:
        result = (
            self._sb.table("proctoring_events")
            .select("*")
            .eq("interview_id", interview_id)
            .order("timestamp")
            .execute()
        )
        return result.data

    # ── Reports ──────────────────────────────────────────────

    async def create_report(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._sb.table("reports").insert(data).execute()
        return result.data[0]

    async def claim_report(self, interview_id: str, attempt_id: str, source: dict[str, Any] | None) -> dict[str, Any]:
        result = self._sb.rpc("claim_interview_report", {
            "p_interview_id": interview_id, "p_attempt_id": attempt_id, "p_source": source,
        }).execute()
        return result.data

    async def save_report_progress(self, interview_id: str, attempt_id: str, data: dict[str, Any]) -> None:
        result = (self._sb.table("scheduled_interviews").update(data).eq("id", interview_id)
                  .eq("report_generation->>attempt_id", attempt_id)
                  .eq("report_generation->>status", "generating").execute())
        if not result.data:
            raise ConflictError("Report generation attempt was superseded")

    async def finish_report(self, interview_id: str, attempt_id: str, report: dict[str, Any]) -> dict[str, Any]:
        return self._sb.rpc("finish_interview_report", {
            "p_interview_id": interview_id, "p_attempt_id": attempt_id, "p_report": report,
        }).execute().data

    async def get_report(self, interview_id: str) -> dict[str, Any] | None:
        result = (
            self._sb.table("reports")
            .select("*")
            .eq("interview_id", interview_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_report_by_id(self, report_id: str) -> dict[str, Any] | None:
        result = (
            self._sb.table("reports")
            .select("*")
            .eq("id", report_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def list_reports(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        query = self._sb.table("reports").select("*", count="exact")
        if filters:
            if "interview_ids" in filters:
                if not filters["interview_ids"]:
                    return [], 0
                query = query.in_("interview_id", filters["interview_ids"])
            if recommendation := filters.get("recommendation"):
                query = query.eq("recommendation", recommendation)
            if interview_id := filters.get("interview_id"):
                query = query.eq("interview_id", interview_id)
        offset = (page - 1) * per_page
        result = query.order("created_at", desc=True).range(offset, offset + per_page - 1).execute()
        return result.data, result.count if result.count is not None else len(result.data)

    async def update_report(self, report_id: str, data: dict[str, Any]) -> dict[str, Any]:
        result = (
            self._sb.table("reports")
            .update(data)
            .eq("id", report_id)
            .execute()
        )
        return result.data[0]
