"""Application schemas: create, response, list."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from app.models.enums import ApplicationStatus
from app.schemas.candidates import CandidateResponse
from app.schemas.jobs import JobResponse


class ApplicationCreate(BaseModel):
    """Application form fields. Resume file is handled separately as multipart."""

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str = Field(..., min_length=1, max_length=50)
    current_role: str | None = None
    current_company: str | None = None
    years_experience: int = Field(..., ge=0)
    expected_salary_min: float | None = None
    expected_salary_max: float | None = None
    linkedin_url: str | None = None


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    candidate_id: str
    status: ApplicationStatus
    eligibility_score: float | None = None
    resume_url: str | None = None
    interview_id: str | None = None
    scheduled_at: datetime | None = None
    meeting_mode: str | None = None
    instant_deadline: datetime | None = None
    instant_status: str | None = None
    room_token: str | None = None
    created_at: datetime
    candidate: CandidateResponse | None = None
    job: JobResponse | None = None


class ApplicationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    applications: list[ApplicationResponse]
    total: int
