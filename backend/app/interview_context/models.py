"""Authoritative Short-term Interview AI Context for Intra AI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.registry import agent_registry
from app.core.exceptions import AgentNotFoundError
from app.models.enums import DifficultyLevel


class EvidenceItem(BaseModel):
    """Typed evidence captured from candidate answers during an interview turn."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    competency: str = Field(default="general", description="Competency demonstrated or evaluated.")
    signal: str = Field(..., description="Observed behavioral or technical signal/evidence.")
    score: float | None = Field(default=None, ge=0.0, le=10.0, description="Provisional evidence score out of 10; null means unscored.")
    source_agent_id: str | None = Field(default=None, description="Agent who elicited or observed this evidence.")
    round_id: str | None = Field(default=None, description="Round during which evidence was gathered.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContradictionItem(BaseModel):
    """Typed contradiction or factual discrepancy detected during the interview."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str = Field(default="", description="Original resume claim or earlier statement.")
    contradiction: str = Field(..., description="Contradicting statement or observed gap.")
    severity: str = Field(default="medium", description="Severity level ('low', 'medium', 'high').")
    detected_by_agent_id: str | None = Field(default=None, description="Agent who noted the contradiction.")
    round_id: str | None = Field(default=None, description="Round where contradiction occurred.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuestionHistoryItem(BaseModel):
    """Represents a structured history of questions asked to prevent repetition."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = Field(..., description="Agent who asked the question.")
    competency: str = Field(default="general", description="Competency targeted by the question.")
    question_text: str = Field(..., description="The actual text of the question asked.")
    difficulty: DifficultyLevel = Field(..., description="Difficulty of the question asked.")
    exploration_status: str = Field(
        default="FOLLOW_UP_REQUIRED",
        description="Status of exploration: SUFFICIENT, ASSESSED_INSUFFICIENT, PARTIAL, or FOLLOW_UP_REQUIRED."
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class InterviewAIContext(BaseModel):
    """Authoritative short-term state object for Intra AI interview orchestration.

    Tracks active interview turn state including:
    - current interview, candidate, round, and active agent
    - current difficulty level (metadata)
    - evaluated competencies and missing competencies
    - accumulated evidence items
    - open questions and information gaps
    - detected contradictions
    - structured question history
    """

    model_config = ConfigDict(extra="ignore")

    interview_id: str = Field(..., description="Unique non-empty interview session identifier.")
    candidate_id: str = Field(..., description="Unique non-empty candidate identifier.")
    current_round_id: str = Field(..., description="Unique non-empty active interview round identifier.")
    current_agent_id: str = Field(..., description="Logical agent ID of currently active interviewer (e.g. 'alex').")
    difficulty: DifficultyLevel = Field(
        default=DifficultyLevel.MEDIUM,
        description="Current interview difficulty metadata.",
    )
    evaluated_competencies: list[str] = Field(
        default_factory=list,
        description="Deduplicated list of competencies evaluated so far in this session.",
    )
    accumulated_evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Evidence items accumulated during current session.",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Deduplicated list of unresolved questions or information gaps.",
    )
    question_history: list[QuestionHistoryItem] = Field(
        default_factory=list,
        description="Structured history of questions asked across all agents.",
    )
    missing_competencies: list[str] = Field(
        default_factory=list,
        description="Deduplicated list of target competencies still requiring evaluation.",
    )
    detected_contradictions: list[ContradictionItem] = Field(
        default_factory=list,
        description="Contradictions noted during current session.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary orchestration metadata.",
    )

    # ── Identity Validators ─────────────────────────────────────────────

    @field_validator("interview_id", "candidate_id", "current_round_id", mode="before")
    @classmethod
    def validate_non_empty_string(cls, v: Any, info: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return v.strip()

    @field_validator("current_agent_id", mode="before")
    @classmethod
    def validate_and_normalize_agent_id(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("current_agent_id must be a non-empty string")
        return v.strip().lower()

    # ── Agent Switching & Validation ────────────────────────────────────

    def switch_agent(self, new_agent_id: str, validate_registry: bool = False) -> None:
        """Switch current active interviewer agent (e.g. 'alex' -> 'jordan').

        Leaves interview_id, candidate_id, and current_round_id unchanged.
        """
        if not isinstance(new_agent_id, str) or not new_agent_id.strip():
            raise ValueError("new_agent_id must be a non-empty string")
        norm_id = new_agent_id.strip().lower()
        if validate_registry:
            if not agent_registry.has_agent(norm_id):
                raise AgentNotFoundError(f"Agent '{new_agent_id}' is not registered in AgentRegistry")
        self.current_agent_id = norm_id

    def set_current_agent(self, new_agent_id: str, validate_registry: bool = False) -> None:
        """Alias for switch_agent."""
        self.switch_agent(new_agent_id, validate_registry=validate_registry)

    def validate_agent_with_registry(self, registry: Any = None) -> bool:
        """Verify that current_agent_id is registered in AgentRegistry.

        Raises:
            AgentNotFoundError: If current_agent_id is not registered.
        """
        reg = registry or agent_registry
        if not reg.has_agent(self.current_agent_id):
            raise AgentNotFoundError(f"Agent '{self.current_agent_id}' is not registered in AgentRegistry")
        return True

    # ── Difficulty State Mutation ───────────────────────────────────────

    def set_difficulty(self, new_difficulty: DifficultyLevel | str) -> None:
        """Update interview difficulty metadata."""
        if isinstance(new_difficulty, str):
            new_difficulty = DifficultyLevel(new_difficulty.strip().lower())
        self.difficulty = new_difficulty

    # ── Competency Mutations ────────────────────────────────────────────

    def add_evaluated_competency(self, competency: str) -> bool:
        """Add a competency to evaluated list (deduplicated). Returns True if added, False if duplicate."""
        if not competency or not competency.strip():
            return False
        norm = competency.strip().lower()
        if norm not in self.evaluated_competencies:
            self.evaluated_competencies.append(norm)
            return True
        return False

    def add_missing_competency(self, competency: str) -> bool:
        """Add a competency to missing list (deduplicated). Returns True if added, False if duplicate."""
        if not competency or not competency.strip():
            return False
        norm = competency.strip().lower()
        if norm not in self.missing_competencies:
            self.missing_competencies.append(norm)
            return True
        return False

    def resolve_missing_competency(self, competency: str) -> bool:
        """Remove a competency from missing list. Returns True if removed, False if not found."""
        norm = competency.strip().lower()
        if norm in self.missing_competencies:
            self.missing_competencies.remove(norm)
            return True
        return False

    # ── Open Questions Mutations ────────────────────────────────────────

    def add_open_question(self, question: str) -> bool:
        """Add an open question or information gap (deduplicated). Returns True if added."""
        if not question or not question.strip():
            return False
        norm = question.strip()
        if norm not in self.open_questions:
            self.open_questions.append(norm)
            return True
        return False

    def resolve_open_question(self, question: str) -> bool:
        """Remove an open question. Returns True if removed, False if not found."""
        norm = question.strip().lower()
        for idx, q in enumerate(self.open_questions):
            if q.strip().lower() == norm:
                self.open_questions.pop(idx)
                return True
        return False

    # ── Question History ────────────────────────────────────────────────

    def add_question_history(self, item: "QuestionHistoryItem") -> None:
        """Append a QuestionHistoryItem to the structured question history."""
        self.question_history.append(item)

    def get_questions_for_competency(self, competency: str) -> list["QuestionHistoryItem"]:
        """Return all previously asked questions targeting a given competency."""
        norm = competency.strip().lower()
        return [q for q in self.question_history if q.competency.strip().lower() == norm]

    def is_competency_sufficiently_asked(self, competency: str) -> bool:
        """Return True if this competency already has a SUFFICIENT exploration in history."""
        return any(
            q.exploration_status == "SUFFICIENT"
            for q in self.get_questions_for_competency(competency)
        )

    # ── Evidence Accumulation ───────────────────────────────────────────

    def add_evidence(self, evidence: EvidenceItem | dict[str, Any] | str) -> EvidenceItem:
        """Add or update an evidence item. Deduplicates by item.id."""
        if isinstance(evidence, str):
            item = EvidenceItem(
                competency="general",
                signal=evidence.strip(),
                source_agent_id=self.current_agent_id,
                round_id=self.current_round_id,
            )
        elif isinstance(evidence, dict):
            item = EvidenceItem.model_validate(evidence)
        elif isinstance(evidence, EvidenceItem):
            item = evidence
        else:
            raise TypeError("evidence must be an EvidenceItem, dict, or str")

        for idx, existing in enumerate(self.accumulated_evidence):
            if existing.id == item.id:
                self.accumulated_evidence[idx] = item
                return item

        self.accumulated_evidence.append(item)
        return item

    # ── Contradiction Accumulation ──────────────────────────────────────

    def add_contradiction(
        self,
        contradiction: ContradictionItem | dict[str, Any] | str,
    ) -> ContradictionItem:
        """Add or update a contradiction item. Deduplicates by item.id."""
        if isinstance(contradiction, str):
            item = ContradictionItem(
                contradiction=contradiction.strip(),
                detected_by_agent_id=self.current_agent_id,
                round_id=self.current_round_id,
            )
        elif isinstance(contradiction, dict):
            item = ContradictionItem.model_validate(contradiction)
        elif isinstance(contradiction, ContradictionItem):
            item = contradiction
        else:
            raise TypeError("contradiction must be a ContradictionItem, dict, or str")

        for idx, existing in enumerate(self.detected_contradictions):
            if existing.id == item.id:
                self.detected_contradictions[idx] = item
                return item

        self.detected_contradictions.append(item)
        return item

    # ── Serialization Helpers ───────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to JSON-compatible dictionary."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InterviewAIContext":
        """Deserialize context from dictionary."""
        return cls.model_validate(data)

    def to_json(self) -> str:
        """Serialize context to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "InterviewAIContext":
        """Deserialize context from JSON string."""
        return cls.model_validate_json(json_str)
