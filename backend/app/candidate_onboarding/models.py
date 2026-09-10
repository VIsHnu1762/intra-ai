from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.candidates import ParsedResumeResponse


class ResumeVersion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    version: int
    filename: str
    extension: str
    parse_source: str
    created_at: datetime
    profile: ParsedResumeResponse


class OnboardingStatus(BaseModel):
    needs_onboarding: bool
    source: str
    current: ResumeVersion | None = None
    profile: ParsedResumeResponse | None = None
    revision: int = 0


class ApplyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    years_experience: int = Field(default=0, ge=0, le=80)
    phone: str = Field(default="", max_length=60)
    current_role: str | None = Field(default=None, max_length=160)
    current_company: str | None = Field(default=None, max_length=160)
    expected_salary_min: float | None = Field(default=None, ge=0)
    expected_salary_max: float | None = Field(default=None, ge=0)
    linkedin_url: str | None = Field(default=None, max_length=500)
    resume_version_id: UUID | None = None
