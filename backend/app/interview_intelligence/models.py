"""Canonical models for Intra AI M1 Interview Intelligence."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.models import AgentProfile
from app.interview_context.models import EvidenceItem, InterviewAIContext


class CompetencyFinding(BaseModel):
    """Structured assessment of a specific competency demonstrated in a candidate answer."""

    model_config = ConfigDict(extra="ignore")

    competency_id: str = Field(..., description="Target competency identifier (e.g. 'system_design').")
    assessment: str = Field(..., description="Concise assessment of demonstrated capability or gap.")
    confidence: float = Field(..., description="Confidence level in this finding (normalized 0.0–1.0).")
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="List of EvidenceItem IDs directly supporting this finding.",
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("competency_id", "assessment")
    @classmethod
    def validate_non_empty(cls, v: str, info: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return v.strip()


class AnswerAnalysis(BaseModel):
    """Authoritative output contract produced by M1 Interview Intelligence.

    Evaluates answer quality, grounded evidence, vagueness, contradictions, and
    competency demonstration. Does NOT decide next actions or routing.
    """

    model_config = ConfigDict(extra="ignore")

    answer_id: str = Field(..., description="Unique identifier for the analyzed answer.")
    overall_performance: float = Field(
        ...,
        description="Normalized performance score for this turn (0.0–1.0).",
    )
    confidence: float = Field(
        ...,
        description="M1's confidence in its own evaluation (0.0–1.0).",
    )
    vague: bool = Field(
        ...,
        description="Indicates whether the answer lacks specificity, examples, or technical depth.",
    )
    vague_reason: str | None = Field(
        default=None,
        description="Concise explanation justifying why the answer was marked vague.",
    )
    contradiction_detected: bool = Field(
        ...,
        description="Indicates whether a factual or logical contradiction was identified.",
    )
    contradiction_details: str | None = Field(
        default=None,
        description="Structured explanation of the detected discrepancy or contradiction.",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Specific information gaps needed to adequately evaluate the competency.",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="List of grounded EvidenceItems extracted directly from the candidate answer.",
    )
    competency_findings: list[CompetencyFinding] = Field(
        default_factory=list,
        description="Specific findings linked to focal competencies.",
    )
    recommended_follow_up: str | None = Field(
        default=None,
        description="Optional recommended follow-up question or probe (informational recommendation only).",
    )

    @field_validator("overall_performance", "confidence")
    @classmethod
    def validate_normalized_score(cls, v: float, info: Any) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"{info.field_name} must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("answer_id")
    @classmethod
    def validate_answer_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("answer_id must be a non-empty string")
        return v.strip()

    @model_validator(mode="after")
    def validate_evidence_integrity(self) -> "AnswerAnalysis":
        """Verify that all evidence_ids referenced in competency_findings exist in self.evidence."""
        existing_evidence_ids = {e.id for e in self.evidence}
        for finding in self.competency_findings:
            for eid in finding.evidence_ids:
                if eid not in existing_evidence_ids:
                    raise ValueError(
                        f"CompetencyFinding for '{finding.competency_id}' references unknown evidence_id '{eid}'. "
                        f"Available evidence IDs: {sorted(list(existing_evidence_ids))}"
                    )
        return self


class InterviewAnswerInput(BaseModel):
    """Typed input payload provided to M1 Interview Intelligence for answer analysis."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    answer_id: str = Field(..., description="Unique identifier for the answer being analyzed.")
    question_text: str = Field(..., description="Text of the question asked to the candidate.")
    answer_text: str = Field(..., description="Candidate's raw or transcribed response text.")
    context: InterviewAIContext = Field(..., description="Current short-term interview orchestration state.")
    agent_profile: AgentProfile = Field(..., description="Profile of the interviewer agent conducting the turn.")
    job_description: str | None = Field(default=None, description="Optional job context.")
    candidate_profile: dict[str, Any] | None = Field(default=None, description="Optional candidate profile summary.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary evaluation metadata.")

    @field_validator("answer_id", "question_text", "answer_text")
    @classmethod
    def validate_non_empty_fields(cls, v: str, info: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return v.strip()
