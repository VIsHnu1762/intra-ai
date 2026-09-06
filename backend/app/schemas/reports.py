"""Report and proctoring schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProctoringEventType, Recommendation
from app.schemas.evaluation import RoundAssessmentResponse


class SalaryRecommendationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min: float
    max: float
    justification: str


class ProctoringEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    type: ProctoringEventType
    timestamp: datetime
    details: str | None = None


class ProctoringReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    face_presence_pct: float = Field(..., ge=0.0, le=100.0)
    tab_switches: int = Field(..., ge=0)
    integrity_score: float = Field(..., ge=0.0, le=100.0)
    events: list[ProctoringEventSchema] = []


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    interview_id: str
    round_assessments: list[RoundAssessmentResponse] = []
    overall_score: float = Field(..., ge=0.0, le=100.0)
    recommendation: Recommendation
    strengths: list[str] = []
    improvements: list[str] = []
    salary_recommendation: SalaryRecommendationSchema | None = None
    pdf_url: str | None = None
    proctoring_summary: ProctoringReport | None = None
    created_at: datetime
    candidate: dict | None = None
    job: dict | None = None
    candidate_rating: float | None = Field(default=None, ge=1, le=5)
    candidate_feedback: list[str] | None = None
    analysis: dict[str, Any] | None = None


class ReportStatusResponse(BaseModel):
    interview_id: str
    status: Literal["not_completed", "not_started", "generating", "ready", "failed"]
    report_id: str | None = None
    error_code: str | None = None
    message: str | None = None
    retryable: bool = False


class CandidatePerformanceResponse(BaseModel):
    """The complete candidate-visible projection: no internal report fields."""
    interview_id: str
    status: Literal["not_completed", "not_started", "generating", "ready", "failed"]
    rating: float | None = Field(default=None, ge=1, le=5)
    feedback: list[str] | None = None
    created_at: datetime | None = None
    message: str | None = None


class ReportListResponse(BaseModel):
    reports: list[ReportResponse]
    total: int
