"""Offline regression tests for evidence-based difficulty and question grounding."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agents.models import AgentProfile, NextAction
from app.agents.registry import AgentRegistry
from app.core.config import settings
from app.interview_context.models import EvidenceItem, InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator.policies import plan_competency_difficulty, question_was_asked, substantive_subject
from app.orchestrator.service import MetaOrchestrator


def analysis(score=0.9, vague=False, competency="scalability", confidence=0.9, evidence=True, **kwargs):
    items = [EvidenceItem(id="proof", competency=competency, signal="Redis cache invalidation under load")] if evidence else []
    return AnswerAnalysis(
        answer_id="answer-1", overall_performance=score, confidence=confidence,
        vague=vague, contradiction_detected=False, evidence=items,
        competency_findings=[CompetencyFinding(competency_id=competency, assessment="Specific observed response", confidence=confidence, evidence_ids=["proof"] if evidence else [])],
        **kwargs,
    )


def context(difficulty=DifficultyLevel.MEDIUM):
    return InterviewAIContext(
        interview_id="policy-test", candidate_id="candidate-test", current_round_id="r1",
        current_agent_id="alex", difficulty=difficulty,
        missing_competencies=["scalability", "debugging"],
        accumulated_evidence=[EvidenceItem(competency="system_design", signal="Earlier example")],
    )


def profile():
    return AgentRegistry().get_profile("alex").model_copy(update={"max_difficulty": DifficultyLevel.HARD})


def assert_concrete_scaling_question(action):
    """Check the assessed objective and a spoken scenario, not its internal label."""
    assert action.competency == "scalability"
    assert action.question_text.count("?") == 1
    assert len(action.question_text.split()) <= 48
    assert any(term in action.question_text.lower() for term in ("cache", "redis", "database", "server", "users", "requests", "twice as many people"))
    assert "core concepts of" not in action.question_text.lower()


@pytest.mark.parametrize("before,score,vague,expected", [
    (DifficultyLevel.EASY, 0.9, False, DifficultyLevel.MEDIUM),
    (DifficultyLevel.MEDIUM, 0.9, False, DifficultyLevel.HARD),
    (DifficultyLevel.HARD, 0.9, False, DifficultyLevel.HARD),
    (DifficultyLevel.HARD, 0.2, False, DifficultyLevel.MEDIUM),
    (DifficultyLevel.MEDIUM, 0.2, False, DifficultyLevel.EASY),
    (DifficultyLevel.EASY, 0.2, False, DifficultyLevel.EASY),
    (DifficultyLevel.MEDIUM, 0.6, False, DifficultyLevel.MEDIUM),
    (DifficultyLevel.MEDIUM, 0.8, True, DifficultyLevel.EASY),
])
def test_evidence_policy_one_step_and_bounds(before, score, vague, expected):
    ctx = context(before)
    snapshot = ctx.to_dict()
    level, policy = plan_competency_difficulty(ctx, analysis(score, vague), profile(), "scalability")
    assert level == expected
    assert policy["before"] == before.value
    assert ctx.to_dict() == snapshot


@pytest.mark.parametrize("result", [analysis(evidence=False), analysis(confidence=0.4), analysis(missing_information=["failure recovery"])])
def test_score_alone_never_increases_difficulty(result):
    level, _ = plan_competency_difficulty(context(), result, profile(), "scalability")
    assert level == DifficultyLevel.MEDIUM


def test_opposing_signal_requires_confirmation_and_survives_serialization():
    ctx = context()
    level, policy = plan_competency_difficulty(ctx, analysis(score=0.2), profile(), "scalability")
    action = NextAction(action=ActionType.ASK_QUESTION, target_agent_id="alex", competency="scalability", difficulty=level, question_text="What is one example of scalability?", metadata={"difficulty_policy": policy})
    MetaOrchestrator.record_question(ctx, action)
    ctx = InterviewAIContext.from_json(ctx.to_json())
    first, pending = plan_competency_difficulty(ctx, analysis(), profile(), "scalability")
    assert first == DifficultyLevel.EASY
    assert pending["reason"] == "await_second_reversal_signal"
    action.difficulty, action.metadata = first, {"difficulty_policy": pending}
    action.question_text = "How would you verify a simple scalability change?"
    MetaOrchestrator.record_question(ctx, action)
    second, _ = plan_competency_difficulty(ctx, analysis(), profile(), "scalability")
    assert second == DifficultyLevel.MEDIUM


def test_competency_level_does_not_inherit_another_competencys_score():
    ctx = context(DifficultyLevel.HARD)
    ctx.add_question_history(QuestionHistoryItem(agent_id="alex", competency="scalability", question_text="Simple scaling example?", difficulty=DifficultyLevel.EASY))
    level, _ = plan_competency_difficulty(ctx, analysis(competency="debugging"), profile(), "scalability")
    assert level == DifficultyLevel.EASY


def test_duplicate_and_close_rewording_detected():
    history = [QuestionHistoryItem(agent_id="alex", competency="scalability", question_text="How did you handle Redis failure?", difficulty=DifficultyLevel.MEDIUM)]
    assert question_was_asked("How did you handle Redis failure?!", history)
    assert question_was_asked("How did you handle a Redis failure?", history)
    assert not question_was_asked("What metric showed that the cache was effective?", history)


def test_repeated_m1_followup_replaced_with_new_competency_objective():
    ctx = context()
    repeated = "Regarding your approach to scalability, what trade-offs did you consider around failure recovery?"
    ctx.add_question_history(QuestionHistoryItem(agent_id="alex", competency="scalability", question_text=repeated, difficulty=DifficultyLevel.MEDIUM))
    with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", ""):
        # Explicitly supply the repeated M1 recommendation; the old fixture
        # depended on the former raw-gap template accidentally regenerating it.
        action = MetaOrchestrator().decide(ctx, analysis(
            score=0.6, missing_information=["failure recovery"], recommended_follow_up=repeated,
        ))
    assert action.question_text != repeated
    assert_concrete_scaling_question(action)
    assert action.metadata["question_policy"]["repetition_prevented"]


def test_jd_target_blocks_invented_competency_and_reuses_existing_model_call():
    ctx = context()
    turn = SimpleNamespace(job=SimpleNamespace(required_competencies=["debugging"]))
    with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", ""):
        action = MetaOrchestrator().decide(ctx, analysis(score=0.2, competency="astrology"), turn_context=turn)
    assert action.action == ActionType.ASK_QUESTION
    assert action.competency == "debugging"
    assert "wrong result" in action.question_text.lower()
    assert "check first" in action.question_text.lower()
    assert action.question_text.count("?") == 1


def test_handoff_and_closing_are_not_question_history():
    ctx = context()
    for kind in (ActionType.SWITCH_AGENT, ActionType.COMPLETE):
        MetaOrchestrator.record_question(ctx, NextAction(action=kind, target_agent_id="jordan", question_text="Thank you. Jordan will continue."))
    assert ctx.question_history == []


def test_unselected_registered_agent_cannot_receive_handoff():
    ctx = context()
    ctx.missing_competencies.append("prioritization")
    ctx.metadata["configured_agent_ids"] = ["alex"]

    async def try_unselected_switch(**kwargs):
        assert '"agent_id": "jordan"' not in kwargs["messages"][1]["content"]
        return {"action": "SWITCH_AGENT", "target_agent_id": "jordan", "competency": "prioritization", "rationale": "A product follow-up could help."}

    with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", "offline-key"), patch("app.orchestrator.graph.call_groq", new=try_unselected_switch):
        action = MetaOrchestrator().decide(ctx, analysis(score=0.6, missing_information=["Redis failure"]))
    assert action.action == ActionType.ASK_QUESTION
    assert action.target_agent_id == "alex"
    assert action.competency == "scalability"


def test_weak_observation_removed_by_m1_is_still_unresolved_in_history():
    ctx = context()
    ctx.missing_competencies = ["debugging"]
    ctx.evaluated_competencies = ["scalability"]  # M1 saw it, but it was weak.
    ctx.add_question_history(QuestionHistoryItem(agent_id="alex", competency="scalability", question_text="What is a simple scaling example?", difficulty=DifficultyLevel.EASY, exploration_status="PARTIAL"))
    with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", ""):
        action = MetaOrchestrator().decide(ctx, analysis(competency="debugging"))
    assert action.action == ActionType.ASK_QUESTION
    assert action.competency == "scalability"
    assert action.difficulty == DifficultyLevel.EASY


def test_unrelated_model_question_replaced_without_second_model_call():
    calls = []

    async def ungrounded_question(**kwargs):
        calls.append(kwargs)
        return {"action": "ASK_QUESTION", "target_agent_id": "alex", "competency": "scalability", "rationale": "Explore the stated competency.", "question_text": "Which planets influence astrological predictions?"}

    with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", "offline-key"), patch("app.orchestrator.graph.call_groq", new=ungrounded_question):
        action = MetaOrchestrator().decide(context(), analysis(score=0.6, missing_information=["Redis failure"]))
    assert len(calls) == 1
    assert_concrete_scaling_question(action)
    assert "planets" not in action.question_text
    assert action.metadata["question_policy"]["ungrounded_question_replaced"]


@pytest.mark.parametrize("prior_subject", [None, "payment service"])
def test_ignorance_does_not_become_a_project_example(prior_subject):
    ctx = context()
    if prior_subject:
        ctx.add_evidence(EvidenceItem(competency="scalability", signal="I built the payment service with idempotency keys.", metadata={"subject": prior_subject}))
    result = analysis(score=0.2, vague=True, missing_information=["Idempotency key generation strategy"])
    result.evidence[0].signal = "I am not sure. I do not know how that works."
    result.evidence[0].metadata["subject"] = "I am not sure."
    with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", ""):
        action = MetaOrchestrator().decide(ctx, result)
    assert action.difficulty == DifficultyLevel.EASY
    assert_concrete_scaling_question(action)
    assert len(action.question_text.split()) <= 32
    # An ignorance response gets one concrete fundamental, not the analyzer's
    # internal missing-information label quoted as a candidate-facing task.
    assert "users" in action.question_text.lower() or "twice as many people" in action.question_text.lower()
    assert "I am not sure" not in action.question_text
    if prior_subject:
        assert "payment service" in action.question_text
    else:
        assert "example you mentioned" not in action.question_text
        assert "payment service" not in action.question_text


@pytest.mark.parametrize("utterance", ["I am not sure.", "I don't know", "I don’t understand", "Hello Alex", "Hi Jordan, nice to meet you.", "no idea", "unknown"])
def test_conversational_utterances_are_not_subjects(utterance):
    assert substantive_subject(utterance) is None


def test_live_async_orchestrator_call_runs_on_callers_event_loop():
    async def run():
        caller_loop = asyncio.get_running_loop()
        seen = []

        async def fake_groq(**kwargs):
            seen.append(asyncio.get_running_loop())
            return {"action": "ASK_QUESTION", "target_agent_id": "alex", "competency": "scalability", "rationale": "Probe the known Redis failure gap.", "question_text": "How would you handle Redis failure?"}

        with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", "offline-key"), patch("app.orchestrator.graph.call_groq", new=fake_groq):
            await MetaOrchestrator().decide_async(context(), analysis(score=0.6, missing_information=["Redis failure"]))
        assert seen == [caller_loop]

    asyncio.run(run())
