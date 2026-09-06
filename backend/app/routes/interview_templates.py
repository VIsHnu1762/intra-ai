"""Authenticated HR interview template management."""

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, get_supabase
from app.schemas.interview_templates import (
    ApplyInterviewTemplateRequest, InterviewTemplateCreate, InterviewTemplateResponse, InterviewTemplateUpdate,
)
from app.schemas.jobs import JobResponse
from app.services.interview_template_service import InterviewTemplateService
from app.voice.authorization import Actor, identity, require_recruiter

router = APIRouter(prefix="/interview-templates", tags=["interview-templates"])


async def _actor(user: dict[str, Any] = Depends(get_current_user), supabase: Any = Depends(get_supabase)) -> Actor:
    actor = await identity(user, supabase)
    require_recruiter(actor)
    return actor


def _service(supabase: Any = Depends(get_supabase)) -> InterviewTemplateService:
    return InterviewTemplateService(supabase)


@router.get("", response_model=list[InterviewTemplateResponse])
async def list_templates(include_archived: bool = Query(False), actor: Actor = Depends(_actor), service: InterviewTemplateService = Depends(_service)):
    return await service.list(actor, include_archived=include_archived)


@router.post("", response_model=InterviewTemplateResponse, status_code=201)
async def create_template(data: InterviewTemplateCreate, actor: Actor = Depends(_actor), service: InterviewTemplateService = Depends(_service)):
    return await service.create(actor, data)


@router.get("/{template_id}", response_model=InterviewTemplateResponse)
async def get_template(template_id: str, actor: Actor = Depends(_actor), service: InterviewTemplateService = Depends(_service)):
    return await service.get(actor, template_id)


@router.patch("/{template_id}", response_model=InterviewTemplateResponse)
async def update_template(template_id: str, data: InterviewTemplateUpdate, actor: Actor = Depends(_actor), service: InterviewTemplateService = Depends(_service)):
    return await service.update(actor, template_id, data)


@router.post("/{template_id}/archive", response_model=InterviewTemplateResponse)
async def archive_template(template_id: str, actor: Actor = Depends(_actor), service: InterviewTemplateService = Depends(_service)):
    return await service.archive(actor, template_id)


@router.post("/{template_id}/apply-to-job", response_model=JobResponse)
async def apply_to_job(template_id: str, data: ApplyInterviewTemplateRequest, actor: Actor = Depends(_actor), service: InterviewTemplateService = Depends(_service)):
    return await service.apply_to_job(actor, template_id, data.job_id)
