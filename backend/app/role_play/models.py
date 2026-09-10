from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.intelligence.core.contracts import StrictModel


class RolePlaySignal(str, Enum):
    EMPATHY = "empathy"
    CLARIFICATION = "clarification"
    COMMITMENT = "commitment"
    SOLUTION = "solution"
    HOSTILITY = "hostility"
    DISMISSAL = "dismissal"
    POLICY_QUESTION = "policy_question"


class PersonaDefinition(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=10, max_length=1200)
    personality: str = Field(min_length=3, max_length=600)
    communication_style: str = Field(min_length=3, max_length=600)
    objectives: list[str] = Field(default_factory=list, max_length=10)
    concerns: list[str] = Field(default_factory=list, max_length=10)
    allowed_information: list[str] = Field(default_factory=list, max_length=15)
    restricted_information: list[str] = Field(default_factory=list, max_length=15)
    escalation_signals: list[RolePlaySignal] = Field(default_factory=lambda: [RolePlaySignal.HOSTILITY, RolePlaySignal.DISMISSAL], max_length=7)
    deescalation_signals: list[RolePlaySignal] = Field(default_factory=lambda: [RolePlaySignal.EMPATHY, RolePlaySignal.CLARIFICATION], max_length=7)
    initial_escalation: int = Field(default=2, ge=0, le=5)

    @model_validator(mode="after")
    def bounds(self):
        for values in [self.objectives, self.concerns, self.allowed_information, self.restricted_information]:
            if any(not value.strip() or len(value) > 600 for value in values): raise ValueError("Persona values must be 1-600 characters")
        if set(self.escalation_signals) & set(self.deescalation_signals): raise ValueError("Escalation rules must not conflict")
        return self


class ScenarioPhase(StrictModel):
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=100)
    brief: str = Field(min_length=10, max_length=1000)
    objectives: list[str] = Field(min_length=1, max_length=8)
    advance_on: list[RolePlaySignal] = Field(default_factory=lambda: [RolePlaySignal.SOLUTION], max_length=7)
    min_turns: int = Field(default=1, ge=1, le=8)
    max_turns: int = Field(default=4, ge=1, le=12)
    reveal_keys: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def bounds(self):
        if self.max_turns < self.min_turns: raise ValueError("Phase turn limits are inconsistent")
        if any(not value.strip() or len(value) > 300 for value in self.objectives): raise ValueError("Objectives must be 1-300 characters")
        return self


class ScenarioDefinition(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=10, max_length=1500)
    candidate_role: str = Field(min_length=2, max_length=160)
    persona_id: UUID
    phases: list[ScenarioPhase] = Field(min_length=1, max_length=8)
    competencies: list[str] = Field(default_factory=lambda: ["communication", "empathy", "problem_solving"], min_length=1, max_length=8)
    success_signals: list[RolePlaySignal] = Field(default_factory=lambda: [RolePlaySignal.SOLUTION, RolePlaySignal.COMMITMENT], max_length=7)
    failure_signals: list[RolePlaySignal] = Field(default_factory=lambda: [RolePlaySignal.HOSTILITY], max_length=7)
    hidden_information: dict[str, str] = Field(default_factory=dict, max_length=20)
    max_turns: int = Field(default=12, ge=2, le=40)
    duration_seconds: int = Field(default=900, ge=60, le=3600)
    policy_query: str = Field(default="", max_length=250)

    @model_validator(mode="after")
    def consistency(self):
        if len({p.id for p in self.phases}) != len(self.phases): raise ValueError("Phase IDs must be unique")
        if sum(p.min_turns for p in self.phases) > self.max_turns: raise ValueError("Not enough turns for configured phases")
        if len(set(self.competencies)) != len(self.competencies) or any(not c or len(c)>80 for c in self.competencies): raise ValueError("Competencies must be unique and bounded")
        if any(len(k)>80 or not k or len(v)>1000 or not v for k,v in self.hidden_information.items()): raise ValueError("Hidden information must be bounded")
        if any(not set(p.reveal_keys) <= self.hidden_information.keys() for p in self.phases): raise ValueError("Unknown reveal key")
        if set(self.success_signals) & set(self.failure_signals): raise ValueError("Success and failure rules conflict")
        return self


class DefinitionWrite(StrictModel):
    expected_revision: int = Field(default=0, ge=0)
    request_id: UUID


class PersonaWrite(DefinitionWrite):
    definition: PersonaDefinition


class ScenarioWrite(DefinitionWrite):
    definition: ScenarioDefinition


class RolePlayState(StrictModel):
    status: Literal["assigned", "active", "completed", "cancelled"] = "assigned"
    phase_index: int = Field(default=0, ge=0)
    phase_turns: int = Field(default=0, ge=0)
    turn_count: int = Field(default=0, ge=0)
    escalation: int = Field(default=2, ge=0, le=5)
    stance: Literal["guarded", "engaged", "resistant"] = "guarded"
    revealed_keys: list[str] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)
    achieved_phases: list[str] = Field(default_factory=list)
    unresolved_objections: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    completion_reason: str | None = None


class RolePlayActionType(str, Enum):
    RESPOND = "RESPOND"
    RAISE_OBJECTION = "RAISE_OBJECTION"
    REVEAL_INFORMATION = "REVEAL_INFORMATION"
    ESCALATE = "ESCALATE"
    DEESCALATE = "DEESCALATE"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    ADVANCE_PHASE = "ADVANCE_PHASE"
    END_SCENARIO = "END_SCENARIO"


class RolePlayAction(StrictModel):
    action: RolePlayActionType
    rationale: str = Field(min_length=1, max_length=600)
    phase_id: str


class SessionCreate(StrictModel):
    scenario_id: UUID
    candidate_id: str = Field(min_length=1, max_length=100)
    request_id: UUID


class TurnInput(StrictModel):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=4000)


class ControlInput(StrictModel):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    action: Literal["start", "finish", "cancel"]
