"""Candidate and parsed resume schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkExperienceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company: str
    role: str
    start_date: str
    end_date: str | None = None
    description: str | None = None


class EducationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    institution: str
    degree: str
    field: str
    year: int | None = None


class ProjectSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str
    technologies: list[str] = []


class ParsedResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skills: list[str] = []
    experience: list[WorkExperienceSchema] = []
    education: list[EducationSchema] = []
    certifications: list[str] = []
    projects: list[ProjectSchema] = []


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    phone: str | None = None
    resume_url: str | None = None
    parsed_resume: ParsedResumeResponse | None = None
    created_at: datetime
