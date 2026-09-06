"""Persisted identity and workspace authorization for auxiliary voice sessions.

JWT claims identify a user, never grant workspace/resource access. Recruiter
access follows the job creator, with matching tenant tags where present.
Sharing a tenant or an admin role never grants access to another recruiter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.repositories.application_repo import ApplicationRepo
from app.repositories.candidate_repo import CandidateRepo
from app.repositories.interview_repo import InterviewRepo
from app.repositories.job_repo import JobRepo
from app.repositories.user_repo import UserRepo


@dataclass(frozen=True)
class Actor:
    user_id: str
    role: str
    email: str
    name: str
    tenant_id: str | None = None
    candidate_id: str | None = None


async def identity(user_claims: dict[str, Any], supabase: Any) -> Actor:
    subject = user_claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise UnauthorizedError()
    user = await UserRepo(supabase).get_user_by_id(subject)
    if not user or str(user.get("id")) != subject or user.get("is_active") is False:
        raise UnauthorizedError("User is no longer active")
    role = user.get("role")
    if role not in {"admin", "recruiter", "candidate"}:
        raise ForbiddenError()
    email = str(user.get("email") or "").strip().lower()
    candidate_id = None
    if role == "candidate":
        candidate = await CandidateRepo(supabase).get_by_email(email) if email else None
        if candidate:
            if user.get("tenant_id") is not None:
                _tenant_match(user.get("tenant_id"), candidate)
            candidate_id = str(candidate["id"])
    return Actor(subject, role, email, str(user.get("name") or ""), user.get("tenant_id"), candidate_id)


def require_recruiter(actor: Actor) -> None:
    if actor.role not in {"admin", "recruiter"}:
        raise ForbiddenError("This operation is available to recruiters only")


def _tenant_match(tenant_id: str | None, row: dict[str, Any]) -> None:
    # A row without a tenant column inherits scope through its parent resource.
    # An explicitly tenant-tagged row must always match the persisted identity.
    row_tenant = row.get("tenant_id")
    if row_tenant is not None and (tenant_id is None or str(row_tenant) != str(tenant_id)):
        raise ForbiddenError("Resource is outside your workspace")


def _job_owned(actor: Actor, job: dict[str, Any]) -> bool:
    owners = [str(job[key]) for key in ("created_by", "recruiter_id") if job.get(key)]
    if not owners or not all(owner == actor.user_id for owner in owners):
        return False
    if actor.tenant_id is not None or job.get("tenant_id") is not None:
        return bool(actor.tenant_id and job.get("tenant_id") and str(actor.tenant_id) == str(job["tenant_id"]))
    return True


async def require_job(actor: Actor, job_id: str, supabase: Any) -> dict[str, Any]:
    job = await JobRepo(supabase).get_by_id(job_id)
    if not job:
        raise NotFoundError("Job not found")
    if actor.role != "candidate" or actor.tenant_id is not None:
        _tenant_match(actor.tenant_id, job)
    if actor.role == "candidate":
        if not actor.candidate_id:
            raise ForbiddenError("No linked candidate profile")
        application = await ApplicationRepo(supabase).get_by_job_and_candidate(job_id, actor.candidate_id)
        if not application:
            raise ForbiddenError("You may only use jobs you applied to")
        if actor.tenant_id is not None:
            _tenant_match(actor.tenant_id, application)
    elif not _job_owned(actor, job):
        raise ForbiddenError("Job is outside your workspace")
    return job


async def require_application(actor: Actor, application_id: str, supabase: Any) -> dict[str, Any]:
    row = await ApplicationRepo(supabase).get_by_id(application_id)
    if not row:
        raise NotFoundError("Application not found")
    if actor.role != "candidate" or actor.tenant_id is not None:
        _tenant_match(actor.tenant_id, row)
    if actor.role == "candidate" and str(row.get("candidate_id")) != actor.candidate_id:
        raise ForbiddenError("You may only use your own applications")
    await require_job(actor, str(row.get("job_id") or ""), supabase)
    candidate = await CandidateRepo(supabase).get_by_id(str(row.get("candidate_id") or ""))
    if not candidate:
        raise NotFoundError("Candidate not found")
    if actor.role != "candidate" or actor.tenant_id is not None:
        _tenant_match(actor.tenant_id, candidate)
    return row


async def require_candidate(actor: Actor, candidate_id: str, supabase: Any) -> dict[str, Any]:
    if actor.role == "candidate" and candidate_id != actor.candidate_id:
        raise ForbiddenError("You may only use your own candidate profile")
    candidate = await CandidateRepo(supabase).get_by_id(candidate_id)
    if not candidate:
        raise NotFoundError("Candidate not found")
    if actor.role != "candidate" or actor.tenant_id is not None:
        _tenant_match(actor.tenant_id, candidate)
    if actor.role == "candidate":
        return candidate
    applications = await CandidateRepo(supabase).list_applications(candidate_id)
    allowed = []
    for application in applications:
        try:
            await require_application(actor, str(application["id"]), supabase)
        except (ForbiddenError, NotFoundError):
            continue
        allowed.append(str(application["id"]))
    if not allowed:
        raise ForbiddenError("Candidate is outside your workspace")
    # Candidates can apply to multiple companies. Never expose another job's
    # uploaded resume/parsed data through the shared candidate row.
    result = dict(candidate)
    parsed = result.get("parsed_resumes") or []
    if isinstance(parsed, dict):
        parsed = [parsed]
    result["parsed_resumes"] = [item for item in parsed if str(item.get("application_id")) in allowed]
    result.pop("resume_url", None)
    result["authorized_application_ids"] = allowed
    return result


async def require_interview(actor: Actor, interview_id: str, supabase: Any) -> dict[str, Any]:
    row = await InterviewRepo(supabase).get_by_id(interview_id)
    if not row:
        raise NotFoundError("Interview not found")
    if actor.role != "candidate" or actor.tenant_id is not None:
        _tenant_match(actor.tenant_id, row)
    application = await require_application(actor, str(row.get("application_id") or ""), supabase)
    if row.get("job_id") != application.get("job_id") or row.get("candidate_id") != application.get("candidate_id"):
        raise ForbiddenError("Interview relationship is invalid")
    return row


async def require_report(actor: Actor, report_id: str, supabase: Any) -> dict[str, Any]:
    repo = InterviewRepo(supabase)
    row = await repo.get_report_by_id(report_id) or await repo.get_report(report_id)
    if not row:
        raise NotFoundError("Report not found")
    if actor.role != "candidate" or actor.tenant_id is not None:
        _tenant_match(actor.tenant_id, row)
    await require_interview(actor, str(row.get("interview_id") or ""), supabase)
    return row
