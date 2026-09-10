from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from app.core.deps import get_supabase
from app.services.workspace_access import current_actor
from app.integrations.resume_storage import content_type_for_extension
from app.candidate_onboarding.models import ApplyProfile, OnboardingStatus, ResumeVersion
from app.candidate_onboarding.service import OnboardingService

router = APIRouter(prefix="/candidate/onboarding", tags=["candidate-onboarding"])


def service(sb: Any = Depends(get_supabase)) -> OnboardingService:
    return OnboardingService(sb)


@router.get("/status", response_model=OnboardingStatus)
async def status(actor=Depends(current_actor), svc=Depends(service)):
    return await svc.status(actor)


@router.get("/resumes", response_model=list[ResumeVersion])
async def versions(actor=Depends(current_actor), svc=Depends(service)):
    svc.require_candidate(actor)
    return await svc.repo.versions(actor.user_id)


@router.post("/resumes", response_model=ResumeVersion, status_code=201)
async def upload(file: UploadFile = File(...), expected_revision: int = Form(..., ge=0),
                 request_id: UUID = Form(...), actor=Depends(current_actor), svc=Depends(service)):
    return await svc.upload(actor, file, expected_revision, str(request_id))


@router.get("/resumes/{version_id}/download")
async def download(version_id: UUID, actor=Depends(current_actor), svc=Depends(service)):
    content, row = await svc.download(actor, str(version_id))
    return Response(content, media_type=content_type_for_extension(row["extension"]), headers={
        "Content-Disposition": f'attachment; filename="resume.{row["extension"]}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/apply/{job_id}", status_code=201)
async def apply(job_id: str, body: ApplyProfile, actor=Depends(current_actor), svc=Depends(service)):
    return await svc.apply(actor, job_id, body)
