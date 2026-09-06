"""Report routes — generate, retrieve, download PDF."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from supabase import Client

from app.core.deps import get_current_user, get_supabase
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import require_role
from app.repositories.interview_repo import InterviewRepo
from app.repositories.job_repo import JobRepo
from app.schemas.reports import CandidatePerformanceResponse, ReportListResponse, ReportResponse, ReportStatusResponse
from app.services.report_service import ReportService
from app.services.workspace_access import WorkspaceAccess, current_actor, recruiter_actor
from app.voice.authorization import Actor, require_interview, require_job

router = APIRouter(prefix="/interviews", tags=["reports"])
reports_router = APIRouter(prefix="/reports", tags=["reports"])


def _report_service(supabase: Client = Depends(get_supabase)) -> ReportService:
    return ReportService(
        interview_repo=InterviewRepo(supabase),
        job_repo=JobRepo(supabase),
    )


@reports_router.get("", response_model=ReportListResponse)
async def list_reports(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    recommendation: str | None = Query(None),
    interview_id: str | None = Query(None),
    job_id: str | None = Query(None),
    actor: Actor = Depends(recruiter_actor),
    service: ReportService = Depends(_report_service),
    supabase: Client = Depends(get_supabase),
) -> ReportListResponse:
    """List generated reports for the recruiter workspace."""
    filters: dict[str, Any] = {}
    if recommendation:
        filters["recommendation"] = recommendation
    if interview_id:
        await require_interview(actor, interview_id, supabase)
        filters["interview_id"] = interview_id
    workspace = WorkspaceAccess(supabase, actor)
    if job_id:
        await require_job(actor, job_id, supabase)
    job_ids = [job_id] if job_id else await workspace.job_ids()
    filters["interview_ids"] = await workspace.related_ids("scheduled_interviews", "id", job_ids)
    return await service.list_reports(filters=filters, page=page, per_page=per_page)


@reports_router.get("/{id_or_interview_id}", response_model=ReportResponse)
async def get_report_by_key(
    id_or_interview_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    service: ReportService = Depends(_report_service),
) -> ReportResponse:
    await service.ensure_access(id_or_interview_id, user)
    return await service.get_report_by_key(id_or_interview_id)


@reports_router.get("/{id_or_interview_id}/status", response_model=ReportStatusResponse)
async def report_status(
    id_or_interview_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: ReportService = Depends(_report_service),
    supabase: Client = Depends(get_supabase),
) -> ReportStatusResponse:
    interview_id = await service.resolve_interview_id(id_or_interview_id)
    await require_interview(actor, interview_id, supabase)
    return await service.status(interview_id)


@router.get("/{interview_id}/performance", response_model=CandidatePerformanceResponse)
async def candidate_performance(
    interview_id: str,
    actor: Actor = Depends(current_actor),
    service: ReportService = Depends(_report_service),
    supabase: Client = Depends(get_supabase),
) -> CandidatePerformanceResponse:
    if actor.role != "candidate":
        raise ForbiddenError("Candidate performance is available through the candidate portal")
    await require_interview(actor, interview_id, supabase)
    return await service.candidate_performance(interview_id)


@router.post("/{interview_id}/report/generate", response_model=ReportStatusResponse, status_code=202)
async def generate_report(
    interview_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: ReportService = Depends(_report_service),
    supabase: Client = Depends(get_supabase),
) -> ReportStatusResponse:
    """Generate a comprehensive assessment report for an interview."""
    await require_interview(actor, interview_id, supabase)
    return await service.request_report(interview_id)


@router.get("/{interview_id}/report", response_model=ReportResponse)
async def get_report(
    interview_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    service: ReportService = Depends(_report_service),
) -> ReportResponse:
    """Get the assessment report for an interview."""
    await service.ensure_access(interview_id, user)
    return await service.get_report(interview_id)


@router.get("/{interview_id}/report/pdf")
async def download_report_pdf(
    interview_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    service: ReportService = Depends(_report_service),
) -> RedirectResponse:
    """Download the report as a PDF. Redirects to the S3 pre-signed URL."""
    await service.ensure_access(interview_id, user)
    report = await service.get_report(interview_id)
    if not report.pdf_url:
        raise NotFoundError("PDF has not been generated for this report")
    return RedirectResponse(url=report.pdf_url)
