"""Internal state and validation models for the LangGraph Meta-Orchestrator."""

from __future__ import annotations

from typing import Any, Optional, TypedDict
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent_context.models import AgentTurnContext
from app.agents.models import AgentProfile, NextAction
from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis
from app.models.enums import ActionType, DifficultyLevel


class NemotronRoutingDecision(BaseModel):
    """Validated structured output from Nemotron routing reasoning.

    This model enforces strict typing on what Nemotron can return.
    Free-form fields like rationale are preserved for traceability but
    do NOT directly control runtime — the orchestrator validates and applies.
    """

    model_config = ConfigDict(extra="ignore")

    action: str = Field(..., description="One of: ASK_QUESTION, SWITCH_AGENT, COMPLETE")
    target_agent_id: str = Field(..., description="Agent ID from the registry to target.")
    competency: Optional[str] = Field(default=None, description="Target competency, if applicable.")
    rationale: str = Field(..., description="Explainable rationale grounded in candidate answer.")
    cross_agent_opportunity: bool = Field(default=False)
    trigger_signals: list[str] = Field(default_factory=list)
    unresolved_target_competencies: list[str] = Field(default_factory=list)
    question_text: Optional[str] = Field(default=None, description="Optional Nemotron-suggested question text.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid = {"ASK_QUESTION", "SWITCH_AGENT", "COMPLETE"}
        if v not in valid:
            raise ValueError(f"action must be one of {valid}, got '{v}'")
        return v

    @field_validator("target_agent_id")
    @classmethod
    def validate_target_agent_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("target_agent_id must be a non-empty string")
        return v.strip().lower()

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("rationale must be a non-empty string")
        return v.strip()

    def to_action_type(self) -> ActionType:
        """Convert string action to ActionType enum."""
        return ActionType(self.action)


class OrchestratorGraphState(TypedDict, total=False):
    """Internal orchestration state passed through LangGraph decision nodes.

    Uses existing authoritative models (InterviewAIContext, AnswerAnalysis, NextAction)
    without duplicating or inventing competing candidate memory stores.
    """

    context: InterviewAIContext
    analysis: AnswerAnalysis
    current_question_text: Optional[str]  # Text of the question that prompted this answer
    current_agent_profile: AgentProfile
    turn_context: Optional[AgentTurnContext]

    # Derived decision flags
    effective_missing_competencies: list[str]
    insufficient_assessments: dict[str, dict[str, Any]]
    is_complete: bool
    force_deterministic: bool  # Enforce policy; brief/weak answers still allow Meta to phrase its question
    priority: str  # "contradiction", "vagueness", "probe_missing_info", "probe_fundamentals", "advance_competency", "switch_agent", "complete"

    # Nemotron routing decision (validated)
    nemotron_decision: Optional[NemotronRoutingDecision]
    nemotron_used: bool  # Whether Nemotron was used or fallback applied
    orchestrator_provider: str
    orchestrator_model: str
    orchestrator_error_code: Optional[str]

    # Selected parameters (from Nemotron or fallback)
    target_competency: Optional[str]
    target_agent_id: Optional[str]
    difficulty: Optional[DifficultyLevel]
    question_text: Optional[str]
    rationale: Optional[str]

    # Canonical terminal output
    next_action: Optional[NextAction]
    error: Optional[str]
