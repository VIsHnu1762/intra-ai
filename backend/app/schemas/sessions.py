"""Pydantic schemas for the Interview Session API (candidate-facing + platform contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InterviewConfigurationRequest(BaseModel):
    """Platform integration boundary contract — posted by the platform to create an interview meeting."""

    model_config = ConfigDict(extra="ignore")

    interview_id: str = Field(..., description="Opaque interview identifier (becomes candidate link token).")
    candidate_id: str = Field(..., description="Candidate identifier.")
    agent_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of agent IDs. e.g. ['alex'] | ['jordan'] | ['alex','jordan']",
    )
    scheduled_start: datetime | None = Field(
        default=None,
        description="Scheduled start time (UTC ISO8601). Null = on-demand / immediate.",
    )
    duration_minutes: int = Field(default=60, ge=5, le=480)
    job_title: str | None = Field(default=None, description="Role title shown in candidate lobby.")
    company: str | None = Field(default=None, description="Company shown in candidate lobby.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_ids")
    @classmethod
    def validate_agent_ids(cls, v: list[str]) -> list[str]:
        cleaned = [a.strip().lower() for a in v if a.strip()]
        if not cleaned:
            raise ValueError("agent_ids must contain at least one non-empty agent ID")
        return cleaned

    @field_validator("interview_id")
    @classmethod
    def validate_interview_id(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("interview_id must be non-empty")
        return stripped


class AgentInfoResponse(BaseModel):
    """Lightweight agent info returned to the candidate UI."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str
    name: str
    role: str
    description: str = ""
    focal_competencies: list[str] = Field(default_factory=list)
    agora_rtc_uid: int | None = Field(
        default=None,
        description="The physical Agora Agent Studio remote RTC UID.",
    )


class SessionInfoResponse(BaseModel):
    """Public interview session info returned to the candidate lobby (no auth required)."""

    model_config = ConfigDict(extra="ignore")

    interview_id: str
    channel_name: str
    status: str
    agent_ids: list[str]
    current_agent_id: str
    selected_agents: list[AgentInfoResponse]
    scheduled_start: datetime | None = None
    duration_minutes: int
    job_title: str | None = None
    company: str | None = None

    # Safe live lifecycle signals for room polling; excludes JD/CV and tokens.
    completed: bool = False
    pending_voice_action: str | None = None
    voice_lifecycle_status: str | None = None
    report_status: str | None = None


class SessionStartResponse(BaseModel):
    """Returned to the candidate after a successful POST /session/start.

    Contains everything the frontend needs to join the Agora channel.
    """

    model_config = ConfigDict(extra="ignore")

    interview_id: str
    channel_name: str
    agora_app_id: str
    agora_token: str
    agora_uid: int
    rtm_user_id: str
    selected_agents: list[AgentInfoResponse]
    current_agent_id: str
    agent_ids: list[str]
    session_status: str
    duration_minutes: int
    job_title: str | None = None
    company: str | None = None
    scheduled_start: datetime | None = None
    expires_in: int = 3600
    agent_start_warnings: list[str] = Field(default_factory=list)


class SessionStopResponse(BaseModel):
    """Returned after a successful POST /session/stop."""

    model_config = ConfigDict(extra="ignore")

    interview_id: str
    channel_name: str
    status: str
    stopped_agents: list[str]
    report_id: str | None = None
    report_status: str = "pending"
    report_error: str | None = None
