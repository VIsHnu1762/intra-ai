"""Replay captured weak answers through the adapter's real routing and graph.

The utterances and score/confidence pairs come from voice-personalized-1788647921
(callback turns 5–14). M1 is an explicit recorded-quality fixture, not a live
provider. The deterministic MetaOrchestrator, context update, and in-memory KG
persistence are real. No Agora/native-greeting lifecycle is simulated as audio.
"""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

from app.agent_context.builder import AgentTurnContextBuilder
from app.agents.models import NextAction
from app.core.config import settings
from app.custom_llm.adapter import CustomLLMAdapter
from app.custom_llm.models import ChatCompletionRequest
from app.interview_context.models import EvidenceItem
from app.interview_context.store import InterviewSessionStore
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.knowledge_graph.memory_service import CandidateMemoryService
from app.knowledge_graph.repository import InMemoryKnowledgeGraphRepository
from app.knowledge_graph.service import KnowledgeGraphPersistenceService
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator.service import MetaOrchestrator


PYTHON_ANSWER = (
    "Like, Python is the primary language that we can use for ML model. So we have used it, "
    "and we used a method of isolation forest and reinforced learning— ML model algorithms— Yeah."
)
DESIGN_ANSWER = (
    "So I started with the system design concepts initially. I learned what is caching, "
    "what is, like, what—how a system should be designed. How a software architecture "
    "should be—and what are the fundamental concepts of it."
)
CODING_ANSWER = (
    "Like, coding problem-solving? I used—uh, I worked on Python basically, so I used to "
    "code on Python. And the fundamentals are, like, branching statements, looping "
    "statements, decision-making, control statements, and the variables pointers and stuff."
)
SCALING_ANSWER = (
    "So the main purpose of scalability is to increase the load balancing capacity of "
    "the application? If the concurrent users increases, the application should not "
    "break and it should work properly."
)
IGNORANCE = "I actually don't know."
FINAL_IGNORANCE = "I can't answer this, actually. I don't know."
CLARIFICATIONS = (
    "One simple example of what?",
    "One simple example of the project that I worked on?",
    "What are you asking? I can't understand.",
    "For scalability of what?",
)
REPLAY = (
    PYTHON_ANSWER, *CLARIFICATIONS[:2], DESIGN_ANSWER, IGNORANCE,
    CODING_ANSWER, *CLARIFICATIONS[2:], SCALING_ANSWER, FINAL_IGNORANCE,
)
OBSERVED_QUALITY = {
    PYTHON_ANSWER: (0.2, 0.4, True),
    DESIGN_ANSWER: (0.2, 0.6, True),
    IGNORANCE: (0.1, 0.2, False),
    CODING_ANSWER: (0.3, 0.7, True),
    SCALING_ANSWER: (0.3, 0.6, True),
    FINAL_IGNORANCE: (0.1, 0.2, True),
}
TECHNICAL_OBJECTIVES = ("technical_depth", "system_design", "coding_problem_solving", "scalability")
GAP = "A concrete implementation and its result are still missing."


class ObservedM1Fixture:
    """Bind recorded answer quality to whichever corrected question is active."""

    def __init__(self):
        self.inputs = []

    async def analyze_async(self, data):
        self.inputs.append(data.model_copy(deep=True))
        performance, confidence, vague = OBSERVED_QUALITY[data.answer_text]
        question = next(q for q in reversed(data.context.question_history)
                        if q.agent_id == data.agent_profile.agent_id)
        evidence = []
        if data.answer_text not in {IGNORANCE, FINAL_IGNORANCE}:
            # The verbatim answer is the evidence; no stronger positive signal
            # or synthetic high confidence is invented to force progression.
            evidence = [EvidenceItem(
                id=f"{data.answer_id}:e1", competency=question.competency,
                signal=data.answer_text, score=performance * 10,
                source_agent_id=data.agent_profile.agent_id,
            )]
        return AnswerAnalysis(
            answer_id=data.answer_id, overall_performance=performance,
            confidence=confidence, vague=vague, contradiction_detected=False,
            missing_information=[GAP], evidence=evidence,
            competency_findings=[CompetencyFinding(
                competency_id=question.competency, assessment=GAP, confidence=confidence,
                evidence_ids=[item.id for item in evidence],
            )],
        )


def build_replay(monkeypatch):
    import app.orchestrator.graph as graph_module
    from app.sessions.service import interview_session_service

    monkeypatch.setattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
    external_call = AsyncMock(side_effect=AssertionError("Replay must not call live Groq"))
    monkeypatch.setattr(graph_module, "call_groq", external_call)
    # Isolated logical transition only; no global live meeting is touched.
    monkeypatch.setattr(interview_session_service, "get_session", lambda _session_id: None)
    store, repository, m1 = InterviewSessionStore(), InMemoryKnowledgeGraphRepository(), ObservedM1Fixture()
    context = store.get_or_create(
        "observed-conversation-replay", candidate_id="observed-replay-candidate", agent_id="alex",
        missing_competencies=[*TECHNICAL_OBJECTIVES, "product_sense"], metadata={
            "configured_agent_ids": ["alex", "jordan"],
            "required_competencies": [*TECHNICAL_OBJECTIVES, "product_sense"],
            "job_description": "Build software and explain its design and customer benefit.",
            "candidate_profile": {"skills": ["Python"], "projects": [{"name": "learning management system"}]},
            "active_interviewer_question": "What did you personally build in your recent project?",
        },
    )
    MetaOrchestrator.record_question(context, NextAction(
        action=ActionType.ASK_QUESTION, target_agent_id="alex", competency="technical_depth",
        difficulty=DifficultyLevel.MEDIUM, question_text=context.metadata["active_interviewer_question"],
    ))
    orchestrator = MetaOrchestrator()
    orchestrator.decide_async = AsyncMock(wraps=orchestrator.decide_async)
    adapter = CustomLLMAdapter(
        session_store=store, m1_analyzer=m1, orchestrator=orchestrator,
        kg_service=KnowledgeGraphPersistenceService(repository),
        context_builder=AgentTurnContextBuilder(memory_service=CandidateMemoryService(repository)),
    )
    return adapter, context, repository, m1, external_call


