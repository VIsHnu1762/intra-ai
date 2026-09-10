import asyncio
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, UploadFile
from app.core.deps import get_supabase
from app.core.exceptions import ValidationError
from app.integrations.document_text import MAX_UPLOAD_BYTES, extract_document
from app.integrations.feature_db import tenant_key
from app.services.workspace_access import recruiter_actor, current_actor
from app.voice.authorization import require_interview, require_job
from app.company_knowledge.models import DocumentInput, ArchiveInput, RetrievalInput, GroundedContext, DocumentView, VersionView
from app.company_knowledge.service import CompanyKnowledgeService

router = APIRouter(prefix="/company-knowledge", tags=["company-knowledge"])


def service(sb: Any = Depends(get_supabase)): return CompanyKnowledgeService(sb)


@router.get("/documents", response_model=list[DocumentView])
async def documents(actor=Depends(recruiter_actor), svc=Depends(service)):
    return await svc.repo.documents(actor)


@router.post("/documents", response_model=VersionView, status_code=201)
async def create(body: DocumentInput, actor=Depends(recruiter_actor), svc=Depends(service)):
    return await svc.save(actor, body)


@router.post("/documents/upload", response_model=VersionView, status_code=201)
async def upload(file: UploadFile = File(...), title: str = Form(..., min_length=1, max_length=160),
                 policy_key: str = Form(...), request_id: UUID = Form(...),
                 effective_from: datetime = Form(...), audience: Literal["candidate", "internal"] = Form("internal"),
                 actor=Depends(recruiter_actor), svc=Depends(service)):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    text, _ = await asyncio.to_thread(extract_document, content, file.filename or "", file.content_type)
    try:
        body = DocumentInput(title=title, policy_key=policy_key, request_id=request_id, content=text,
                             effective_from=effective_from, audience=audience)
    except ValueError:
        raise ValidationError("Invalid document metadata; dates require a timezone") from None
    return await svc.save(actor, body)


@router.get("/documents/{document_id}/versions", response_model=list[VersionView])
async def versions(document_id: UUID, actor=Depends(recruiter_actor), svc=Depends(service)):
    await svc.require_document(actor, str(document_id))
    return await svc.repo.versions(str(document_id))


@router.post("/documents/{document_id}/versions", response_model=VersionView, status_code=201)
async def new_version(document_id: UUID, body: DocumentInput, actor=Depends(recruiter_actor), svc=Depends(service)):
    return await svc.save(actor, body, str(document_id))


@router.patch("/documents/{document_id}/archive", response_model=DocumentView)
async def archive(document_id: UUID, body: ArchiveInput, actor=Depends(recruiter_actor), svc=Depends(service)):
    return await svc.archive(actor, str(document_id), body)


@router.post("/retrieve", response_model=GroundedContext)
async def retrieve(body: RetrievalInput, actor=Depends(recruiter_actor), svc=Depends(service)):
    return await svc.retrieve(actor.user_id, tenant_key(actor), body.query, candidate_visible=False, effective_at=body.effective_at)


@router.post("/interviews/{interview_id}/context", response_model=GroundedContext)
async def interview_context(interview_id: str, body: RetrievalInput, actor=Depends(current_actor),
                            sb=Depends(get_supabase), svc=Depends(service)):
    interview = await require_interview(actor, interview_id, sb)
    job = await require_job(actor, interview["job_id"], sb)
    owner = str(job["created_by"])
    scope = str(job.get("tenant_id") or ("user:" + owner))
    return await svc.retrieve(owner, scope, body.query, candidate_visible=True, effective_at=body.effective_at)
