"""Normalized transcript models and schemas for Intra AI."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class SpeakerType(str, Enum):
    """Normalized speaker roles in an interview session."""

    CANDIDATE = "candidate"
    AGENT = "agent"
    SYSTEM = "system"


class TranscriptEventType(str, Enum):
    """Lifecycle and transcript event types."""

    TRANSCRIPT = "transcript"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    STATUS = "status"


class TranscriptEvent(BaseModel):
    """Canonical representation of an individual transcript turn or dialogue event."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique event identifier or turn ID")
    interview_id: str = Field(..., description="Canonical interview ID")
    channel: str = Field(..., description="Agora RTC/RTM channel name")
    agent_id: Optional[str] = Field(default=None, description="Logical agent ID (e.g. alex, jordan)")
    speaker: SpeakerType = Field(..., description="Speaker attribution (candidate or agent)")
    speaker_uid: Optional[str] = Field(default=None, description="Agora RTC UID of the speaker")
    text: str = Field(..., description="Transcript text content")
    timestamp: float = Field(..., description="Authoritative Unix timestamp (milliseconds)")
    sequence: Optional[int] = Field(default=None, description="Monotonic sequence number within the session")
    event_type: TranscriptEventType = Field(default=TranscriptEventType.TRANSCRIPT, description="Event type")
    is_final: bool = Field(default=True, description="Whether this is a final transcript turn (vs interim update)")
    source: str = Field(default="agora_server", description="Origin of the event (e.g. agora_webhook_103, rtm)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Safe event metadata (latencies, turn_id, etc.)")


class TranscriptEventCreate(BaseModel):
    """Input payload for direct or normalized transcript ingestion."""

    id: Optional[str] = None
    interview_id: Optional[str] = None
    channel: Optional[str] = None
    agent_id: Optional[str] = None
    speaker: Optional[SpeakerType] = None
    role: Optional[str] = None
    speaker_uid: Optional[str] = None
    text: str
    timestamp: Optional[float] = None
    sequence: Optional[int] = None
    event_type: Optional[TranscriptEventType] = TranscriptEventType.TRANSCRIPT
    is_final: bool = True
    source: str = "direct_ingestion"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgoraWebhookPayload(BaseModel):
    """Envelope for Agora Notification Webhook events (e.g. 101, 102, 103, 112)."""

    notice_id: Optional[str] = None
    event_id: Optional[int | str] = None
    event_type: Optional[int | str] = None
    notify_ts: Optional[int | float] = None
    payload: Optional[dict[str, Any]] = None


class TranscriptListResponse(BaseModel):
    """Ordered transcript response for an interview session."""

    model_config = ConfigDict(from_attributes=True)

    interview_id: str
    channel: str
    agent_id: Optional[str] = None
    total_events: int
    events: list[TranscriptEvent]
