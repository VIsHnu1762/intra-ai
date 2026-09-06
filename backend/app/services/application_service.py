"""Application service — apply, shortlist, reject, list."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import UploadFile

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.integrations import s3_client
from app.integrations import resume_storage
from app.models.enums import ApplicationStatus
from app.repositories.application_repo import ApplicationRepo
from app.repositories.candidate_repo import CandidateRepo
from app.repositories.job_repo import JobRepo
from app.schemas.applications import ApplicationListResponse, ApplicationResponse
from app.schemas.candidates import ParsedResumeResponse
from app.core.config import settings

logger = structlog.stdlib.get_logger("intra_ai.service.application")


class ApplicationService:
    """Handles the candidate application lifecycle."""

    def __init__(
        self,
        app_repo: ApplicationRepo,
        candidate_repo: CandidateRepo,
        job_repo: JobRepo,
    ) -> None:
        self._app_repo = app_repo
        self._candidate_repo = candidate_repo
        self._job_repo = job_repo

    async def apply(
        self,
        job_id: str,
        name: str,
        email: str,
        phone: str,
        years_experience: int,
        resume_file: UploadFile,
        current_role: str | None = None,
        current_company: str | None = None,
        expected_salary_min: float | None = None,
        expected_salary_max: float | None = None,
        linkedin_url: str | None = None,
    ) -> ApplicationResponse:
        """Process a new application: upload resume, create candidate, create application."""
        email = email.strip().lower()
        # Verify job exists and is published
        job = await self._job_repo.get_by_id(job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")
        if job.get("status") != "published":
            raise ValidationError("This job is not accepting applications")

        # Get or create candidate
        candidate = await self._candidate_repo.get_by_email(email)
        if not candidate:
            candidate_id = str(uuid.uuid4())
            candidate = await self._candidate_repo.create(
                {
                    "id": candidate_id,
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        else:
            candidate_id = candidate["id"]

        # A candidate can submit at most one application per job. Check after
        # resolving the candidate so retries are safe even when the first
        # request already created the candidate row.
        existing_application = await self._app_repo.get_by_job_and_candidate(
            job_id, candidate_id
        )
        if existing_application:
            raise ConflictError(
                "You have already applied for this position with this email address"
            )

        # Read once so parsing can proceed even while AWS/S3 remains paused.
        resume_bytes = await resume_file.read()
        try:
            resume_file.file.seek(0)
        except Exception:
            pass

        # Upload resume to S3 when configured. AWS is optional during local/Supabase
        # validation; the application remains usable when no bucket is configured.
        app_id = str(uuid.uuid4())
        extension = resume_storage.file_extension(resume_file.filename, resume_file.content_type)
        content_type = resume_file.content_type or resume_storage.content_type_for_extension(extension)
        resume_url = None
        if settings.AWS_S3_BUCKET:
            try:
                resume_key = s3_client.make_resume_key(job_id, resume_file.filename or "resume.pdf")
                resume_url = await s3_client.upload_file(
                    resume_file.file,
                    resume_key,
                    content_type=content_type,
                )
            except Exception as exc:
                logger.warning("resume_upload_failed_application_continues", error_type=type(exc).__name__)
        else:
            # Keep AWS paused while retaining the uploaded file in the supplied
            # Supabase project. The object remains private and is served only by
            # the authenticated recruiter download route.
            try:
                storage_key = resume_storage.make_supabase_key(app_id, extension)
                resume_storage.upload_to_supabase(
                    self._app_repo._sb,
                    storage_key,
                    resume_bytes,
                    content_type,
                )
                resume_url = resume_storage.internal_resume_url(app_id, extension)
            except Exception as exc:
                logger.warning(
                    "supabase_resume_upload_failed_application_continues",
                    error_type=type(exc).__name__,
                )

        # Update candidate resume_url
        if resume_url:
            self._candidate_repo._sb.table("candidates").update(
                {"resume_url": resume_url}
            ).eq("id", candidate_id).execute()

        # Create application
        now = datetime.now(timezone.utc).isoformat()

        try:
            app_row = await self._app_repo.create(
                {
                    "id": app_id,
                    "job_id": job_id,
                    "candidate_id": candidate_id,
                    "status": ApplicationStatus.APPLIED.value,
                    "years_experience": years_experience,
                    "current_role": current_role,
                    "current_company": current_company,
                    "expected_salary_min": expected_salary_min,
                    "expected_salary_max": expected_salary_max,
                    "linkedin_url": linkedin_url,
                    "resume_url": resume_url,
                    "created_at": now,
                }
            )
        except Exception as exc:
            # The database unique index is the final race-safe guard. Normalize
            # its violation into the same retry-safe API contract as the
            # preflight lookup above.
            if getattr(exc, "code", None) in {"23505", "PGRST116"} or "duplicate key" in str(exc).lower():
                raise ConflictError(
                    "You have already applied for this position with this email address"
                ) from exc
            raise

        # Parse and score immediately when the repository exposes the shared
        # Supabase client. Failures are isolated so a transient model outage does
        # not discard a valid application.
        try:
            from app.repositories.interview_repo import InterviewRepo
            from app.services.eligibility_service import EligibilityService
            from app.services.resume_service import ResumeService

            resume_service = ResumeService(self._app_repo, InterviewRepo(self._app_repo._sb))
            await resume_service.parse_resume_content(
                application_id=app_id,
                candidate_id=candidate_id,
                content=resume_bytes,
                filename=resume_file.filename,
                content_type=resume_file.content_type,
            )
            await EligibilityService(self._app_repo, self._job_repo).check_eligibility(app_id)
        except Exception as exc:
            try:
                await self._app_repo.update_status(app_id, ApplicationStatus.APPLIED.value)
            except Exception:
                pass
            logger.warning(
                "application_enrichment_deferred",
                app_id=app_id,
                error=str(exc)[:240],
                error_type=type(exc).__name__,
            )

        final_row = await self._app_repo.get_by_id(app_id) or app_row

        logger.info(
            "application_created",
            app_id=app_id,
            job_id=job_id,
            candidate_id=candidate_id,
            email=email,
        )

        return ApplicationResponse(
            id=final_row["id"],
            job_id=final_row["job_id"],
            candidate_id=final_row["candidate_id"],
            status=final_row["status"],
            eligibility_score=final_row.get("eligibility_score"),
            resume_url=final_row.get("resume_url"),
            created_at=final_row["created_at"],
        )

    async def get_applications(
        self,
        job_id: str,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> ApplicationListResponse:
        """List applications for a specific job."""
        rows, total = await self._app_repo.list_by_job(
            job_id, filters=filters, page=page, per_page=per_page
        )
        return ApplicationListResponse(
            applications=[self._to_response(r) for r in rows],
            total=total,
        )

    async def get_application(self, app_id: str) -> ApplicationResponse:
        """Get a single application by ID."""
        row = await self._app_repo.get_by_id(app_id)
        if not row:
            raise NotFoundError(f"Application {app_id} not found")
        return self._to_response(row)

    async def get_parsed_resume(self, app_id: str) -> ParsedResumeResponse:
        """Get parsed resume data for an application."""
        row = await self._app_repo.get_parsed_resume(app_id)
        if not row:
            raise NotFoundError(f"No parsed resume for application {app_id}")
        return ParsedResumeResponse(
            skills=row.get("skills", []),
            experience=row.get("experience", []),
            education=row.get("education", []),
            certifications=row.get("certifications", []),
            projects=row.get("projects", []),
        )

    async def replace_resume(self, app_id: str, resume_file: UploadFile) -> ApplicationResponse:
        """Replace an application resume, then reparse and rescore it.

        Recruiters can correct a mistaken or unreadable upload without asking a
        candidate to create a duplicate application. Existing recruiter
        decisions (shortlisted/invited and later interview states) are retained
        while the new automated score is refreshed.
        """
        existing = await self._app_repo.get_by_id(app_id)
        if not existing:
            raise NotFoundError(f"Application {app_id} not found")

        content = await resume_file.read()
        if not content:
            raise ValidationError("The replacement resume file is empty")

        extension = resume_storage.file_extension(resume_file.filename, resume_file.content_type)
        content_type = resume_file.content_type or resume_storage.content_type_for_extension(extension)
        if settings.AWS_S3_BUCKET:
            try:
                key = s3_client.make_resume_key(existing["job_id"], resume_file.filename or "resume.pdf")
                import io

                resume_url = await s3_client.upload_file(
                    io.BytesIO(content), key, content_type=content_type
                )
            except Exception as exc:
                raise ValidationError("The resume could not be stored") from exc
        else:
            try:
                storage_key = resume_storage.make_supabase_key(app_id, extension)
                resume_storage.upload_to_supabase(
                    self._app_repo._sb, storage_key, content, content_type
                )
                resume_url = resume_storage.internal_resume_url(app_id, extension)
            except Exception as exc:
                raise ValidationError("The resume could not be stored") from exc

        self._app_repo._sb.table("applications").update(
            {"resume_url": resume_url}
        ).eq("id", app_id).execute()
        self._candidate_repo._sb.table("candidates").update(
            {"resume_url": resume_url}
        ).eq("id", existing["candidate_id"]).execute()

        previous_status = existing["status"]
        try:
            from app.repositories.interview_repo import InterviewRepo
            from app.services.eligibility_service import EligibilityService
            from app.services.resume_service import ResumeService

            resume_service = ResumeService(self._app_repo, InterviewRepo(self._app_repo._sb))
            await resume_service.parse_resume_content(
                application_id=app_id,
                candidate_id=existing["candidate_id"],
                content=content,
                filename=resume_file.filename,
                content_type=resume_file.content_type,
            )
            await EligibilityService(self._app_repo, self._job_repo).check_eligibility(app_id)
        except Exception as exc:
            await self._app_repo.update_status(app_id, previous_status)
            raise ValidationError("The resume was stored, but parsing failed. Please try another PDF or DOCX file.") from exc

        if previous_status in {
            ApplicationStatus.SHORTLISTED.value,
            ApplicationStatus.INVITED.value,
            ApplicationStatus.SCHEDULED.value,
            ApplicationStatus.IN_PROGRESS.value,
            ApplicationStatus.COMPLETED.value,
        }:
            await self._app_repo.update_status(app_id, previous_status)

        refreshed = await self._app_repo.get_by_id(app_id)
        if not refreshed:
            raise NotFoundError(f"Application {app_id} not found after resume replacement")
        return self._to_response(refreshed)

    async def shortlist(self, app_id: str) -> ApplicationResponse:
        """Manually shortlist an application."""
        existing = await self._app_repo.get_by_id(app_id)
        if not existing:
            raise NotFoundError(f"Application {app_id} not found")
        if existing["status"] in (
            ApplicationStatus.SHORTLISTED.value,
            ApplicationStatus.INVITED.value,
        ):
            # Eligibility enrichment can shortlist automatically before a
            # recruiter opens the application. Keep the manual action
            # idempotent and never regress an already invited candidate.
            return self._to_response(existing)
        if existing["status"] not in (
            ApplicationStatus.APPLIED.value,
            ApplicationStatus.PARSING.value,
            ApplicationStatus.REJECTED.value,
        ):
            raise ValidationError(f"Cannot shortlist application in '{existing['status']}' state")

        row = await self._app_repo.update_status(app_id, ApplicationStatus.SHORTLISTED.value)
        logger.info("application_shortlisted", app_id=app_id)
        return self._to_response(row)

    async def reject(self, app_id: str) -> ApplicationResponse:
        """Manually reject an application."""
        existing = await self._app_repo.get_by_id(app_id)
        if not existing:
            raise NotFoundError(f"Application {app_id} not found")
        if existing["status"] in (
            ApplicationStatus.COMPLETED.value,
            ApplicationStatus.REJECTED.value,
        ):
            raise ValidationError(f"Cannot reject application in '{existing['status']}' state")

        row = await self._app_repo.update_status(app_id, ApplicationStatus.REJECTED.value)
        logger.info("application_rejected", app_id=app_id)
        return self._to_response(row)

    async def invite(self, app_id: str) -> ApplicationResponse:
        """Mark a shortlisted application as invited to schedule an interview."""
        existing = await self._app_repo.get_by_id(app_id)
        if not existing:
            raise NotFoundError(f"Application {app_id} not found")
        if existing["status"] not in (
            ApplicationStatus.SHORTLISTED.value,
            ApplicationStatus.INVITED.value,
        ):
            raise ValidationError(
                f"Only shortlisted applications can be invited (current: {existing['status']})"
            )
        row = await self._app_repo.update_status(app_id, ApplicationStatus.INVITED.value)
        logger.info("application_invited", app_id=app_id)
        return self._to_response(row)

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _to_response(row: dict[str, Any]) -> ApplicationResponse:
        return ApplicationResponse(
            id=row["id"],
            job_id=row["job_id"],
            candidate_id=row["candidate_id"],
            status=row["status"],
            eligibility_score=row.get("eligibility_score"),
            resume_url=row.get("resume_url"),
            created_at=row["created_at"],
        )
