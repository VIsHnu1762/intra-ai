import asyncio
import hashlib
import io
from pathlib import PurePath
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.integrations.document_text import MAX_UPLOAD_BYTES, extract_document
from app.integrations import resume_storage
from app.integrations.feature_db import DependencyUnavailable
from app.schemas.candidates import ParsedResumeResponse
from app.services.resume_service import ResumeService
from app.candidate_onboarding.models import OnboardingStatus, ResumeVersion
from app.candidate_onboarding.repository import OnboardingRepository


class OnboardingService:
    def __init__(self, sb: Any, *, llm: Any = None):
        self.sb, self.repo, self.llm = sb, OnboardingRepository(sb), llm

    @staticmethod
    def require_candidate(actor: Any) -> None:
        if actor.role != "candidate":
            raise ForbiddenError("Candidate onboarding is available to candidates only")

    async def status(self, actor: Any) -> OnboardingStatus:
        self.require_candidate(actor)
        profile = await self.repo.profile(actor.user_id)
        if profile and profile.get("current_resume_id"):
            row = await self.repo.version(actor.user_id, profile["current_resume_id"])
            if row:
                version = ResumeVersion.model_validate(row)
                return OnboardingStatus(needs_onboarding=False, source="onboarding", current=version,
                                        profile=version.profile, revision=profile["revision"])
        # Existing applicants are not forced to upload again just to log in.
        if actor.candidate_id:
            from app.integrations.feature_db import execute
            rows = await execute(self.sb.table("parsed_resumes").select("skills,experience,education,certifications,projects")
                                 .eq("candidate_id", actor.candidate_id).order("created_at", desc=True).limit(1))
            if rows:
                parsed = ParsedResumeResponse.model_validate(ResumeService._normalize_parsed(rows[0]))
                if any(parsed.model_dump().values()):
                    return OnboardingStatus(needs_onboarding=False, source="existing_application", profile=parsed)
        return OnboardingStatus(needs_onboarding=True, source="missing", revision=(profile or {}).get("revision", 0))

    async def upload(self, actor: Any, file: UploadFile, expected_revision: int, request_id: str) -> ResumeVersion:
        self.require_candidate(actor)
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        filename = PurePath((file.filename or "resume").replace("\\", "/")).name[:180]
        text, extension = await asyncio.to_thread(extract_document, content, filename, file.content_type)
        digest = hashlib.sha256(content).hexdigest()
        # A retried upload returns its original immutable version, even after replacement.
        for old in await self.repo.versions(actor.user_id):
            if old.get("request_id") == request_id:
                if old["content_sha256"] != digest:
                    raise ConflictError("Request ID already belongs to different resume content")
                return ResumeVersion.model_validate(old)
        parsed, source = await ResumeService.parse_profile_text(text, client=self.llm)
        if not any(parsed.model_dump().values()):
            raise ValidationError("No usable profile facts were extracted. Try a clearer resume")
        version_id = str(uuid4())
        key = f"profiles/{actor.user_id}/{version_id}.{extension}"
        try:
            await asyncio.to_thread(resume_storage.upload_to_supabase, self.sb, key, content,
                                    resume_storage.content_type_for_extension(extension))
        except Exception:
            raise DependencyUnavailable("Private resume storage is unavailable; your current resume is unchanged") from None
        data = {"id": version_id, "filename": filename, "extension": extension, "storage_key": key,
                "content_sha256": digest, "request_id": request_id, "profile": parsed.model_dump(),
                "raw_text": text, "parse_source": source}
        try:
            row = await self.repo.save(actor, data, expected_revision)
        except (ConflictError, ForbiddenError, ValidationError):
            # These are definitive rollbacks. On a lost network response the
            # transaction may have committed, so retain the object for recovery.
            try:
                from app.core.config import settings
                await asyncio.to_thread(self.sb.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove, [key])
            except Exception:
                pass
            raise
        return ResumeVersion.model_validate(row)

    async def download(self, actor: Any, version_id: str) -> tuple[bytes, dict]:
        self.require_candidate(actor)
        row = await self.repo.version(actor.user_id, version_id)
        if not row:
            raise NotFoundError("Resume version not found")
        content = await asyncio.to_thread(resume_storage.download_from_supabase, self.sb, row["storage_key"])
        return content, row

    async def apply(self, actor: Any, job_id: str, body: Any) -> Any:
        self.require_candidate(actor)
        status = await self.status(actor)
        if not status.current:
            raise ValidationError("Upload a profile resume before using it for an application")
        content, row = await self.download(actor, str(body.resume_version_id) if body.resume_version_id else status.current.id)
        from app.repositories.application_repo import ApplicationRepo
        from app.repositories.candidate_repo import CandidateRepo
        from app.repositories.job_repo import JobRepo
        from app.services.application_service import ApplicationService
        from starlette.datastructures import Headers
        file = UploadFile(io.BytesIO(content), filename=row["filename"], headers=Headers({
            "content-type": resume_storage.content_type_for_extension(row["extension"])}))
        return await ApplicationService(ApplicationRepo(self.sb), CandidateRepo(self.sb), JobRepo(self.sb)).apply(
            job_id, actor.name, actor.email, body.phone, body.years_experience, file,
            current_role=body.current_role, current_company=body.current_company,
            expected_salary_min=body.expected_salary_min, expected_salary_max=body.expected_salary_max,
            linkedin_url=body.linkedin_url, parsed_profile=row["profile"])
