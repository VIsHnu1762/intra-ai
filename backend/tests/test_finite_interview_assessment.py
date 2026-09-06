"""Assessment may conclude with insufficient evidence, without requiring mastery."""

from copy import deepcopy

import pytest

from app.agents.models import AgentProfile, NextAction
from app.agents.registry import AgentRegistry
from app.core.config import settings
from app.interview_context.models import EvidenceItem, InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator.assessment import plan_insufficient_assessment
from app.orchestrator.policies import build_competency_question_options
from app.orchestrator.service import MetaOrchestrator
from app.sessions.models import InterviewConfiguration, InterviewSession
from app.sessions.service import InterviewSessionService


def result(answer_id, competency, *, confidence=.9, performance=.1, contradiction=False):
    return AnswerAnalysis(
        answer_id=answer_id, overall_performance=performance, confidence=confidence,
        vague=performance < .45, contradiction_detected=contradiction,
        contradiction_details="Earlier claim differs" if contradiction else None,
        missing_information=[f"Unresolved gap described differently in {answer_id}"],
        evidence=[EvidenceItem(id=f"ev-{answer_id}", competency=competency,
            signal="Candidate could not explain the requested simple task", score=performance * 10)],
        competency_findings=[CompetencyFinding(competency_id=competency, confidence=confidence,
            assessment="Cannot yet demonstrate this objective", evidence_ids=[f"ev-{answer_id}"])],
    )


def context():
    return InterviewAIContext(interview_id="finite-assessment", candidate_id="isolated-finite",
        current_round_id="technical", current_agent_id="alex", difficulty=DifficultyLevel.EASY,
        missing_competencies=["system_design", "product_sense"],
        metadata={"configured_agent_ids": ["alex", "jordan"]})


def ask_objective(ctx, competency, *, objective=True, difficulty=DifficultyLevel.EASY):
    ctx.add_question_history(QuestionHistoryItem(agent_id=ctx.current_agent_id,
        competency=competency, question_text=f"Explain one simple {competency} task.",
        difficulty=difficulty, metadata={"objective_id": f"{competency}:purpose"} if objective else {}))


