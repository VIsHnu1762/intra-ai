"""Candidate routes — list, detail, applications."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from supabase import Client

from app.core.deps import get_current_user, get_supabase
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import require_role
from app.repositories.candidate_repo import CandidateRepo
from app.schemas.candidates import CandidateResponse
from app.services.workspace_access import WorkspaceAccess, current_actor, recruiter_actor
from app.voice.authorization import Actor, require_candidate

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _candidate_repo(supabase: Client = Depends(get_supabase)) -> CandidateRepo:
    return CandidateRepo(supabase)


@router.get("", response_model=dict)
async def list_candidates(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    actor: Actor = Depends(recruiter_actor),
    repo: CandidateRepo = Depends(_candidate_repo),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """List all candidates (admin/recruiter)."""
    filters: dict[str, Any] = {}
    if search:
        filters["search"] = search
    workspace = WorkspaceAccess(supabase, actor)
    filters["candidate_ids"] = await workspace.related_ids("applications", "candidate_id", await workspace.job_ids())
    filters["tenant_id"] = actor.tenant_id

    rows, total = await repo.list(filters=filters, page=page, per_page=per_page)
    candidates = [
        CandidateResponse(
            id=r["id"],
            name=r["name"],
            email=r["email"],
            phone=r.get("phone"),
            resume_url=None,
            parsed_resume=None,
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return {"candidates": candidates, "total": total}


@router.get("/me/applications", response_model=dict)
async def get_my_applications(
    actor: Actor = Depends(current_actor),
    repo: CandidateRepo = Depends(_candidate_repo),
) -> dict:
    """Return applications belonging to the authenticated candidate."""
    if actor.role != "candidate":
        raise ForbiddenError("This page is available to candidates only")
    if not actor.candidate_id:
        return {"applications": [], "total": 0}
    applications = await repo.list_applications(actor.candidate_id)
    return {"applications": applications, "total": len(applications)}


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: str,
    actor: Actor = Depends(recruiter_actor),
    repo: CandidateRepo = Depends(_candidate_repo),
    supabase: Client = Depends(get_supabase),
) -> CandidateResponse:
    """Get candidate detail with parsed resume."""
    row = await require_candidate(actor, candidate_id, supabase)

    parsed = row.pop("parsed_resumes", None)
    parsed_first = max(parsed, key=lambda item: str(item.get("created_at") or ""), default=None) if isinstance(parsed, list) else parsed
    applications = await repo.list_applications(candidate_id)
    allowed = set(row["authorized_application_ids"])
    owned = [application for application in applications if application["id"] in allowed]
    latest = max(owned, key=lambda item: str(item.get("created_at") or ""), default={})

    return CandidateResponse(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        phone=row.get("phone"),
        resume_url=latest.get("resume_url"),
        parsed_resume=parsed_first,
        created_at=row["created_at"],
    )


@router.get("/{candidate_id}/applications", response_model=dict)
async def get_candidate_applications(
    candidate_id: str,
    actor: Actor = Depends(recruiter_actor),
    repo: CandidateRepo = Depends(_candidate_repo),
    supabase: Client = Depends(get_supabase),
) -> dict:
    """Get all applications for a candidate."""
    # Verify candidate exists
    candidate = await require_candidate(actor, candidate_id, supabase)

    applications = await repo.list_applications(candidate_id)
    allowed = set(candidate["authorized_application_ids"])
    applications = [
        {key: value for key, value in row.items() if key not in {"candidate", "candidates", "parsed_resumes"}}
        for row in applications if row["id"] in allowed
    ]
    return {"applications": applications, "total": len(applications)}
