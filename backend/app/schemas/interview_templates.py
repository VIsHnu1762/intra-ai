"""Reusable interview configuration and immutable scheduling snapshots."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.jobs import InterviewRoundConfigSchema


def checked_rounds(rounds: list[InterviewRoundConfigSchema]) -> list[InterviewRoundConfigSchema]:
    active = [row for row in rounds if row.enabled]
    if not active:
        raise ValueError("Enable at least one interview round")
    if sum(row.duration_minutes for row in active) > 60:
        raise ValueError("Active interview rounds cannot exceed 60 minutes")
    for row in rounds:
        if row.duration_minutes > 60:
            raise ValueError("A round cannot exceed 60 minutes")
        row.focus_areas = list(dict.fromkeys(value.strip() for value in row.focus_areas if value.strip()))
        if len(row.focus_areas) > 24 or any(len(value) > 160 or value.startswith("__intra_") for value in row.focus_areas):
            raise ValueError("Use at most 24 plain-text focus areas, each up to 160 characters")
        if len(row.agent_ids) > 24 or any(len(value) > 64 for value in row.agent_ids):
            raise ValueError("Use at most 24 interviewer agents")
        if row.enabled and (not row.agent_ids or not row.focus_areas):
            raise ValueError("Each active round needs an interviewer and a focus area")
    return rounds


class InterviewTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    rounds: list[InterviewRoundConfigSchema] = Field(min_length=1, max_length=24)

    _validate_rounds = field_validator("rounds")(checked_rounds)


class InterviewTemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    rounds: list[InterviewRoundConfigSchema] | None = Field(default=None, min_length=1, max_length=24)
    expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_patch(self) -> "InterviewTemplateUpdate":
        supplied = self.model_fields_set - {"expected_version"}
        if not supplied or any(getattr(self, field) is None for field in supplied):
            raise ValueError("Provide at least one non-null template field to update")
        if self.rounds is not None:
            checked_rounds(self.rounds)
        return self


class InterviewTemplateResponse(InterviewTemplateCreate):
    id: str
    duration_minutes: int = Field(ge=1, le=60)
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class TemplateSnapshot(BaseModel):
    """Stored on the interview row; never resolved against an edited template."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    template_id: str = Field(min_length=1, max_length=128)
    template_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=160)
    rounds: list[InterviewRoundConfigSchema] = Field(min_length=1, max_length=24)
    duration_minutes: int = Field(ge=1, le=60)

    _validate_rounds = field_validator("rounds")(checked_rounds)

    @model_validator(mode="after")
    def validate_duration(self) -> "TemplateSnapshot":
        if self.duration_minutes != sum(row.duration_minutes for row in self.rounds if row.enabled):
            raise ValueError("Snapshot duration must equal the active round durations")
        return self


class ApplyInterviewTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    job_id: str = Field(min_length=1, max_length=128)
