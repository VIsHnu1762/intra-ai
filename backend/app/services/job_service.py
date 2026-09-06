"""Job posting service — CRUD, publish, archive, public listing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import JobStatus
from app.repositories.job_repo import JobRepo
from app.schemas.jobs import (
    JobCreate,
    JobListResponse,
    JobResponse,
    JobUpdate,
)
from app.services.round_agents import decode_round_agents

logger = structlog.stdlib.get_logger("intra_ai.service.job")


class JobService:
    """Business logic for job postings."""

    def __init__(self, job_repo: JobRepo) -> None:
        self._repo = job_repo

    async def create_job(self, data: JobCreate, user_id: str, *, tenant_id: str | None = None) -> JobResponse:
        """Create a new draft job posting."""
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        row = await self._repo.create(
            {
                "id": job_id,
                "title": data.title,
                "department": data.department,
                "location": data.location,
                "job_type": data.job_type,
                "description": data.description,
                "required_skills": data.required_skills,
                "experience_min": data.experience_min,
                "experience_max": data.experience_max,
                "salary_min": data.salary_min,
                "salary_max": data.salary_max,
                "education": data.education,
                "eligibility_threshold": data.eligibility_threshold,
                "status": JobStatus.DRAFT.value,
                "created_by": user_id,
                **({"tenant_id": str(tenant_id)} if tenant_id is not None else {}),
                "created_at": now,
                "updated_at": now,
            }
        )
        await self._repo.replace_rounds(
            job_id,
            [
                {
                    "id": str(uuid.uuid4()),
                    "job_id": job_id,
                    "type": round_config.type.value,
                    "duration_minutes": round_config.duration_minutes,
                    "focus_areas": round_config.focus_areas,
                    "agent_ids": round_config.agent_ids,
                    "enabled": round_config.enabled,
                    "order_index": index,
                }
                for index, round_config in enumerate(data.interview_rounds)
            ],
        )
        row = await self._repo.get_by_id(job_id) or row

        logger.info("job_created", job_id=job_id, title=data.title, user_id=user_id)
        return self._to_response(row)

    async def get_jobs(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> JobListResponse:
        """List all jobs (admin/recruiter) with filters and pagination."""
        rows, total = await self._repo.list(filters=filters, page=page, per_page=per_page)
        return JobListResponse(
            jobs=[self._to_response(r) for r in rows],
            total=total,
            page=page,
            per_page=per_page,
        )

    async def get_job(self, job_id: str) -> JobResponse:
        """Get a single job by ID."""
        row = await self._repo.get_by_id(job_id)
        if not row:
            raise NotFoundError(f"Job {job_id} not found")
        return self._to_response(row)

    async def update_job(self, job_id: str, data: JobUpdate) -> JobResponse:
        """Update a job posting. Only draft jobs can be edited."""
        existing = await self._repo.get_by_id(job_id)
        if not existing:
            raise NotFoundError(f"Job {job_id} not found")

        if existing["status"] not in (JobStatus.DRAFT.value, JobStatus.PUBLISHED.value):
            raise ValidationError("Cannot edit a closed or archived job")

        update_data = data.model_dump(exclude_unset=True, exclude_none=False)
        if not update_data:
            raise ValidationError("No fields to update")

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        rounds = update_data.pop("interview_rounds", None)
        row = await self._repo.update(job_id, update_data)
        if rounds is not None:
            await self._repo.replace_rounds(
                job_id,
                [
                    {
                        "id": str(uuid.uuid4()),
                        "job_id": job_id,
                        "type": round_config["type"].value if hasattr(round_config["type"], "value") else round_config["type"],
                        "duration_minutes": round_config["duration_minutes"],
                        "focus_areas": round_config.get("focus_areas", []),
                        "agent_ids": round_config.get("agent_ids") or ([round_config.get("agent_id")] if round_config.get("agent_id") else []),
                        "enabled": round_config.get("enabled", True),
                        "order_index": index,
                    }
                    for index, round_config in enumerate(rounds)
                ],
            )
            row = await self._repo.get_by_id(job_id) or row
        logger.info("job_updated", job_id=job_id, fields=list(update_data.keys()))
        return self._to_response(row)

    async def publish_job(self, job_id: str) -> JobResponse:
        """Transition a job from draft to published."""
        existing = await self._repo.get_by_id(job_id)
        if not existing:
            raise NotFoundError(f"Job {job_id} not found")
        if existing["status"] != JobStatus.DRAFT.value:
            raise ValidationError("Only draft jobs can be published")

        row = await self._repo.update(
            job_id,
            {"status": JobStatus.PUBLISHED.value, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        logger.info("job_published", job_id=job_id)
        return self._to_response(row)

    async def archive_job(self, job_id: str) -> JobResponse:
        """Archive a job posting."""
        existing = await self._repo.get_by_id(job_id)
        if not existing:
            raise NotFoundError(f"Job {job_id} not found")

        row = await self._repo.update(
            job_id,
            {"status": JobStatus.ARCHIVED.value, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
        logger.info("job_archived", job_id=job_id)
        return self._to_response(row)

    async def get_public_jobs(
        self,
        filters: dict[str, Any] | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> JobListResponse:
        """List published jobs only (public facing)."""
        combined = {**(filters or {}), "status": JobStatus.PUBLISHED.value}
        rows, total = await self._repo.list(filters=combined, page=page, per_page=per_page)
        return JobListResponse(
            jobs=[self._to_response(r) for r in rows],
            total=total,
            page=page,
            per_page=per_page,
        )

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _to_response(row: dict[str, Any]) -> JobResponse:
        row = dict(row)
        rounds = row.pop("job_rounds", None) or []
        rounds = sorted(rounds, key=lambda item: item.get("order_index", 0))
        normalized_rounds = []
        for round_row in rounds:
            agent_ids, focus_areas = decode_round_agents(round_row)
            normalized_rounds.append({
                **round_row,
                "focus_areas": focus_areas,
                "agent_ids": agent_ids,
                "agent_id": agent_ids[0] if agent_ids else None,
            })
        return JobResponse(
            id=row["id"],
            title=row["title"],
            department=row["department"],
            location=row["location"],
            job_type=row["job_type"],
            description=row["description"],
            required_skills=row.get("required_skills", []),
            experience_min=row["experience_min"],
            experience_max=row["experience_max"],
            salary_min=row.get("salary_min"),
            salary_max=row.get("salary_max"),
            status=row["status"],
            applications_count=row.get("applications_count", 0),
            interview_rounds=normalized_rounds,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
