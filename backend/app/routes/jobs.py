"""Job posting routes — public listings, admin CRUD, publish, archive."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from starlette.datastructures import UploadFile
from supabase import Client

from app.core.deps import get_current_user, get_supabase
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import require_role
from app.repositories.job_repo import JobRepo
from app.schemas.common import MessageResponse
from app.schemas.jobs import JobCreate, JobListResponse, JobResponse, JobUpdate, JdParseResponse
from app.services.job_service import JobService
from app.services.jd_service import parse_job_document, parse_job_description
from app.services.workspace_access import WorkspaceAccess, recruiter_actor
from app.voice.authorization import Actor, require_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job_service(supabase: Client = Depends(get_supabase)) -> JobService:
    return JobService(job_repo=JobRepo(supabase))


# ── Public endpoints (no auth) ──────────────────────────────


@router.get("/public", response_model=JobListResponse)
async def list_public_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    department: str | None = Query(None),
    service: JobService = Depends(_job_service),
) -> JobListResponse:
    """List published job postings (public, no auth required)."""
    filters: dict[str, Any] = {}
    if search:
        filters["search"] = search
    if department:
        filters["department"] = department
    return await service.get_public_jobs(filters=filters, page=page, per_page=per_page)


@router.get("/public/{job_id}", response_model=JobResponse)
async def get_public_job(
    job_id: str,
    service: JobService = Depends(_job_service),
) -> JobResponse:
    """Get a single published job detail (public)."""
    job = await service.get_job(job_id)
    if job.status != "published":
        raise NotFoundError("Published job not found")
    return job


@router.post("/parse-jd", response_model=JdParseResponse)
async def parse_jd(
    request: Request,
    actor: Actor = Depends(recruiter_actor),
) -> JdParseResponse:
    """Parse raw JD text or an uploaded PDF/DOCX into a recruiter-editable preview."""
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        raw_text = form.get("text")
        if isinstance(upload, UploadFile):
            return parse_job_document(await upload.read(), upload.filename, upload.content_type)
        if isinstance(raw_text, str) and raw_text.strip():
            return parse_job_description(raw_text)
    elif "application/json" in content_type:
        payload = await request.json()
        raw_text = payload.get("text") if isinstance(payload, dict) else None
        if isinstance(raw_text, str) and raw_text.strip():
            return parse_job_description(raw_text)
    raise ValidationError("Provide JD text or a PDF/DOCX file")


# ── Admin / Recruiter endpoints ─────────────────────────────


@router.get("", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    search: str | None = Query(None),
    department: str | None = Query(None),
    actor: Actor = Depends(recruiter_actor),
    service: JobService = Depends(_job_service),
    supabase: Client = Depends(get_supabase),
) -> JobListResponse:
    """List all jobs (admin/recruiter, all statuses)."""
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = status
    if search:
        filters["search"] = search
    if department:
        filters["department"] = department
    filters["job_ids"] = await WorkspaceAccess(supabase, actor).job_ids()
    return await service.get_jobs(filters=filters, page=page, per_page=per_page)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: JobService = Depends(_job_service),
    supabase: Client = Depends(get_supabase),
) -> JobResponse:
    """Get a single job for the recruiter workspace."""
    await require_job(actor, job_id, supabase)
    return await service.get_job(job_id)


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    data: JobCreate,
    actor: Actor = Depends(recruiter_actor),
    service: JobService = Depends(_job_service),
) -> JobResponse:
    """Create a new job posting (draft)."""
    return await service.create_job(data, user_id=actor.user_id, tenant_id=actor.tenant_id)


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: str,
    data: JobUpdate,
    actor: Actor = Depends(recruiter_actor),
    service: JobService = Depends(_job_service),
    supabase: Client = Depends(get_supabase),
) -> JobResponse:
    """Update a job posting."""
    await require_job(actor, job_id, supabase)
    return await service.update_job(job_id, data)


@router.post("/{job_id}/publish", response_model=JobResponse)
async def publish_job(
    job_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: JobService = Depends(_job_service),
    supabase: Client = Depends(get_supabase),
) -> JobResponse:
    """Publish a draft job posting."""
    await require_job(actor, job_id, supabase)
    return await service.publish_job(job_id)


@router.post("/{job_id}/archive", response_model=JobResponse)
async def archive_job(
    job_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: JobService = Depends(_job_service),
    supabase: Client = Depends(get_supabase),
) -> JobResponse:
    """Archive a job posting."""
    await require_job(actor, job_id, supabase)
    return await service.archive_job(job_id)
