"""Interview lifecycle service — start, end, get."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from app.core.exceptions import NotFoundError, ValidationError
from app.repositories.interview_repo import InterviewRepo
from app.schemas.candidates import CandidateResponse
from app.schemas.interviews import ScheduledInterviewResponse
from app.schemas.jobs import InterviewRoundConfigSchema, JobResponse
from app.services.round_agents import decode_round_agents

logger = structlog.stdlib.get_logger("intra_ai.service.interview")


class InterviewService:
    """Manages interview session lifecycle."""

    def __init__(self, interview_repo: InterviewRepo) -> None:
        self._repo = interview_repo

    async def start_interview(self, interview_id: str) -> dict[str, Any]:
        """Mark interview as in-progress and record start time."""
        interview = await self._repo.get_by_id(interview_id)
        if not interview:
            raise NotFoundError(f"Interview {interview_id} not found")

        if interview["status"] not in {"scheduled", "instant_active"}:
            raise ValidationError(f"Cannot start interview in '{interview['status']}' state")

        now = datetime.now(timezone.utc).isoformat()
        updated = await self._repo.update(
            interview_id,
            {"status": "in_progress", "started_at": now},
        )

        logger.info("interview_started", interview_id=interview_id)
        return {"interview_id": interview_id, "status": "in_progress", "started_at": now}

    async def end_interview(self, interview_id: str) -> dict[str, Any]:
        """Mark interview as completed and record end time."""
        interview = await self._repo.get_by_id(interview_id)
        if not interview:
            raise NotFoundError(f"Interview {interview_id} not found")

        if interview["status"] != "in_progress":
            raise ValidationError(f"Cannot end interview in '{interview['status']}' state")

        now = datetime.now(timezone.utc).isoformat()
        updated = await self._repo.update(
            interview_id,
            {"status": "completed", "ended_at": now},
        )

        logger.info("interview_ended", interview_id=interview_id)
        from app.sessions.completion import persist_completed_interview
        completion = await persist_completed_interview(interview_id, self._repo._sb)
        return {"interview_id": interview_id, "status": "completed", "ended_at": now, **completion}

    async def get_interview(self, interview_id: str) -> ScheduledInterviewResponse:
        """Get interview details."""
        interview = await self._repo.get_by_id(interview_id)
        if not interview:
            raise NotFoundError(f"Interview {interview_id} not found")

        return self._to_response(interview)

    async def list_interviews(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[ScheduledInterviewResponse], int]:
        """List all interviews with filters."""
        rows, total = await self._repo.list(filters=filters, page=page, per_page=per_page)
        interviews = [self._to_response(r) for r in rows]
        return interviews, total

    @staticmethod
    def _to_response(interview: dict[str, Any]) -> ScheduledInterviewResponse:
        """Map the nested durable records into the UI's typed interview contract."""
        status = str(interview.get("status") or "scheduled")
        candidate_row = interview.get("candidates") or interview.get("candidate")
        job_row = interview.get("jobs") or interview.get("job")
        candidate = None
        if candidate_row and candidate_row.get("id") and candidate_row.get("name") and candidate_row.get("email"):
            candidate = CandidateResponse(
                id=candidate_row["id"],
                name=candidate_row["name"],
                email=candidate_row["email"],
                phone=candidate_row.get("phone"),
                # A shared candidate profile may hold another job's last CV.
                # Application-specific resume links are fetched in its dossier.
                resume_url=None,
                parsed_resume=None,
                created_at=candidate_row.get("created_at") or interview.get("created_at"),
            )

        job = None
        if job_row and job_row.get("id") and job_row.get("title"):
            rounds = [
                InterviewRoundConfigSchema(
                    type=round_row["type"],
                    duration_minutes=round_row.get("duration_minutes", 15),
                    focus_areas=decode_round_agents(round_row)[1],
                    enabled=round_row.get("enabled", True),
                    agent_ids=decode_round_agents(round_row)[0],
                )
                for round_row in (job_row.get("job_rounds") or [])
                if round_row.get("type")
            ]
            job = JobResponse(
                id=job_row["id"],
                title=job_row["title"],
                department=job_row.get("department") or "General",
                location=job_row.get("location") or "Remote",
                job_type=job_row.get("job_type") or "remote",
                description=job_row.get("description") or "",
                required_skills=job_row.get("required_skills") or [],
                experience_min=job_row.get("experience_min") or 0,
                experience_max=job_row.get("experience_max") or 0,
                salary_min=job_row.get("salary_min"),
                salary_max=job_row.get("salary_max"),
                status=job_row.get("status") or "published",
                applications_count=job_row.get("applications_count") or 0,
                interview_rounds=rounds,
                created_at=job_row.get("created_at") or interview.get("created_at"),
                updated_at=job_row.get("updated_at") or job_row.get("created_at") or interview.get("created_at"),
            )

        return ScheduledInterviewResponse(
            id=interview["id"],
            application_id=interview["application_id"],
            scheduled_at=interview["scheduled_at"],
            duration_minutes=interview.get("duration_minutes") or 60,
            room_token=interview.get("room_token"),
            status=status,
            meeting_mode="instant" if status.startswith("instant_") else "scheduled",
            response_deadline=interview.get("scheduled_at") if status == "instant_pending" else None,
            candidate=candidate,
            job=job,
        )