def test_weak_simple_answer_switches_to_remaining_owner_without_claiming_mastery(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
    ctx = context()
    ask_objective(ctx, "system_design")
    before = deepcopy(ctx.model_dump())
    action = MetaOrchestrator().decide(ctx, result("a1", "system_design"))
    assert action.action == ActionType.SWITCH_AGENT and action.target_agent_id == "jordan"
    assert action.competency == "product_sense"
    assert ctx.model_dump() == before  # Planning remains side-effect free.
    MetaOrchestrator.record_assessment(ctx, action)
    assert ctx.question_history[-1].exploration_status == "ASSESSED_INSUFFICIENT"
    assert ctx.metadata["assessed_insufficient"]["system_design"]["answer_id"] == "a1"
    assert "system_design" in ctx.missing_competencies
    assert not ctx.is_competency_sufficiently_asked("system_design")
    assert ctx.evaluated_competencies == []


@pytest.mark.parametrize("objective,difficulty,confidence,performance,contradiction", [
    (False, DifficultyLevel.EASY, .9, .1, False),
    (True, DifficultyLevel.MEDIUM, .9, .1, False),
    (True, DifficultyLevel.EASY, .3, .1, False),
    (True, DifficultyLevel.EASY, .9, .85, False),
    (True, DifficultyLevel.EASY, .9, .1, True),
])
def test_unscaffolded_uncertain_strong_or_contradictory_answer_is_not_closed(
    objective, difficulty, confidence, performance, contradiction,
):
    ctx = context()
    ask_objective(ctx, "system_design", objective=objective, difficulty=difficulty)
    assert plan_insufficient_assessment(ctx, result("a1", "system_design",
        confidence=confidence, performance=performance, contradiction=contradiction)) == {}


def test_all_insufficient_competencies_complete_and_survive_serialization(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
    ctx = context(); ask_objective(ctx, "system_design")
    orch = MetaOrchestrator()
    first = orch.decide(ctx, result("a1", "system_design"))
    MetaOrchestrator.record_assessment(ctx, first)
    ctx = InterviewAIContext.model_validate_json(ctx.model_dump_json())
    ctx.current_agent_id = "jordan"
    ask_objective(ctx, "product_sense")
    final = orch.decide(ctx, result("a2", "product_sense"))
    assert final.action == ActionType.COMPLETE
    assert "insufficient" in final.rationale.lower()
    MetaOrchestrator.record_assessment(ctx, final)
    assert set(ctx.metadata["assessed_insufficient"]) == {"system_design", "product_sense"}
    assert all(q.exploration_status == "ASSESSED_INSUFFICIENT" for q in ctx.question_history)
    assert not any(ctx.is_competency_sufficiently_asked(c) for c in ctx.missing_competencies)


def test_registry_driven_third_agent_receives_remaining_objective(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
    registry = AgentRegistry()
    registry.register(AgentProfile(agent_id="taylor", display_name="Taylor", role="Design reviewer",
        description="Assess interface design", focal_competencies=["interface_design"],
        questioning_style="clear", instructions="Ask about interface design."))
    ctx = context(); ctx.metadata["configured_agent_ids"] = ["alex", "taylor"]
    ctx.missing_competencies = ["system_design", "interface_design"]
    ask_objective(ctx, "system_design")
    action = MetaOrchestrator(registry).decide(ctx, result("a1", "system_design"))
    assert action.action == ActionType.SWITCH_AGENT and action.target_agent_id == "taylor"


def test_changed_gap_wording_cannot_reopen_exhausted_objectives(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
    ctx = context()
    weak = result("old", "system_design", confidence=.3)
    for objective, text in build_competency_question_options("system_design", DifficultyLevel.EASY, ctx, weak):
        ctx.add_question_history(QuestionHistoryItem(agent_id="alex", competency="system_design",
            question_text=f"Earlier wording of {objective}", difficulty=DifficultyLevel.EASY,
            exploration_status="PARTIAL", metadata={"objective_id": objective, "answered_by": "old"}))
    action = MetaOrchestrator().decide(ctx, result("completely-new-gap-label", "system_design", confidence=.3))
    assert action.action == ActionType.SWITCH_AGENT and action.target_agent_id == "jordan"
    assert action.metadata["assessment_policy"]["system_design"]["reason"] == "distinct_objectives_exhausted"


def test_round_objectives_canonicalize_declared_aliases_and_preserve_unknowns():
    session = InterviewSession.from_config(InterviewConfiguration(
        interview_id="legacy-objectives", candidate_id="isolated", agent_ids=["alex", "jordan"],
        metadata={"round_configs": [
            {"type": "disabled", "enabled": False, "order_index": 0, "focus_areas": ["disabled_topic"]},
            {"type": "technical", "enabled": True, "order_index": 2, "focus_areas": ["system_design"]},
            {"type": "introduction", "enabled": True, "order_index": 1, "focus_areas": ["user_empathy", "trade_off_analysis", "stakeholder_management", "custom_topic"]},
        ]},
    ))
    InterviewSessionService._prepare_context_metadata(session)
    assert session.metadata["current_round_id"] == "introduction"
    assert session.metadata["required_competencies"] == ["customer_understanding", "trade_off_decisions", "communication_of_product_decisions", "custom_topic", "system_design"]
    assert session.metadata["competency_aliases_applied"]["user_empathy"] == "customer_understanding"
    assert session.metadata["unassigned_competencies"] == ["custom_topic"]


def test_scheduling_keeps_round_details_without_assigning_disabled_agents(monkeypatch):
    from app.services.scheduling_service import SchedulingService
    from app.sessions.service import interview_session_service

    configurations = []
    monkeypatch.setattr(interview_session_service, "create_session", configurations.append)
    rounds = [
        {"type": "behavioral", "enabled": False, "order_index": 1, "agent_ids": ["jordan"], "focus_areas": ["product_sense"], "duration_minutes": 10},
        {"type": "technical", "enabled": True, "order_index": 2, "agent_ids": ["alex"], "focus_areas": ["system_design"], "duration_minutes": 20},
    ]
    SchedulingService._ensure_live_session(
        {"id": "application", "candidate_id": "synthetic-candidate", "jobs": {"job_rounds": rounds}},
        {"id": "synthetic-session"},
    )
    assert len(configurations) == 1
    config = configurations[0]
    assert config.agent_ids == ["alex"]
    assert config.metadata["round_configs"] == rounds
    assert config.metadata["required_competencies"] == ["system_design"]


def test_compound_model_question_is_replaced_by_one_clear_objective(monkeypatch):
    from app.orchestrator.questions import spoken_question_is_clear

    monkeypatch.setattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "dummy-key")
    ctx = context()
    ctx.difficulty = DifficultyLevel.MEDIUM
    ask_objective(ctx, "system_design", difficulty=DifficultyLevel.MEDIUM)

    async def model_call(**_kwargs):
        return {"action": "ASK_QUESTION", "target_agent_id": "alex", "competency": "system_design",
            "rationale": "Probe the unresolved design mechanism", "cross_agent_opportunity": False,
            "question_text": "How do you recover the system design after a database failure, and why would you choose that strategy?"}

    monkeypatch.setattr("app.orchestrator.graph.call_groq", model_call)
    action = MetaOrchestrator().decide(ctx, result("strong-but-incomplete", "system_design", performance=.85))
    assert action.action == ActionType.ASK_QUESTION
    assert action.metadata["compound_question_split"] is True
    assert action.question_text == "How do you recover the system design after a database failure?"
    assert spoken_question_is_clear(action.question_text, action.difficulty)
    assert action.metadata["objective_id"].startswith("system_design:")
    assert action.metadata["assessment_policy"] == {}  # No false negative/mastery assessment.


def test_clear_new_model_prose_cannot_extend_exhausted_objective_bank(monkeypatch):
    """Moderate answers cannot create a fifth objective through fresh LLM wording."""
    monkeypatch.setattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "dummy-key")
    ctx = context()
    ctx.difficulty = DifficultyLevel.MEDIUM
    moderate = result("new-moderate", "system_design", performance=.55)
    options = build_competency_question_options("system_design", DifficultyLevel.MEDIUM, ctx, moderate)
    assert options
    for objective, _ in options:
        ctx.add_question_history(QuestionHistoryItem(agent_id="alex", competency="system_design",
            question_text=f"Previous distinct wording for {objective}", difficulty=DifficultyLevel.MEDIUM,
            exploration_status="PARTIAL", metadata={"objective_id": objective, "answered_by": "previous"}))

    calls = []

    async def new_clear_question(**kwargs):
        calls.append(kwargs)
        return {"action": "ASK_QUESTION", "target_agent_id": "alex", "competency": "system_design",
            "rationale": "Explore another recovery mechanism", "cross_agent_opportunity": False,
            "question_text": "How would you verify database recovery for this system design?"}

    monkeypatch.setattr("app.orchestrator.graph.call_groq", new_clear_question)
    action = MetaOrchestrator().decide(ctx, moderate)
    assert len(calls) == 1
    assert action.action == ActionType.SWITCH_AGENT
    assert action.target_agent_id == "jordan" and action.competency == "product_sense"
    assert action.metadata["assessment_policy"]["system_design"]["reason"] == "distinct_objectives_exhausted"
    assert "objective_id" not in action.metadata
    MetaOrchestrator.record_assessment(ctx, action)
    assert "system_design" in ctx.metadata["assessed_insufficient"]
    assert not ctx.is_competency_sufficiently_asked("system_design")
