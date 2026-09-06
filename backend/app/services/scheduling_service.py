"""Scheduling service — slot management and interview booking."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from pydantic import ValidationError as SchemaValidationError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.enums import ApplicationStatus
from app.repositories.application_repo import ApplicationRepo
from app.repositories.interview_repo import InterviewRepo
from app.schemas.interviews import InterviewSlotResponse, ScheduledInterviewResponse
from app.schemas.interview_templates import TemplateSnapshot
from app.services.round_agents import decode_round_agents

logger = structlog.stdlib.get_logger("intra_ai.service.scheduling")


class SchedulingService:
    """Manages interview slots and candidate booking."""

    def __init__(
        self,
        interview_repo: InterviewRepo,
        app_repo: ApplicationRepo,
    ) -> None:
        self._repo = interview_repo
        self._app_repo = app_repo

    async def create_slots(
        self,
        job_id: str,
        slots: list[dict[str, Any]],
    ) -> list[InterviewSlotResponse]:
        """Create available interview slots for a job."""
        rows_to_insert = [
            {
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "date": slot["date"],
                "start_time": slot["start_time"],
                "end_time": slot["end_time"],
                "is_booked": False,
            }
            for slot in slots
        ]

        created = await self._repo.create_slots_batch(rows_to_insert)

        logger.info("slots_created", job_id=job_id, count=len(created))
        return [
            InterviewSlotResponse(
                id=s["id"],
                job_id=s["job_id"],
                date=s["date"],
                start_time=s["start_time"],
                end_time=s["end_time"],
                is_booked=s["is_booked"],
            )
            for s in created
        ]

    async def get_available_slots(self, job_id: str) -> list[InterviewSlotResponse]:
        """Get all unbooked slots for a job."""
        rows = await self._repo.get_available_slots(job_id)
        return [
            InterviewSlotResponse(
                id=s["id"],
                job_id=s["job_id"],
                date=s["date"],
                start_time=s["start_time"],
                end_time=s["end_time"],
                is_booked=s["is_booked"],
            )
            for s in rows
        ]

    async def book_slot(
        self,
        application_id: str,
        slot_id: str,
        *,
        template_snapshot: dict[str, Any] | None = None,
    ) -> ScheduledInterviewResponse:
        """Book an interview slot for an application."""
        # Validate application
        app = await self._app_repo.get_by_id(application_id)
        if not app:
            raise NotFoundError(f"Application {application_id} not found")
        if app["status"] not in (
            ApplicationStatus.SHORTLISTED.value,
            ApplicationStatus.INVITED.value,
            ApplicationStatus.COMPLETED.value,
        ):
            raise ValidationError("The application must be shortlisted, invited, or completed to schedule an interview")

        # Validate slot
        slot = await self._repo.get_slot_by_id(slot_id)
        if not slot:
            raise NotFoundError(f"Slot {slot_id} not found")
        if slot["is_booked"]:
            raise ConflictError("This slot is already booked")
        if slot.get("job_id") != app.get("job_id"):
            raise ValidationError("The selected slot belongs to a different job")
        snapshot = _copy_template_snapshot(template_snapshot)
        scheduled_at = _slot_start(slot)
        if snapshot:
            _require_slot_duration(slot, snapshot["duration_minutes"])

        # Book the slot
        await self._repo.book_slot(slot_id)

        # Create scheduled interview
        interview_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        room_token = str(uuid.uuid4())  # placeholder; real token from video provider

        try:
            interview = await self._repo.create({
                "id": interview_id,
                "application_id": application_id,
                "job_id": app["job_id"],
                "candidate_id": app["candidate_id"],
                "slot_id": slot_id,
                "status": "scheduled",
                "room_token": room_token,
                "scheduled_at": scheduled_at,
                **({"template_snapshot": snapshot, "duration_minutes": snapshot["duration_minutes"]} if snapshot else {}),
                "created_at": now,
            })
        except Exception:
            await self._repo.release_slot(slot_id)
            raise

        # Update application status
        await self._app_repo.update_status(application_id, ApplicationStatus.SCHEDULED.value)

        # Materialize the live-session boundary at booking time.  The session
        # remains in memory until the candidate enters, while the scheduled
        # interview row remains the durable source of truth for ATS reporting.
        self._ensure_live_session(app, interview)

        logger.info(
            "interview_booked",
            interview_id=interview_id,
            application_id=application_id,
            slot_id=slot_id,
        )

        return ScheduledInterviewResponse(
            id=interview["id"],
            application_id=interview["application_id"],
            scheduled_at=interview["scheduled_at"],
            duration_minutes=interview.get("duration_minutes") or 60,
            room_token=interview.get("room_token"),
            status=interview["status"],
            meeting_mode="scheduled",
        )

    async def reschedule(
        self,
        application_id: str,
        slot_id: str,
    ) -> ScheduledInterviewResponse:
        """Move an existing recruiter-scheduled interview to another slot."""
        app = await self._app_repo.get_by_id(application_id)
        if not app:
            raise NotFoundError(f"Application {application_id} not found")
        if app["status"] != ApplicationStatus.SCHEDULED.value:
            raise ValidationError("Only a scheduled interview can be rescheduled")

        interview = await self._repo.get_latest_by_application_id(application_id)
        if not interview or interview.get("status") not in {"scheduled", "instant_active"}:
            raise NotFoundError("No active interview found for this application")

        slot = await self._repo.get_slot_by_id(slot_id)
        if not slot:
            raise NotFoundError(f"Slot {slot_id} not found")
        if slot.get("job_id") != app.get("job_id"):
            raise ValidationError("The selected slot belongs to a different job")
        if slot.get("is_booked") and slot.get("id") != interview.get("slot_id"):
            raise ConflictError("This slot is already booked")
        scheduled_at = _slot_start(slot)
        if interview.get("template_snapshot"):
            _require_slot_duration(slot, interview["duration_minutes"])

        old_slot_id = interview.get("slot_id")
        if old_slot_id != slot_id:
            await self._repo.book_slot(slot_id)
            if old_slot_id:
                await self._repo.release_slot(old_slot_id)

        updated = await self._repo.update(
            interview["id"],
            {
                "slot_id": slot_id,
                "scheduled_at": scheduled_at,
                "status": "scheduled",
            },
        )
        self._ensure_live_session(app, updated, scheduled_start=scheduled_at)
        self._update_live_session_start(interview["id"], scheduled_at)

        logger.info(
            "interview_rescheduled",
            interview_id=interview["id"],
            application_id=application_id,
            old_slot_id=old_slot_id,
            slot_id=slot_id,
        )
        return ScheduledInterviewResponse(
            id=updated["id"],
            application_id=updated["application_id"],
            scheduled_at=updated["scheduled_at"],
            duration_minutes=updated.get("duration_minutes") or 60,
            room_token=updated.get("room_token"),
            status=updated["status"],
            meeting_mode="scheduled",
        )

    async def start_instant(
        self,
        application_id: str,
        *,
        template_snapshot: dict[str, Any] | None = None,
    ) -> ScheduledInterviewResponse:
        """Create a recruiter-triggered interview invitation with a 10-minute deadline."""
        app = await self._app_repo.get_by_id(application_id)
        if not app:
            raise NotFoundError(f"Application {application_id} not found")
        if app["status"] not in {
            ApplicationStatus.SHORTLISTED.value,
            ApplicationStatus.INVITED.value,
        }:
            raise ValidationError("Instant meetings are available for shortlisted or invited candidates")
        snapshot = _copy_template_snapshot(template_snapshot)

        latest = await self._repo.get_latest_by_application_id(application_id)
        now = datetime.now(timezone.utc)
        if latest and latest.get("status") == "instant_pending":
            deadline = _as_utc_datetime(latest.get("scheduled_at"))
            if deadline and deadline > now:
                if snapshot is not None and snapshot != latest.get("template_snapshot"):
                    raise ConflictError("An instant invitation already exists with a different configuration")
                if app["status"] != ApplicationStatus.INVITED.value:
                    await self._app_repo.update_status(application_id, ApplicationStatus.INVITED.value)
                return self._response_for_interview(latest, meeting_mode="instant", deadline=deadline)

        deadline = now + timedelta(minutes=10)
        interview = await self._repo.create(
            {
                "id": str(uuid.uuid4()),
                "application_id": application_id,
                "job_id": app["job_id"],
                "candidate_id": app["candidate_id"],
                "slot_id": None,
                "status": "instant_pending",
                "room_token": str(uuid.uuid4()),
                # The existing scheduled_at column doubles as the durable
                # response deadline for an instant invitation.
                "scheduled_at": deadline.isoformat(),
                **({"template_snapshot": snapshot, "duration_minutes": snapshot["duration_minutes"]} if snapshot else {}),
                "created_at": now.isoformat(),
            }
        )
        # An instant meeting is also an invitation: the candidate portal must
        # render the acceptance action even when the recruiter started from
        # the shortlisted state.
        await self._app_repo.update_status(application_id, ApplicationStatus.INVITED.value)
        # A pending instant invite has no calendar start; the candidate opens
        # it immediately after accepting the invitation.
        self._ensure_live_session(app, interview, scheduled_start="")
        logger.info(
            "instant_interview_started",
            interview_id=interview["id"],
            application_id=application_id,
            response_deadline=deadline.isoformat(),
        )
        return self._response_for_interview(interview, meeting_mode="instant", deadline=deadline)

    async def respond_to_instant(
        self,
        application_id: str,
    ) -> ScheduledInterviewResponse:
        """Accept an instant invite before its deadline and open the meeting."""
        app = await self._app_repo.get_by_id(application_id)
        if not app:
            raise NotFoundError(f"Application {application_id} not found")
        interview = await self._repo.get_latest_by_application_id(application_id)
        if not interview or interview.get("status") != "instant_pending":
            raise ValidationError("There is no active instant interview invitation")

        deadline = _as_utc_datetime(interview.get("scheduled_at"))
        now = datetime.now(timezone.utc)
        if not deadline or deadline <= now:
            await self._repo.update(interview["id"], {"status": "instant_expired"})
            raise ValidationError("The instant interview invitation has expired")

        updated = await self._repo.update(
            interview["id"],
            {"status": "instant_active", "scheduled_at": now.isoformat()},
        )
        await self._app_repo.update_status(application_id, ApplicationStatus.SCHEDULED.value)
        self._update_live_session_start(interview["id"], None)
        logger.info("instant_interview_accepted", interview_id=interview["id"], application_id=application_id)
        return self._response_for_interview(updated, meeting_mode="instant")

    @staticmethod
    def _response_for_interview(
        interview: dict[str, Any],
        *,
        meeting_mode: str,
        deadline: datetime | None = None,
    ) -> ScheduledInterviewResponse:
        return ScheduledInterviewResponse(
            id=interview["id"],
            application_id=interview["application_id"],
            scheduled_at=interview["scheduled_at"],
            duration_minutes=interview.get("duration_minutes") or 60,
            room_token=interview.get("room_token"),
            status=interview["status"],
            meeting_mode=meeting_mode,
            response_deadline=deadline,
        )

    @staticmethod
    def _ensure_live_session(
        app: dict[str, Any],
        interview: dict[str, Any],
        scheduled_start: datetime | str | None = None,
    ) -> None:
        """Create the in-memory voice session used by the candidate lobby."""
        try:
            from app.sessions.models import InterviewConfiguration
            from app.sessions.service import interview_session_service

            job = app.get("jobs") or app.get("job") or {}
            snapshot = _copy_template_snapshot(interview.get("template_snapshot"))
            rounds = snapshot["rounds"] if snapshot else job.get("interview_rounds") or job.get("job_rounds") or []
            active_rounds = sorted(
                [r for r in rounds if isinstance(r, dict) and r.get("is_active", r.get("enabled", True))],
                key=lambda r: r.get("order_index", 0),
            )
            agent_ids: list[str] = []
            for round_row in active_rounds:
                for agent_id in decode_round_agents(round_row)[0]:
                    if agent_id not in agent_ids:
                        agent_ids.append(agent_id)
            agent_ids = agent_ids or ["alex"]
            candidate = app.get("candidates") or app.get("candidate") or {}
            parsed_resume = app.get("parsed_resume") or candidate.get("parsed_resumes") or {}
            if isinstance(parsed_resume, list):
                resumes = [row for row in parsed_resume if isinstance(row, dict)]
                application_id = app.get("id") or interview.get("application_id")
                matching = [row for row in resumes if application_id and row.get("application_id") == application_id]
                parsed_resume = max(matching or resumes, key=lambda row: str(row.get("created_at") or ""), default={})
            metadata = {
                "application_id": app.get("id") or interview.get("application_id"),
                "resume_id": parsed_resume.get("id"),
                "job_id": job.get("id") or app.get("job_id") or interview.get("job_id"),
                "job_title": job.get("title"),
                "job_description": job.get("description"),
                "required_skills": job.get("required_skills") or [],
                "required_competencies": (job.get("required_competencies") if not snapshot else None) or [
                    focus
                    for round_row in active_rounds
                    for focus in decode_round_agents(round_row)[1]
                ],
                "interview_rounds": [str(round_row.get("type") or "") for round_row in active_rounds],
                "round_configs": deepcopy(rounds),
                **({"template_id": snapshot["template_id"], "template_version": snapshot["template_version"]} if snapshot else {}),
                "candidate_name": candidate.get("name"),
                "candidate_email": candidate.get("email"),
                "candidate_skills": parsed_resume.get("skills") or [],
                "candidate_experience": parsed_resume.get("experience") or [],
                "candidate_education": parsed_resume.get("education") or [],
                "resume_url": candidate.get("resume_url") or app.get("resume_url"),
                "parsed_resume": parsed_resume,
            }
            source_start = interview.get("scheduled_at") if scheduled_start is None else scheduled_start
            parsed_start = _as_utc_datetime(source_start)
            interview_session_service.create_session(
                InterviewConfiguration(
                    interview_id=interview["id"],
                    candidate_id=app["candidate_id"],
                    agent_ids=agent_ids,
                    scheduled_start=parsed_start,
                    duration_minutes=snapshot["duration_minutes"] if snapshot else interview.get("duration_minutes") or 60,
                    job_title=job.get("title"),
                    company=job.get("company") or "Intra AI",
                    metadata=metadata,
                )
            )
        except Exception as exc:
            # Persistence and scheduling remain successful if a local live
            # session cannot be materialized; the platform can create it via
            # POST /sessions when the candidate is ready.
            logger.warning("live_session_materialization_failed", interview_id=interview.get("id"), error=str(exc))

    @staticmethod
    def _update_live_session_start(interview_id: str, scheduled_start: datetime | str | None) -> None:
        try:
            from app.sessions.service import interview_session_service

            session = interview_session_service.get_session(interview_id)
            if session:
                session.scheduled_start = _as_utc_datetime(scheduled_start)
                from app.sessions.store import session_store
                session_store.set(session)
        except Exception as exc:
            logger.warning("live_session_reschedule_sync_failed", interview_id=interview_id, error=str(exc))


def _as_utc_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _copy_template_snapshot(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        return TemplateSnapshot.model_validate(deepcopy(value)).model_dump(mode="json")
    except SchemaValidationError as exc:
        raise ValidationError("Interview template snapshot is invalid") from exc


def _slot_start(slot: dict[str, Any]) -> str:
    # Supabase returns TIME columns with seconds; clients may submit HH:MM.
    # An explicit time offset is honored; legacy naive slot times mean UTC.
    parsed = _as_utc_datetime(f"{slot['date']}T{slot['start_time']}")
    if parsed is None:
        raise ValidationError("The selected slot has an invalid start time")
    return parsed.astimezone(timezone.utc).isoformat()


def _require_slot_duration(slot: dict[str, Any], duration: int) -> None:
    start = _as_utc_datetime(_slot_start(slot))
    end = _as_utc_datetime(f"{slot['date']}T{slot.get('end_time', '')}")
    if end is None or end <= start or (end - start).total_seconds() < duration * 60:
        raise ValidationError("The selected slot is shorter than the interview template")
