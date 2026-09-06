"""Application routes — apply (multipart), list, shortlist, reject."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from supabase import Client

from app.core.deps import get_current_user, get_supabase
from app.core.exceptions import NotFoundError
from app.core.security import require_role
from app.repositories.application_repo import ApplicationRepo
from app.repositories.candidate_repo import CandidateRepo
from app.repositories.job_repo import JobRepo
from app.schemas.applications import ApplicationListResponse, ApplicationResponse
from app.schemas.candidates import ParsedResumeResponse
from app.services.application_service import ApplicationService
from app.services.workspace_access import recruiter_actor, current_actor
from app.voice.authorization import Actor, require_application, require_job
from app.integrations.resume_storage import (
    content_type_for_extension,
    download_from_supabase,
    make_supabase_key,
)

router = APIRouter(tags=["applications"])


def _app_service(supabase: Client = Depends(get_supabase)) -> ApplicationService:
    return ApplicationService(
        app_repo=ApplicationRepo(supabase),
        candidate_repo=CandidateRepo(supabase),
        job_repo=JobRepo(supabase),
    )


# ── Public apply ─────────────────────────────────────────────


@router.post("/jobs/{job_id}/apply", response_model=ApplicationResponse, status_code=201)
async def apply(
    job_id: str,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    years_experience: int = Form(...),
    resume: UploadFile = File(...),
    current_role: str | None = Form(None),
    current_company: str | None = Form(None),
    expected_salary_min: float | None = Form(None),
    expected_salary_max: float | None = Form(None),
    linkedin_url: str | None = Form(None),
    service: ApplicationService = Depends(_app_service),
) -> ApplicationResponse:
    """Public endpoint: submit a job application with resume upload."""
    return await service.apply(
        job_id=job_id,
        name=name,
        email=email,
        phone=phone,
        years_experience=years_experience,
        resume_file=resume,
        current_role=current_role,
        current_company=current_company,
        expected_salary_min=expected_salary_min,
        expected_salary_max=expected_salary_max,
        linkedin_url=linkedin_url,
    )


# ── Admin / Recruiter endpoints ─────────────────────────────


@router.get("/jobs/{job_id}/applications", response_model=ApplicationListResponse)
async def list_applications(
    job_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    actor: Actor = Depends(recruiter_actor),
    service: ApplicationService = Depends(_app_service),
    supabase: Client = Depends(get_supabase),
) -> ApplicationListResponse:
    """List applications for a specific job (admin/recruiter)."""
    await require_job(actor, job_id, supabase)
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = status
    return await service.get_applications(
        job_id=job_id, filters=filters, page=page, per_page=per_page
    )


@router.get("/applications/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: ApplicationService = Depends(_app_service),
    supabase: Client = Depends(get_supabase),
) -> ApplicationResponse:
    """Get a single application detail."""
    await require_application(actor, app_id, supabase)
    return await service.get_application(app_id)


@router.get("/applications/{app_id}/parsed-resume", response_model=ParsedResumeResponse)
async def get_parsed_resume(
    app_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: ApplicationService = Depends(_app_service),
    supabase: Client = Depends(get_supabase),
) -> ParsedResumeResponse:
    """Get parsed resume data for an application."""
    await require_application(actor, app_id, supabase)
    return await service.get_parsed_resume(app_id)


@router.get("/applications/{app_id}/resume/{extension}")
async def download_application_resume(
    app_id: str,
    extension: str,
    actor: Actor = Depends(current_actor),
    service: ApplicationService = Depends(_app_service),
    supabase: Client = Depends(get_supabase),
) -> Response:
    """Serve a private CV to its candidate or the job's authorized recruiter."""
    await require_application(actor, app_id, supabase)
    extension = extension.lower().lstrip(".")
    if extension not in {"pdf", "doc", "docx", "txt", "rtf"}:
        raise NotFoundError("Resume file type is not supported")

    row = await service._app_repo.get_by_id(app_id)
    if not row or not row.get("resume_url", "").endswith(f"/resume/{extension}"):
        raise NotFoundError(f"Resume for application {app_id} not found")

    try:
        content = download_from_supabase(
            service._app_repo._sb,
            make_supabase_key(app_id, extension),
        )
    except Exception as exc:
        raise NotFoundError(f"Resume for application {app_id} is unavailable") from exc

    return Response(
        content=content,
        media_type=content_type_for_extension(extension),
        headers={"Content-Disposition": f'inline; filename="resume.{extension}"'},
    )


@router.post("/applications/{app_id}/resume", response_model=ApplicationResponse)
async def replace_application_resume(
    app_id: str,
    resume: UploadFile = File(...),
    actor: Actor = Depends(recruiter_actor),
    service: ApplicationService = Depends(_app_service),
    supabase: Client = Depends(get_supabase),
) -> ApplicationResponse:
    """Replace and reparse a candidate resume from the recruiter dossier."""
    await require_application(actor, app_id, supabase)
    return await service.replace_resume(app_id, resume)


@router.post("/applications/{app_id}/shortlist", response_model=ApplicationResponse)
async def shortlist_application(
    app_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: ApplicationService = Depends(_app_service),
    supabase: Client = Depends(get_supabase),
) -> ApplicationResponse:
    """Manually shortlist an application."""
    await require_application(actor, app_id, supabase)
    return await service.shortlist(app_id)


@router.post("/applications/{app_id}/reject", response_model=ApplicationResponse)
async def reject_application(
    app_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: ApplicationService = Depends(_app_service),
    supabase: Client = Depends(get_supabase),
) -> ApplicationResponse:
    """Manually reject an application."""
    await require_application(actor, app_id, supabase)
    return await service.reject(app_id)


@router.post("/applications/{app_id}/invite", response_model=ApplicationResponse)
async def invite_application(
    app_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: ApplicationService = Depends(_app_service),
    supabase: Client = Depends(get_supabase),
) -> ApplicationResponse:
    """Invite a shortlisted candidate to choose an interview slot."""
    await require_application(actor, app_id, supabase)
    return await service.invite(app_id)
