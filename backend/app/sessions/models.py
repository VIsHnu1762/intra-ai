"""Interview Session — in-memory representation of a live AI interview meeting.

Separate from the platform's `scheduled_interviews` Postgres table.
This model owns the live meeting state: channel, agents, status, credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class SessionStatus(StrEnum):
    CREATED = "CREATED"
    READY = "READY"
    STARTING = "STARTING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


def _make_channel_name(interview_id: str) -> str:
    """Canonical deterministic Agora channel name for an interview.

    Format: intra-{interview_id}
    Safe for Agora channel naming rules (no special chars beyond hyphen).
    """
    safe_id = interview_id.strip().lower()
    # Strip existing intra- prefix to prevent double-prefixing
    if safe_id.startswith("intra-"):
        return safe_id
    return f"intra-{safe_id}"


@dataclass
class InterviewSession:
    """Live AI interview meeting session.

    Created when the platform posts an InterviewConfiguration.
    Updated when the candidate starts the session.
    """

    interview_id: str
    channel_name: str                       # intra-{interview_id}
    candidate_id: str
    agent_ids: list[str]                    # ["alex"] | ["jordan"] | ["alex","jordan"]
    current_agent_id: str                   # currently-active agent
    scheduled_start: datetime | None        # UTC; None = immediate
    duration_minutes: int = 60
    status: SessionStatus = SessionStatus.CREATED
    started_agents: dict[str, str] = field(default_factory=dict)   # agent_id → agora_agent_id
    job_title: str | None = None
    company: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: "InterviewConfiguration") -> "InterviewSession":
        """Build an InterviewSession from a platform-supplied InterviewConfiguration."""
        agent_ids = [a.strip().lower() for a in config.agent_ids if a.strip()]
        if not agent_ids:
            raise ValueError("agent_ids must contain at least one valid agent ID")

        return cls(
            interview_id=config.interview_id,
            channel_name=_make_channel_name(config.interview_id),
            candidate_id=config.candidate_id,
            agent_ids=agent_ids,
            current_agent_id=agent_ids[0],
            scheduled_start=config.scheduled_start,
            duration_minutes=config.duration_minutes,
            status=SessionStatus.CREATED,
            job_title=config.job_title,
            company=config.company,
            metadata=dict(config.metadata),
        )

    def is_startable(self, start_window_minutes: int = 10) -> tuple[bool, str]:
        """Check whether the session can be started now.

        Returns (can_start, reason).
        - If scheduled_start is None → always startable.
        - If now >= scheduled_start - window_minutes → startable.
        - Otherwise → not yet open.
        """
        if self.scheduled_start is None:
            return True, "ok"

        now = datetime.now(timezone.utc)
        # Ensure scheduled_start is timezone-aware
        sched = self.scheduled_start
        if sched.tzinfo is None:
            sched = sched.replace(tzinfo=timezone.utc)

        from datetime import timedelta
        open_at = sched - timedelta(minutes=start_window_minutes)

        if now >= open_at:
            return True, "ok"

        wait_seconds = int((open_at - now).total_seconds())
        return False, f"Interview opens in {wait_seconds // 60}m {wait_seconds % 60}s"

    def to_dict(self) -> dict[str, Any]:
        return {
            "interview_id": self.interview_id,
            "channel_name": self.channel_name,
            "candidate_id": self.candidate_id,
            "agent_ids": self.agent_ids,
            "current_agent_id": self.current_agent_id,
            "scheduled_start": self.scheduled_start.isoformat() if self.scheduled_start else None,
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "started_agents": self.started_agents,
            "job_title": self.job_title,
            "company": self.company,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
        }


@dataclass
class InterviewConfiguration:
    """Platform integration boundary contract.

    The platform posts this to POST /api/v1/sessions to create an interview meeting.
    Our side consumes it and drives the full candidate experience.
    """

    interview_id: str
    candidate_id: str
    agent_ids: list[str]                    # ["alex"] | ["jordan"] | ["alex","jordan"]
    scheduled_start: datetime | None = None # UTC ISO8601; None = immediate/on-demand
    duration_minutes: int = 60
    job_title: str | None = None
    company: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
