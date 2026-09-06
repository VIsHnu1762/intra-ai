"""Evaluation and assessment schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import InterviewRoundType


class AnswerCreate(BaseModel):
    question_id: str
    transcript: str = Field(..., min_length=1)
    duration_seconds: int = Field(..., gt=0)


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    answer_id: str
    relevance: float = Field(..., ge=0.0, le=10.0)
    depth: float = Field(..., ge=0.0, le=10.0)
    accuracy: float = Field(..., ge=0.0, le=10.0)
    communication: float = Field(..., ge=0.0, le=10.0)
    confidence: float = Field(..., ge=0.0, le=10.0)
    overall: float = Field(..., ge=0.0, le=10.0)
    feedback: str


class RoundAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    round_type: str
    score: float = Field(..., ge=0.0, le=100.0)
    round_id: str | None = None
    round_name: str | None = None
    agent_ids: list[str] = Field(default_factory=list)
    configured_agent_ids: list[str] = Field(default_factory=list)
    identity_resolution: str | None = None
    observations: list[str] = []
    strengths: list[str] = []
    weaknesses: list[str] = []


class SkillAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill: str
    score: float = Field(..., ge=0.0, le=100.0)
    level: str
