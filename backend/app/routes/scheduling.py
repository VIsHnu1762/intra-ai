"""Scheduling routes — slot management, interview booking, listing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from supabase import Client

from app.core.deps import get_current_user, get_supabase
from app.core.security import require_role
from app.repositories.application_repo import ApplicationRepo
from app.repositories.interview_repo import InterviewRepo
from app.schemas.interviews import (
    InstantInterviewRequest,
    InterviewSlotResponse,
    ScheduleInterviewRequest,
    ScheduledInterviewResponse,
)
from app.services.interview_service import InterviewService
from app.services.scheduling_service import SchedulingService
from app.services.interview_template_service import InterviewTemplateService
from app.voice.authorization import Actor, identity, require_application, require_interview, require_job, require_recruiter
from app.services.workspace_access import WorkspaceAccess, current_actor, recruiter_actor

router = APIRouter(tags=["scheduling"])


def _scheduling_service(supabase: Client = Depends(get_supabase)) -> SchedulingService:
    return SchedulingService(
        interview_repo=InterviewRepo(supabase),
        app_repo=ApplicationRepo(supabase),
    )


def _interview_service(supabase: Client = Depends(get_supabase)) -> InterviewService:
    return InterviewService(interview_repo=InterviewRepo(supabase))


# ── Slots ────────────────────────────────────────────────────


@router.get("/jobs/{job_id}/slots", response_model=list[InterviewSlotResponse])
async def get_available_slots(
    job_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: SchedulingService = Depends(_scheduling_service),
    supabase: Client = Depends(get_supabase),
) -> list[InterviewSlotResponse]:
    """Get available interview slots for a job (admin/recruiter)."""
    await require_job(actor, job_id, supabase)
    return await service.get_available_slots(job_id)


@router.post(
    "/jobs/{job_id}/slots",
    response_model=list[InterviewSlotResponse],
    status_code=201,
)
async def create_slots(
    job_id: str,
    slots: list[dict[str, str]],
    actor: Actor = Depends(recruiter_actor),
    service: SchedulingService = Depends(_scheduling_service),
    supabase: Client = Depends(get_supabase),
) -> list[InterviewSlotResponse]:
    """Create interview slots for a job (admin/recruiter)."""
    await require_job(actor, job_id, supabase)
    return await service.create_slots(job_id, slots)


# ── Booking ──────────────────────────────────────────────────


@router.post(
    "/applications/{app_id}/schedule",
    response_model=ScheduledInterviewResponse,
    status_code=201,
)
async def book_slot(
    app_id: str,
    data: ScheduleInterviewRequest,
    user: dict[str, Any] = Depends(require_role("admin", "recruiter")),
    service: SchedulingService = Depends(_scheduling_service),
    supabase: Client = Depends(get_supabase),
) -> ScheduledInterviewResponse:
    """Recruiter books an available interview slot for a shortlisted candidate."""
    actor = await identity(user, supabase)
    require_recruiter(actor)
    await require_application(actor, app_id, supabase)
    if data.template_id:
        snapshot = await InterviewTemplateService(supabase).require_snapshot(actor, data.template_id)
        return await service.book_slot(application_id=app_id, slot_id=data.slot_id, template_snapshot=snapshot)
    return await service.book_slot(application_id=app_id, slot_id=data.slot_id)


@router.post(
    "/applications/{app_id}/reschedule",
    response_model=ScheduledInterviewResponse,
)
async def reschedule_interview(
    app_id: str,
    data: ScheduleInterviewRequest,
    user: dict[str, Any] = Depends(require_role("admin", "recruiter")),
    service: SchedulingService = Depends(_scheduling_service),
    supabase: Client = Depends(get_supabase),
) -> ScheduledInterviewResponse:
    """Move a scheduled interview to another recruiter-owned slot."""
    actor = await identity(user, supabase)
    require_recruiter(actor)
    await require_application(actor, app_id, supabase)
    if data.template_id:
        from app.core.exceptions import ValidationError
        raise ValidationError("Rescheduling preserves the original interview configuration")
    return await service.reschedule(application_id=app_id, slot_id=data.slot_id)


@router.post(
    "/applications/{app_id}/instant",
    response_model=ScheduledInterviewResponse,
    status_code=201,
)
async def start_instant_interview(
    app_id: str,
    data: InstantInterviewRequest | None = None,
    user: dict[str, Any] = Depends(require_role("admin", "recruiter")),
    service: SchedulingService = Depends(_scheduling_service),
    supabase: Client = Depends(get_supabase),
) -> ScheduledInterviewResponse:
    """Send a recruiter-triggered instant interview invitation."""
    actor = await identity(user, supabase)
    require_recruiter(actor)
    await require_application(actor, app_id, supabase)
    if data and data.template_id:
        snapshot = await InterviewTemplateService(supabase).require_snapshot(actor, data.template_id)
        return await service.start_instant(application_id=app_id, template_snapshot=snapshot)
    return await service.start_instant(application_id=app_id)


@router.post(
    "/applications/{app_id}/instant/respond",
    response_model=ScheduledInterviewResponse,
)
async def respond_to_instant_interview(
    app_id: str,
    actor: Actor = Depends(current_actor),
    service: SchedulingService = Depends(_scheduling_service),
    supabase: Client = Depends(get_supabase),
) -> ScheduledInterviewResponse:
    """Candidate accepts an instant invitation before its ten-minute deadline."""
    from app.core.exceptions import ForbiddenError
    if actor.role != "candidate":
        raise ForbiddenError("Only the invited candidate may accept this interview")
    await require_application(actor, app_id, supabase)
    return await service.respond_to_instant(application_id=app_id)


# ── Interview listing ────────────────────────────────────────


@router.get("/interviews", response_model=dict)
async def list_interviews(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    job_id: str | None = Query(None),
    actor: Actor = Depends(recruiter_actor),
    service: InterviewService = Depends(_interview_service),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """List all interviews (admin/recruiter)."""
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = status
    if job_id:
        await require_job(actor, job_id, supabase)
        filters["job_id"] = job_id
    filters["job_ids"] = await WorkspaceAccess(supabase, actor).job_ids()

    interviews, total = await service.list_interviews(
        filters=filters, page=page, per_page=per_page
    )
    return {"interviews": interviews, "total": total}


@router.get("/interviews/{interview_id}", response_model=ScheduledInterviewResponse)
async def get_interview(
    interview_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: InterviewService = Depends(_interview_service),
    supabase: Client = Depends(get_supabase),
) -> ScheduledInterviewResponse:
    """Get interview details."""
    await require_interview(actor, interview_id, supabase)
    return await service.get_interview(interview_id)
