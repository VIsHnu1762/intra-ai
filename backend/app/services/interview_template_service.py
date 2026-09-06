"""Recruiter-managed reusable rounds; snapshots belong to scheduled interviews."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agents.registry import agent_registry
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.repositories.interview_template_repo import InterviewTemplateRepo
from app.repositories.job_repo import JobRepo
from app.schemas.interview_templates import (
    InterviewTemplateCreate, InterviewTemplateResponse, InterviewTemplateUpdate, TemplateSnapshot,
)
from app.schemas.jobs import JobResponse, JobUpdate
from app.services.job_service import JobService
from app.voice.authorization import Actor, require_job, require_recruiter


class InterviewTemplateService:
    def __init__(self, supabase: Any):
        self._sb = supabase
        self._repo = InterviewTemplateRepo(supabase)

    @staticmethod
    def _response(row: dict[str, Any]) -> InterviewTemplateResponse:
        # Scope/creator fields are server-owned and are not accepted or exposed.
        return InterviewTemplateResponse.model_validate({
            field: row.get(field) for field in InterviewTemplateResponse.model_fields
        })

    @staticmethod
    def _check_agents(data: InterviewTemplateCreate) -> None:
        unknown = sorted({agent for row in data.rounds for agent in row.agent_ids if not agent_registry.has_agent(agent)})
        if unknown:
            raise ValidationError("Select registered interviewer agents", details={"unknown_agent_ids": unknown})

    async def list(self, actor: Actor, *, include_archived: bool = False) -> list[InterviewTemplateResponse]:
        require_recruiter(actor)
        return [self._response(row) for row in await self._repo.list(actor, include_archived=include_archived)]

    async def get(self, actor: Actor, template_id: str) -> InterviewTemplateResponse:
        require_recruiter(actor)
        row = await self._repo.get(actor, template_id)
        if not row:
            raise NotFoundError("Interview template not found")
        return self._response(row)

    async def create(self, actor: Actor, data: InterviewTemplateCreate) -> InterviewTemplateResponse:
        require_recruiter(actor)
        self._check_agents(data)
        now = datetime.now(timezone.utc).isoformat()
        row = await self._repo.create({
            **data.model_dump(mode="json"), "id": str(uuid4()), "created_by": actor.user_id,
            "tenant_id": str(actor.tenant_id) if actor.tenant_id is not None else None,
            "duration_minutes": sum(round.duration_minutes for round in data.rounds if round.enabled),
            "version": 1, "created_at": now, "updated_at": now, "archived_at": None,
        })
        return self._response(row)

    async def update(self, actor: Actor, template_id: str, data: InterviewTemplateUpdate) -> InterviewTemplateResponse:
        existing = await self.get(actor, template_id)
        if existing.archived_at:
            raise ConflictError("Archived templates cannot be edited; duplicate one to reuse it")
        if data.expected_version is not None and data.expected_version != existing.version:
            raise ConflictError("This template was edited elsewhere. Reload it before saving")
        changes = data.model_dump(mode="json", exclude_unset=True, exclude={"expected_version"})
        merged = InterviewTemplateCreate.model_validate({
            **existing.model_dump(include={"name", "description", "rounds"}, mode="json"), **changes,
        })
        self._check_agents(merged)
        updated = await self._repo.update(actor, template_id, existing.version, {
            **merged.model_dump(mode="json"),
            "duration_minutes": sum(round.duration_minutes for round in merged.rounds if round.enabled),
            "version": existing.version + 1, "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not updated:
            raise ConflictError("This template changed while saving. Reload it before saving")
        return self._response(updated)

    async def archive(self, actor: Actor, template_id: str) -> InterviewTemplateResponse:
        existing = await self.get(actor, template_id)
        if existing.archived_at:
            return existing
        now = datetime.now(timezone.utc).isoformat()
        updated = await self._repo.update(actor, template_id, existing.version, {
            "archived_at": now, "updated_at": now, "version": existing.version + 1,
        })
        if not updated:
            raise ConflictError("This template changed while archiving. Reload it and try again")
        return self._response(updated)

    async def require_snapshot(self, actor: Actor, template_id: str) -> dict[str, Any]:
        """Authorize and copy now; callers separately authorize the target application."""
        template = await self.get(actor, template_id)
        if template.archived_at:
            raise ConflictError("Choose an active interview template")
        self._check_agents(template)
        return TemplateSnapshot(
            template_id=template.id, template_version=template.version, name=template.name,
            rounds=template.rounds, duration_minutes=template.duration_minutes,
        ).model_dump(mode="json")

    async def apply_to_job(self, actor: Actor, template_id: str, job_id: str) -> JobResponse:
        require_recruiter(actor)
        await require_job(actor, job_id, self._sb)
        snapshot = await self.require_snapshot(actor, template_id)
        return await JobService(JobRepo(self._sb)).update_job(
            job_id, JobUpdate(interview_rounds=snapshot["rounds"]),
        )