async def submit(adapter, context, text, turn_id):
    request = ChatCompletionRequest(messages=[
        {"role": "assistant", "content": context.metadata["active_interviewer_question"]},
        {"role": "user", "content": text},
    ], turn_id=turn_id)
    turn = adapter.parse_turn(request, headers={
        "x-session-id": context.interview_id, "x-agent-id": context.current_agent_id,
    })
    return await adapter.process_turn_async(turn)


def assert_clear_question(text):
    assert text.count("?") == 1
    assert len(text.split()) <= 32
    for phrase in ("core concepts of", "example of concrete", "Which part", "first step you personally took"):
        assert phrase.casefold() not in text.casefold()


def test_actual_confusion_and_weak_answers_do_not_loop_forever(monkeypatch):
    async def run():
        adapter, context, repository, m1, external_call = build_replay(monkeypatch)
        ask_texts = []
        actions = []
        for turn_id, utterance in enumerate(REPLAY, 1):
            before_context = context.model_dump()
            before_graph = deepcopy((repository._nodes, repository._relationships))
            before_calls = len(m1.inputs)
            before_decisions = adapter.orchestrator.decide_async.await_count
            response, action = await submit(adapter, context, utterance, turn_id)
            if utterance in CLARIFICATIONS:
                assert action is None
                assert len(m1.inputs) == before_calls
                assert adapter.orchestrator.decide_async.await_count == before_decisions
                assert context.model_dump() == before_context
                assert (repository._nodes, repository._relationships) == before_graph
                assert response.count("?") == 1
                assert "Which part" not in response
                assert "learning management system" in response
            else:
                assert len(m1.inputs) == before_calls + 1
                assert adapter.orchestrator.decide_async.await_count == before_decisions + 1
                assert action is not None
                actions.append(action)
                if action.action == ActionType.ASK_QUESTION:
                    assert_clear_question(response)
                    ask_texts.append(response)
                    assert action.difficulty == DifficultyLevel.EASY

        # Extend the observed low-confidence admission to test the finite
        # objective budget. This tail is a synthetic regression, not a claim
        # that the original browser participant gave these additional turns.
        for extra in range(20):
            if context.current_agent_id == "jordan":
                break
            response, action = await submit(adapter, context, FINAL_IGNORANCE, 100 + extra)
            assert action is not None
            actions.append(action)
            if action.action == ActionType.ASK_QUESTION:
                assert_clear_question(response)
                ask_texts.append(response)
            assert action.action != ActionType.COMPLETE, "Jordan's configured objective must not be skipped"

        assert context.current_agent_id == "jordan"
        switches = [action for action in actions if action.action == ActionType.SWITCH_AGENT]
        assert len(switches) == 1 and switches[0].target_agent_id == "jordan"
        assert len(m1.inputs) <= 20, "Weak/uncertain answers must eventually exhaust finite Alex objectives"
        assert len(ask_texts) == len(set(ask_texts)), "Changing wording must not recycle an already asked objective"
        objective_ids = [q.metadata["objective_id"] for q in context.question_history if q.metadata.get("objective_id")]
        assert len(objective_ids) == len(set(objective_ids))
        assert all(q.exploration_status != "SUFFICIENT" for q in context.question_history)

        gaps = context.metadata["assessed_insufficient"]
        assert set(TECHNICAL_OBJECTIVES).issubset(gaps)
        assert "product_sense" not in gaps
        assert all(gaps[comp]["status"] == "ASSESSED_INSUFFICIENT" for comp in TECHNICAL_OBJECTIVES)
        assert all(GAP in gaps[comp]["missing_information"] for comp in TECHNICAL_OBJECTIVES)
        assert all(gaps[comp]["performance"] <= 0.3 for comp in TECHNICAL_OBJECTIVES)
        # The only high-confidence answer here describes coding constructs;
        # it is not an admission of inability. The actual inability answers
        # have confidence .2, so every closure must respect the finite budget.
        assert all(item["reason"] == "distinct_objectives_exhausted" for item in gaps.values())

        # Every scored answer, including evidence-free admissions, is persisted
        # with its low observed score. Clarification sentences never become
        # answers/evidence, and handoff must not relabel Alex's final evidence.
        for data in m1.inputs:
            answer = repository.get_answer(data.answer_id)
            assert answer is not None and answer.answer_text == data.answer_text
            assert answer.metadata["overall_performance"] == OBSERVED_QUALITY[data.answer_text][0]
            assert answer.metadata["agent_id"] == "alex"
        assert len(repository._nodes["Answer"]) == len(m1.inputs)
        assert all(answer["answer_text"] not in CLARIFICATIONS for answer in repository._nodes["Answer"].values())
        evidence = repository.get_candidate_evidence(context.candidate_id, limit=100)
        assert evidence and all(item.source_agent_id == "alex" for item in evidence)
        assert all(item.signal not in CLARIFICATIONS for item in evidence)
        external_call.assert_not_called()

    asyncio.run(run())
