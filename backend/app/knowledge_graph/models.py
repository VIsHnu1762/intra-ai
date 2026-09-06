"""Typed domain models and relationship definitions for Intra AI Knowledge Graph."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge_graph.exceptions import EntityValidationError, RelationshipValidationError


# ── Canonical Relationship Types ─────────────────────────────────────────────


class GraphRelationshipType(str, Enum):
    """Explicit relationship vocabulary for Intra AI Knowledge Graph."""

    PARTICIPATED_IN = "PARTICIPATED_IN"
    HAS_PROJECT = "HAS_PROJECT"
    HAS_SKILL = "HAS_SKILL"
    KNOWS_TECHNOLOGY = "KNOWS_TECHNOLOGY"
    HAS_EVIDENCE = "HAS_EVIDENCE"
    HAS_QUESTION = "HAS_QUESTION"
    HAS_ANSWER = "HAS_ANSWER"
    TARGETS_COMPETENCY = "TARGETS_COMPETENCY"
    SUPPORTED_BY = "SUPPORTED_BY"
    SUPPORTS_COMPETENCY = "SUPPORTS_COMPETENCY"
    USES_TECHNOLOGY = "USES_TECHNOLOGY"
    DEMONSTRATES_SKILL = "DEMONSTRATES_SKILL"


# Allowed (SourceLabel, TargetLabel) pairs per relationship type
ALLOWED_RELATIONSHIPS: dict[GraphRelationshipType, list[tuple[str, str]]] = {
    GraphRelationshipType.PARTICIPATED_IN: [("Candidate", "InterviewRound")],
    GraphRelationshipType.HAS_PROJECT: [("Candidate", "Project")],
    GraphRelationshipType.HAS_SKILL: [("Candidate", "Skill")],
    GraphRelationshipType.KNOWS_TECHNOLOGY: [("Candidate", "Technology")],
    GraphRelationshipType.HAS_EVIDENCE: [("Candidate", "Evidence")],
    GraphRelationshipType.HAS_QUESTION: [("InterviewRound", "Question")],
    GraphRelationshipType.HAS_ANSWER: [
        ("InterviewRound", "Answer"),
        ("Question", "Answer"),
    ],
    GraphRelationshipType.TARGETS_COMPETENCY: [("Question", "Competency")],
    GraphRelationshipType.SUPPORTED_BY: [("Answer", "Evidence")],
    GraphRelationshipType.SUPPORTS_COMPETENCY: [("Evidence", "Competency")],
    GraphRelationshipType.USES_TECHNOLOGY: [("Project", "Technology")],
    GraphRelationshipType.DEMONSTRATES_SKILL: [("Project", "Skill")],
}


def validate_relationship_compatibility(
    source_label: str,
    target_label: str,
    relationship_type: GraphRelationshipType | str,
) -> GraphRelationshipType:
    """Validate that source_label and target_label are compatible with relationship_type.

    Raises:
        RelationshipValidationError: If relationship_type is unrecognized or endpoints are incompatible.
    """
    if isinstance(relationship_type, str):
        try:
            rel_type = GraphRelationshipType(relationship_type.strip())
        except ValueError:
            raise RelationshipValidationError(
                f"Unknown relationship type '{relationship_type}'. Allowed: {[r.value for r in GraphRelationshipType]}"
            )
    else:
        rel_type = relationship_type

    allowed_pairs = ALLOWED_RELATIONSHIPS.get(rel_type, [])
    pair = (source_label.strip(), target_label.strip())
    if pair not in allowed_pairs:
        raise RelationshipValidationError(
            f"Relationship '{rel_type.value}' is not permitted between source '{source_label}' and target '{target_label}'. "
            f"Allowed pairs: {allowed_pairs}"
        )

    return rel_type


# ── Core Domain Entity Models ────────────────────────────────────────────────


def _validate_non_empty(v: Any, field_name: str) -> str:
    """Helper validating non-empty string fields."""
    if not isinstance(v, str) or not v.strip():
        raise EntityValidationError(f"{field_name} must be a non-empty string")
    return v.strip()


class Candidate(BaseModel):
    """Candidate root entity in the Knowledge Graph."""

    model_config = ConfigDict(extra="ignore")

    candidate_id: str = Field(..., description="Canonical candidate identifier")
    name: Optional[str] = Field(default=None, description="Candidate full name")
    email: Optional[str] = Field(default=None, description="Candidate email address")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_id")
    @classmethod
    def validate_candidate_id(cls, v: str) -> str:
        return _validate_non_empty(v, "candidate_id")


class InterviewRound(BaseModel):
    """Interview round entity in the Knowledge Graph."""

    model_config = ConfigDict(extra="ignore")

    round_id: str = Field(..., description="Unique round identifier")
    interview_id: str = Field(..., description="Meeting session identifier")
    candidate_id: str = Field(..., description="Associated candidate identifier")
    round_type: str = Field(default="technical", description="Round type (e.g. technical, product)")
    status: str = Field(default="scheduled", description="Status of the round")
    started_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("round_id", "interview_id", "candidate_id")
    @classmethod
    def validate_ids(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


class Question(BaseModel):
    """Question asked to a candidate during an interview turn."""

    model_config = ConfigDict(extra="ignore")

    question_id: str = Field(..., description="Unique question identifier")
    round_id: str = Field(..., description="Round during which question was asked")
    agent_id: str = Field(..., description="Logical agent who asked the question (e.g. alex, jordan)")
    competency: str = Field(default="general", description="Competency targeted by the question")
    question_text: str = Field(..., description="Spoken question text")
    difficulty: str = Field(default="medium", description="Difficulty metadata (e.g. easy, medium, hard, expert)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question_id", "round_id", "agent_id", "question_text")
    @classmethod
    def validate_required_fields(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


class Answer(BaseModel):
    """Candidate's transcribed response to an interview question."""

    model_config = ConfigDict(extra="ignore")

    answer_id: str = Field(..., description="Unique answer identifier")
    question_id: str = Field(..., description="Question that prompted this response")
    candidate_id: str = Field(..., description="Candidate who answered")
    round_id: str = Field(..., description="Round during which answer was given")
    answer_text: str = Field(..., description="Transcribed response text")
    duration_seconds: int = Field(default=0, ge=0, description="Duration of response in seconds")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("answer_id", "question_id", "candidate_id", "round_id", "answer_text")
    @classmethod
    def validate_required_fields(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


class Evidence(BaseModel):
    """Atomic behavioral/technical evidence with strict provenance tracking."""

    model_config = ConfigDict(extra="ignore")

    evidence_id: str = Field(..., description="Unique evidence identifier")
    answer_id: str = Field(..., description="Answer from which evidence was extracted")
    candidate_id: str = Field(..., description="Candidate to whom evidence belongs")
    round_id: str = Field(..., description="Round in which evidence was gathered")
    source_agent_id: str = Field(..., description="Agent who elicited/observed this evidence")
    competency: str = Field(default="general", description="Target competency evaluated")
    signal: str = Field(..., description="Concrete behavioral or technical observation")
    score: Optional[float] = Field(default=None, ge=0.0, le=10.0, description="Turn-level score (0.0 to 10.0)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "evidence_id",
        "answer_id",
        "candidate_id",
        "round_id",
        "source_agent_id",
        "signal",
    )
    @classmethod
    def validate_provenance_and_signal(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


class Competency(BaseModel):
    """Target evaluation competency node in the Knowledge Graph."""

    model_config = ConfigDict(extra="ignore")

    competency_id: str = Field(..., description="Stable competency identifier (e.g. 'system_design')")
    name: str = Field(..., description="Display name of competency")
    category: str = Field(default="technical", description="Competency category (technical, product, behavioral)")
    description: Optional[str] = Field(default=None, description="Detailed competency definition")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("competency_id", "name")
    @classmethod
    def validate_required_fields(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


class Project(BaseModel):
    """Candidate project entity in the Knowledge Graph."""

    model_config = ConfigDict(extra="ignore")

    project_id: str = Field(..., description="Unique project identifier")
    candidate_id: str = Field(..., description="Candidate who completed this project")
    name: str = Field(..., description="Project name or concise subject")
    description: Optional[str] = Field(default=None, description="Project overview or architecture summary")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("project_id", "candidate_id", "name")
    @classmethod
    def validate_required_fields(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


class Technology(BaseModel):
    """Technology or tool entity in the Knowledge Graph."""

    model_config = ConfigDict(extra="ignore")

    technology_id: str = Field(..., description="Stable technology key (e.g. 'redis', 'kafka')")
    name: str = Field(..., description="Canonical display name")
    category: str = Field(default="general", description="Technology category (e.g. database, queue, framework)")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("technology_id", "name")
    @classmethod
    def validate_required_fields(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


class Skill(BaseModel):
    """Candidate skill entity in the Knowledge Graph."""

    model_config = ConfigDict(extra="ignore")

    skill_id: str = Field(..., description="Stable skill key (e.g. 'distributed_caching')")
    name: str = Field(..., description="Canonical skill name")
    category: str = Field(default="general", description="Skill category")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("skill_id", "name")
    @classmethod
    def validate_required_fields(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


# ── Relationship & Graph Query Models ────────────────────────────────────────


class GraphRelationship(BaseModel):
    """Typed relationship between two Knowledge Graph nodes."""

    model_config = ConfigDict(extra="ignore")

    source_id: str = Field(..., description="Identifier of source node")
    source_label: str = Field(..., description="Neo4j label of source node (e.g. 'Candidate')")
    target_id: str = Field(..., description="Identifier of target node")
    target_label: str = Field(..., description="Neo4j label of target node (e.g. 'Project')")
    relationship_type: GraphRelationshipType = Field(..., description="Canonical relationship type")
    properties: dict[str, Any] = Field(default_factory=dict, description="Relationship properties")

    @field_validator("source_id", "source_label", "target_id", "target_label")
    @classmethod
    def validate_non_empty_ids(cls, v: str, info: Any) -> str:
        return _validate_non_empty(v, info.field_name)


class CandidateGraphResponse(BaseModel):
    """Subgraph response for a candidate's neighborhood."""

    candidate_id: str
    depth: int = 1
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
