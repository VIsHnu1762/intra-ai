"""Job posting schemas: create, update, response, list."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import InterviewRoundType, JobStatus


class InterviewRoundConfigSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: InterviewRoundType
    duration_minutes: int = Field(..., gt=0)
    focus_areas: list[str] = Field(default_factory=list)
    enabled: bool = True
    agent_ids: list[str] = Field(default_factory=list)
    # Kept for clients that still send the original single-agent field.
    agent_id: str | None = None

    @model_validator(mode="after")
    def normalize_agents(self) -> "InterviewRoundConfigSchema":
        ids = []
        for value in [*self.agent_ids, self.agent_id]:
            clean = str(value).strip().lower() if value else ""
            if clean and clean not in ids:
                ids.append(clean)
        self.agent_ids = ids
        self.agent_id = ids[0] if ids else None
        return self


class JobCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    department: str = Field(..., min_length=1, max_length=255)
    location: str = Field(..., min_length=1, max_length=255)
    job_type: Literal["remote", "hybrid", "onsite"]
    description: str = Field(..., min_length=1)
    required_skills: list[str] = Field(..., min_length=1)
    experience_min: int = Field(..., ge=0)
    experience_max: int = Field(..., ge=0)
    salary_min: float | None = None
    salary_max: float | None = None
    education: str | None = None
    eligibility_threshold: float = Field(default=60.0, ge=0.0, le=100.0)
    interview_rounds: list[InterviewRoundConfigSchema] = Field(..., min_length=1)


class JobUpdate(BaseModel):
    title: str | None = None
    department: str | None = None
    location: str | None = None
    job_type: Literal["remote", "hybrid", "onsite"] | None = None
    description: str | None = None
    required_skills: list[str] | None = None
    experience_min: int | None = None
    experience_max: int | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    education: str | None = None
    eligibility_threshold: float | None = None
    interview_rounds: list[InterviewRoundConfigSchema] | None = None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    department: str
    location: str
    job_type: str
    description: str
    required_skills: list[str]
    experience_min: int
    experience_max: int
    salary_min: float | None = None
    salary_max: float | None = None
    status: JobStatus
    applications_count: int = 0
    interview_rounds: list[InterviewRoundConfigSchema] = []
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    jobs: list[JobResponse]
    total: int
    page: int
    per_page: int


class JdParseResponse(BaseModel):
    """Structured job-description preview returned before a job is created."""

    title: str = ""
    department: str = ""
    location: str = ""
    job_type: str = "remote"
    description: str = ""
    required_skills: list[str] = []
    experience_min: int | None = None
    experience_max: int | None = None
    education: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    suggested_competencies: list[str] = []
