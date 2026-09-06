"""Control utterances cannot replace the question attached to a real answer."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent_context.builder import AgentTurnContextBuilder
from app.agents.models import NextAction
from app.custom_llm.adapter import CustomLLMAdapter
from app.custom_llm.models import ChatCompletionRequest
from app.interview_context.models import EvidenceItem
from app.interview_context.store import InterviewSessionStore
from app.interview_intelligence.models import AnswerAnalysis
from app.knowledge_graph.memory_service import CandidateMemoryService
from app.knowledge_graph.repository import InMemoryKnowledgeGraphRepository
from app.knowledge_graph.service import KnowledgeGraphPersistenceService
from app.models.enums import ActionType, DifficultyLevel


OPENING = "What did you personally build in your project?"
ANSWER = "I built an LMS software using FastAPI and Postgres backend."
FOLLOWUP = "What did you use FastAPI to build in your LMS?"


@pytest.fixture
def interview():
    store = InterviewSessionStore()
    context = store.get_or_create(
        "question-identity", candidate_id="candidate-identity", agent_id="alex",
        missing_competencies=["system_design"],
        metadata={"active_interviewer_question": OPENING},
    )
    analysis = AnswerAnalysis(
        answer_id="lms-answer", overall_performance=.6, confidence=.9,
        vague=False, contradiction_detected=False,
        evidence=[EvidenceItem(id="lms-evidence", competency="system_design",
                               signal="Candidate built an LMS using FastAPI and Postgres.")],
    )
    m1 = SimpleNamespace(analyze_async=AsyncMock(return_value=analysis))
    orchestrator = SimpleNamespace(decide_async=AsyncMock(return_value=NextAction(
        action=ActionType.ASK_QUESTION, target_agent_id="alex", competency="system_design",
        difficulty=DifficultyLevel.EASY, question_text=FOLLOWUP,
    )))
    repository = InMemoryKnowledgeGraphRepository()
    builder = AgentTurnContextBuilder(memory_service=CandidateMemoryService(repository))
    builder.build_turn_context_async = AsyncMock(wraps=builder.build_turn_context_async)
    adapter = CustomLLMAdapter(
        session_store=store, m1_analyzer=m1, orchestrator=orchestrator,
        context_builder=builder,
        kg_service=KnowledgeGraphPersistenceService(repository),
        background_kg_persistence=False,
    )
    return SimpleNamespace(adapter=adapter, context=context, m1=m1, orchestrator=orchestrator,
                           builder=builder, repository=repository)


async def speak(interview, history, answer):
    history.append({"role": "user", "content": answer})
    turn = interview.adapter.parse_turn(
        ChatCompletionRequest(messages=history),
        headers={"x-session-id": interview.context.interview_id, "x-agent-id": "alex"},
    )
    text, action = await interview.adapter.process_turn_async(turn)
    history.append({"role": "assistant", "content": text})
    return text, action


def assert_answer_question(interview, expected):
    evaluated = interview.m1.analyze_async.await_args.args[0]
    assert evaluated.question_text == expected
    assert evaluated.answer_text == ANSWER
    assert interview.builder.build_turn_context_async.await_args.kwargs["current_question"] == expected
    routing = interview.orchestrator.decide_async.await_args.kwargs
    assert routing["current_question_text"] == expected
    assert routing["turn_context"].current_question == expected
    assert routing["turn_context"].current_answer == ANSWER
    saved_answer = interview.repository.get_answer("lms-answer")
    assert saved_answer is not None and saved_answer.answer_text == ANSWER
    assert interview.repository.get_question(saved_answer.question_id).question_text == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("control", [
    "Hello.", "Hi Alex.", "Can you hear me?", "Could you repeat that?",
    "Can we take a short break?",
])
async def test_control_reply_does_not_become_the_assessed_or_persisted_question(interview, control):
    history = [{"role": "assistant", "content": OPENING}]
    _, action = await speak(interview, history, control)
    assert action is None
    assert interview.context.metadata["active_interviewer_question"] == OPENING
    interview.m1.analyze_async.assert_not_awaited()
    response, _ = await speak(interview, history, ANSWER)
    assert_answer_question(interview, OPENING)
    assert response == FOLLOWUP
    assert interview.context.metadata["active_interviewer_question"] == FOLLOWUP


@pytest.mark.asyncio
async def test_new_real_question_remains_authoritative_after_another_control(interview):
    history = [{"role": "assistant", "content": OPENING}]
    await speak(interview, history, ANSWER)
    await speak(interview, history, "Hello.")
    await speak(interview, history, ANSWER)
    assert_answer_question(interview, FOLLOWUP)


@pytest.mark.asyncio
async def test_incoming_question_is_retained_when_session_has_no_active_question(interview):
    interview.context.metadata.pop("active_interviewer_question")
    history = [{"role": "assistant", "content": OPENING}]
    await speak(interview, history, ANSWER)
    assert_answer_question(interview, OPENING)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["analysis", "routing"])
async def test_outage_resume_retries_the_original_question_and_answer_after_controls(interview, stage):
    history = [{"role": "assistant", "content": OPENING}]
    await speak(interview, history, "Hello.")
    failing_call = (interview.m1.analyze_async if stage == "analysis"
                    else interview.orchestrator.decide_async)
    failing_call.side_effect = RuntimeError("provider temporarily unavailable")
    response, action = await speak(interview, history, ANSWER)
    assert action is None and "temporarily unavailable" in response
    paused = interview.context.metadata["service_pause"]
    assert paused["question"] == OPENING and paused["answer"] == ANSWER
    assert interview.repository.get_answer("lms-answer") is None

    await speak(interview, history, "Can you hear me?")
    paused["retry_at"] = 0
    failing_call.side_effect = None
    await speak(interview, history, "continue")
    assert_answer_question(interview, OPENING)
    assert "service_pause" not in interview.context.metadata
