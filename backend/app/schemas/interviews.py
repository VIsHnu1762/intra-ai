"""Interview scheduling and question schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DifficultyLevel, InterviewRoundType
from app.schemas.candidates import CandidateResponse
from app.schemas.jobs import JobResponse


class InterviewSlotCreate(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    start_time: str = Field(..., description="Start time in HH:MM format")
    end_time: str = Field(..., description="End time in HH:MM format")


class InterviewSlotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    date: str
    start_time: str
    end_time: str
    is_booked: bool = False


class ScheduleInterviewRequest(BaseModel):
    slot_id: str
    template_id: str | None = Field(default=None, min_length=1, max_length=128)


class InstantInterviewRequest(BaseModel):
    template_id: str | None = Field(default=None, min_length=1, max_length=128)


class ScheduledInterviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str
    scheduled_at: datetime
    duration_minutes: int
    room_token: str | None = None
    status: str
    meeting_mode: str = "scheduled"
    response_deadline: datetime | None = None
    candidate: CandidateResponse | None = None
    job: JobResponse | None = None


class GenerateQuestionsRequest(BaseModel):
    round_type: InterviewRoundType


class InterviewQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    interview_id: str
    round_type: InterviewRoundType
    text: str
    topic: str
    difficulty: DifficultyLevel
    order: int
