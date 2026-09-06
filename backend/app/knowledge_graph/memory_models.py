"""Domain models for retrieved Persistent Candidate Memory."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge_graph.exceptions import EntityValidationError


class MemorySourceType(str, Enum):
    """Source taxonomy for candidate memory items."""

    INTERVIEW_EVIDENCE = "INTERVIEW_EVIDENCE"
    RESUME = "RESUME"
    APPLICATION = "APPLICATION"
    OTHER = "OTHER"


class RetrievedEvidence(BaseModel):
    """Evidence item retrieved from candidate Knowledge Graph with strict provenance."""

    model_config = ConfigDict(extra="ignore")

    evidence_id: str
    answer_id: str
    candidate_id: str
    round_id: str
    source_agent_id: str
    competency: str
    signal: str
    score: Optional[float] = None
    timestamp: datetime
    source_type: MemorySourceType = MemorySourceType.INTERVIEW_EVIDENCE
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "evidence_id",
        "answer_id",
        "candidate_id",
        "round_id",
        "source_agent_id",
        "competency",
        "signal",
    )
    @classmethod
    def validate_non_empty(cls, v: str, info: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise EntityValidationError(f"{info.field_name} must be a non-empty string in RetrievedEvidence")
        return v.strip()


class CompetencySummary(BaseModel):
    """Summary of a competency demonstrated across candidate interview history."""

    model_config = ConfigDict(extra="ignore")

    competency_id: str
    name: str
    evidence_count: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    average_score: Optional[float] = None
    assessments: list[str] = Field(default_factory=list)


class ProjectSummary(BaseModel):
    """Summary of candidate project and associated technologies/skills."""

    model_config = ConfigDict(extra="ignore")

    project_id: str
    name: str
    description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class InterviewHistorySummary(BaseModel):
    """Summary of an interview round attended by the candidate."""

    model_config = ConfigDict(extra="ignore")

    round_id: str
    interview_id: str
    round_type: str = "technical"
    status: str = "active"
    questions_count: int = 0
    answers_count: int = 0
    agents_involved: list[str] = Field(default_factory=list)


class PersistentCandidateMemory(BaseModel):
    """Structured, typed representation of persistent candidate memory retrieved from Knowledge Graph.

    Provides a comprehensive, read-only projection of cumulative candidate history across
    all interview turns, agents, and rounds.
    """

    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    filter_applied: dict[str, Any] = Field(default_factory=dict)

    # Core Knowledge Findings
    evidence: list[RetrievedEvidence] = Field(default_factory=list)
    competencies: list[CompetencySummary] = Field(default_factory=list)

    # Candidate Background
    projects: list[ProjectSummary] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)

    # Multi-Round Audit Trail
    interview_rounds: list[InterviewHistorySummary] = Field(default_factory=list)

    # Provenance Rollups
    total_evidence_count: int = 0
    source_agents: list[str] = Field(default_factory=list)
    source_rounds: list[str] = Field(default_factory=list)

    @field_validator("candidate_id")
    @classmethod
    def validate_candidate_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise EntityValidationError("candidate_id must be a non-empty string in PersistentCandidateMemory")
        return v.strip()
