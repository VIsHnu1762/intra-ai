"""Keep live routing choices aligned with the same JD and coverage guards."""

import asyncio
import json
from unittest.mock import patch

from app.agent_context.models import AgentTurnContext, CandidateProfileContext, JobContext
from app.agents.models import AgentProfile
from app.agents.registry import AgentRegistry
from app.core.config import settings
from app.interview_context.models import InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.models.enums import ActionType, DifficultyLevel
from app.knowledge_graph.memory_models import PersistentCandidateMemory
from app.orchestrator.prompts import build_nemotron_routing_messages
from app.orchestrator.service import MetaOrchestrator


def prompt_state(messages):
    return json.loads(messages[1]["content"].split("INTERVIEW STATE:\n", 1)[1].split("\n\nReturn your routing decision", 1)[0])


def context():
    return InterviewAIContext(
        interview_id="prompt-eligibility", candidate_id="candidate", current_round_id="panel",
        current_agent_id="alex", missing_competencies=["system_design", "debugging", "product_sense"],
        metadata={"configured_agent_ids": ["alex", "jordan"],
                  "required_competencies": ["System Design", "Debugging", "Product Sense"]},
    )


def partial_analysis(competency="system_design"):
    return AnswerAnalysis(answer_id="partial", overall_performance=.6, confidence=.9,
        vague=False, contradiction_detected=False,
        competency_findings=[CompetencyFinding(competency_id=competency, assessment="A detail remains unexplained", confidence=.9)],
        missing_information=["Kafka failure recovery"])


def test_prompt_lists_only_configured_job_eligible_choices_and_levels():
    registry = AgentRegistry()
    registry.register(AgentProfile(agent_id="taylor", display_name="Taylor", role="Security specialist",
                                  description="Assesses security decisions", questioning_style="Scenario-based",
                                  instructions="Probe the candidate's own security work.",
                                  focal_competencies=["security"]))
    ctx = context()
    state = prompt_state(build_nemotron_routing_messages(
        ctx, partial_analysis(), registry,
        unresolved_competencies=ctx.missing_competencies,
        selected_priority="probe_missing_info", selected_target_competency="technical_depth",
    ))
    assert state["eligible_competencies_by_agent"] == {
        "alex": ["system_design", "debugging"], "jordan": ["product_sense"],
    }
    assert state["selected_policy"] == {"priority": "probe_missing_info", "target_competency": "system_design"}
    assert {a["agent_id"] for a in state["agent_registry"]} == {"alex", "jordan"}
    for agent in state["agent_registry"]:
        eligible = state["eligible_competencies_by_agent"][agent["agent_id"]]
        assert agent["unresolved_focal_competencies"] == eligible
        assert list(state["difficulty_by_competency"][agent["agent_id"]]) == eligible
    # Broad persona expertise stays available without becoming a routing target.
    assert "technical_depth" in state["agent_registry"][0]["focal_competencies"]
    assert "technical_depth" not in state["difficulty_by_competency"]["alex"]


def test_partial_observation_remains_eligible_but_sufficient_history_does_not():
    ctx = context()
    ctx.evaluated_competencies = ["system_design", "debugging"]
    ctx.missing_competencies = ["product_sense"]
    ctx.add_question_history(QuestionHistoryItem(
        agent_id="alex", competency="debugging", question_text="How did you debug it?",
        difficulty=DifficultyLevel.MEDIUM, exploration_status="SUFFICIENT"))
    state = prompt_state(build_nemotron_routing_messages(
        ctx, partial_analysis(), AgentRegistry(), unresolved_competencies=["product_sense", "debugging"],
        selected_priority="probe_missing_info", selected_target_competency="system_design",
    ))
    assert state["eligible_competencies_by_agent"]["alex"] == ["system_design"]
    assert state["difficulty_by_competency"]["alex"] == {"system_design": "medium"}


def test_prompt_eligibility_supports_a_third_configured_agent():
    registry = AgentRegistry()
    registry.register(AgentProfile(agent_id="taylor", display_name="Taylor", role="Security specialist",
                                  description="Assesses security decisions", questioning_style="Scenario-based",
                                  instructions="Probe the candidate's own security work.",
                                  focal_competencies=["security", "incident_response"]))
    ctx = context()
    ctx.metadata.update(configured_agent_ids=["alex", "taylor"], required_competencies=["system_design", "security"])
    ctx.missing_competencies = ["security"]
    state = prompt_state(build_nemotron_routing_messages(
        ctx, partial_analysis(), registry, selected_priority="switch_agent", selected_target_competency="security",
    ))
    assert state["eligible_competencies_by_agent"] == {"alex": ["system_design"], "taylor": ["security"]}
    assert state["selected_policy"]["target_competency"] == "security"
    assert "jordan" not in state["difficulty_by_competency"]


def test_live_graph_passes_priority_and_keeps_valid_grounded_model_dialogue():
    async def run():
        ctx = context()
        captured = []
        question = "How would you recover the Kafka payment service after a consumer failure?"

        async def fake_groq(**kwargs):
            captured.append(prompt_state(kwargs["messages"]))
            return {"action": "ASK_QUESTION", "target_agent_id": "alex", "competency": "system_design",
                    "question_text": question, "rationale": "Clarify Kafka failure recovery."}

        with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", "offline-key"), patch("app.orchestrator.graph.call_groq", new=fake_groq):
            action = await MetaOrchestrator().decide_async(ctx, partial_analysis())
        assert len(captured) == 1
        assert captured[0]["selected_policy"] == {"priority": "probe_missing_info", "target_competency": "system_design"}
        assert captured[0]["eligible_competencies_by_agent"]["alex"] == ["system_design", "debugging"]
        assert action.action == ActionType.ASK_QUESTION
        assert action.metadata["nemotron_used"] is True
        assert action.question_text == question

    asyncio.run(run())


def test_off_jd_model_target_is_still_rejected_without_another_model_call():
    async def run():
        ctx = context()
        # The hydrated job is authoritative even when session metadata is broader.
        turn = AgentTurnContext(
            candidate=CandidateProfileContext(candidate_id=ctx.candidate_id),
            job=JobContext(job_id="payments", title="Payments Engineer", required_competencies=["system_design"]),
            persistent_memory=PersistentCandidateMemory(candidate_id=ctx.candidate_id),
            interview=ctx, agent=AgentRegistry().get_profile("alex"),
            current_answer="Kafka consumers replay offsets after a failure.",
        )
        captured = []

        async def fake_groq(**kwargs):
            captured.append(prompt_state(kwargs["messages"]))
            return {"action": "ASK_QUESTION", "target_agent_id": "alex", "competency": "technical_depth",
                    "question_text": "Describe compiler internals.", "rationale": "Probe broader technical knowledge."}

        with patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", "offline-key"), patch("app.orchestrator.graph.call_groq", new=fake_groq):
            action = await MetaOrchestrator().decide_async(ctx, partial_analysis(), turn_context=turn)
        assert len(captured) == 1
        assert captured[0]["eligible_competencies_by_agent"] == {"alex": ["system_design"], "jordan": []}
        assert action.metadata["nemotron_used"] is False
        assert action.competency == "system_design"
        assert "compiler" not in action.question_text.lower()

    asyncio.run(run())
