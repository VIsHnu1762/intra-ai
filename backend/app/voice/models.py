"""Private session records and minimal authenticated browser contracts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DashboardContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str | None = Field(default=None, min_length=1, max_length=128)
    candidate_id: str | None = Field(default=None, min_length=1, max_length=128)
    application_id: str | None = Field(default=None, min_length=1, max_length=128)
    interview_id: str | None = Field(default=None, min_length=1, max_length=128)


class PracticeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_role: str = Field(default="", max_length=200)
    experience_level: Literal["intern", "junior", "mid", "senior"] = "intern"


class StartVoiceSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: DashboardContext = Field(default_factory=DashboardContext)
    practice: PracticeOptions | None = None
    force: bool = False


class ConfirmVoiceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_id: str = Field(min_length=1, max_length=128)
    approved: bool


class CallVoiceTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = Field(min_length=1, max_length=80)
    args: dict[str, Any] = Field(default_factory=dict)


class VoiceSession(BaseModel):
    """Server-only record. Contains no Agora/callback credentials or RTC tokens."""
    session_id: str
    user_id: str
    role: str
    tenant_id: str | None = None
    persona: Literal["taylor", "morgan"]
    agent_type: Literal["TAYLOR_TRAINING", "MORGAN_HR"]
    project_name: Literal["training_hr"] = "training_hr"
    channel_name: str
    rtc_uid: int
    agent_rtc_uid: str
    cloud_agent_id: str | None = None
    status: str = "CONNECTING"
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    expires_at: datetime
    heartbeat_at: datetime = Field(default_factory=utc_now)
    dashboard_context: DashboardContext = Field(default_factory=DashboardContext)
    practice: PracticeOptions | None = None
    practice_feedback: dict[str, Any] | None = None
    # Private, single-attempt checkpoint. Never include reviewed answer text or
    # the native request marker in browser session/status responses.
    feedback_attempt_id: str | None = None
    feedback_checkpoint: dict[str, Any] | None = None
    feedback_deadline_at: datetime | None = None
    pending_action: dict[str, Any] | None = None
    last_tool_result: dict[str, Any] | None = None
    transcript: list[dict[str, str]] = Field(default_factory=list)
    error_code: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id, "agent_type": self.agent_type,
            "agent_name": self.persona.title(), "status": self.status,
            "expires_at": self.expires_at.isoformat(),
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "pending_action": self.pending_action, "last_tool_result": self.last_tool_result,
            "transcript": self.transcript[-80:], "error_code": self.error_code,
            "practice": self.practice.model_dump() if self.practice else None,
            "practice_feedback": self.practice_feedback,
        }
