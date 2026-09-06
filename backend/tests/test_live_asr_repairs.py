"""Fresh browser repairs/hesitations must not consume assessment objectives."""

import asyncio

import pytest

from app.custom_llm.classifier import FastPathTurnClassifier, TurnIntent
from app.agents.models import NextAction
from app.models.enums import ActionType
from app.orchestrator.service import MetaOrchestrator
from tests.test_voice_intent_latency import make_turn, setup_adapter


@pytest.mark.parametrize("text", [
    "Can you come again?", "Could you come again?", "Come again?",
    "Sorry, can you come again?", "Could you please come again?",
    "Would you come again, please?", "Please come again.",
])
def test_live_come_again_repeats_without_provider_call_or_assessment(text):
    async def run():
        adapter, context, m1, orchestrator, graph = setup_adapter()
        assert adapter.classifier.classify(text).intent == TurnIntent.REPEAT_QUESTION
        question = "What number could show whether your LMS helped a user?"
        context.metadata["active_interviewer_question"] = question
        before = context.model_dump()
        response, action = await adapter.process_turn_async(make_turn(adapter, text))
        assert question in response and response.count("?") == 1
        assert action is None and context.model_dump() == before
        m1.analyze_async.assert_not_called()
        orchestrator.decide_async.assert_not_called()
        graph.persist_turn_evaluation_async.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("text", [
    "The customer asked can you come again.",
    "I asked the user to come again after testing the prototype.",
    "Can you come again? We used Redis to cache database queries.",
    "If users come again, our retention metric increases.",
    "I don't know whether they will come again.",
])
def test_reported_or_substantive_come_again_remains_an_answer(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.INTERVIEW_ANSWER


@pytest.mark.parametrize("text", ["continue", "Continue.", "resume", "Resume!", "Please continue", "Please resume."])
def test_bare_resume_control_matches_the_spoken_service_pause_instruction(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.CONTINUE_INTERVIEW


@pytest.mark.parametrize("text", [
    "We continue processing Kafka messages after recovery.",
    "Continue processing the database transaction after acquiring the lock.",
    "The customer said continue.",
    "If we resume the interview, I would explain my architecture.",
    "I don't want to continue processing failed events.",
    "My resume lists Python and PostgreSQL.",
])
def test_technical_and_reported_continue_remains_answer_content(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.INTERVIEW_ANSWER


@pytest.mark.parametrize("text", [
    "Like, my code— What are you asking specifically? I can't understand.",
    "Like, my code – what exactly are you asking?",
    "My code - what are you asking exactly?",
    "What?",
    "Sorry, what?",
    "What exactly?",
    "What specifically are you asking me?",
])
def test_question_repair_is_clarification_despite_abandoned_answer_prefix(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.CLARIFICATION


@pytest.mark.parametrize("text", [
    "So the limitations were—",
    "Like, my code—",
    "My implementation was...",
    "The output is…",
    "We used a—",
    "I built the—",
])
def test_unfinished_subject_or_predicate_waits_for_candidate_completion(text):
    result = FastPathTurnClassifier().classify(text)
    assert result.intent == TurnIntent.INCOMPLETE_ANSWER
    assert result.is_control_turn


@pytest.mark.parametrize("text", [
    "I don't know.",
    "I don't know—",
    "I don't understand Kafka.",
    "I can't understand distributed consensus.",
    "So the limitations were higher latency—",
    "My code failed—",
    "Our code processes input—",
    "I built a cache—",
    "We used Redis—",
    "I built a cache. The limitations were—",
    "We asked—what are you asking specifically?",
    "My manager asked—what exactly are you asking?",
    "If a customer said—what?—I would explain the feature.",
    "I used the variable called what?",
    "The limitations were higher latency and less throughput.",
])
def test_complete_ignorance_reported_and_technical_answers_remain_scored(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.INTERVIEW_ANSWER


@pytest.mark.parametrize("text", [
    "Like, my code— What are you asking specifically? I can't understand.",
    "What?",
])
def test_live_question_repair_does_not_advance_or_score(text):
    async def run():
        adapter, context, m1, orchestrator, graph = setup_adapter()
        before = context.model_dump()
        response, action = await adapter.process_turn_async(make_turn(adapter, text))
        assert response.count("?") == 1
        assert action is None
        assert context.model_dump() == before
        m1.analyze_async.assert_not_called()
        orchestrator.decide_async.assert_not_called()
        graph.persist_turn_evaluation_async.assert_not_called()

    asyncio.run(run())


def test_unfinished_fragment_then_full_answer_scores_only_the_completion():
    async def run():
        adapter, context, m1, orchestrator, graph = setup_adapter()
        before = context.model_dump()
        for fragment in ("Like, my code—", "So the limitations were—"):
            response, action = await adapter.process_turn_async(make_turn(adapter, fragment))
            assert response == "" and action is None
            assert context.model_dump() == before
            m1.analyze_async.assert_not_called()
            orchestrator.decide_async.assert_not_called()
            graph.persist_turn_evaluation_async.assert_not_called()

        full_answer = "So the limitations were higher latency because every request waited for a database write."
        response, action = await adapter.process_turn_async(make_turn(adapter, full_answer))
        await adapter.drain_background_tasks()
        assert response and action is not None
        m1.analyze_async.assert_awaited_once()
        assert m1.analyze_async.call_args.args[0].answer_text == full_answer
        orchestrator.decide_async.assert_awaited_once()
        graph.persist_turn_evaluation_async.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize("competency,expected", [
    ("scalability", "ten times as many people"),
    ("coding_problem_solving", "one coding problem you solved yourself"),
])
def test_bare_what_rephrases_active_competency_using_supported_cv_subject(competency, expected):
    async def run():
        adapter, context, m1, orchestrator, graph = setup_adapter()
        context.metadata["candidate_profile"]["projects"] = [{"name": "learning management system"}]
        context.metadata["last_candidate_answer"] = "I don't know Redis."
        active = "Could you describe your approach in detail?"
        context.metadata["active_interviewer_question"] = active
        MetaOrchestrator.record_question(context, NextAction(
            action=ActionType.ASK_QUESTION, target_agent_id="alex", competency=competency,
            difficulty=context.difficulty, question_text=active,
        ))
        before = context.model_dump()
        response, action = await adapter.process_turn_async(make_turn(adapter, "What?"))
        assert action is None and response.count("?") == 1
        assert expected in response
        assert "learning management system" in response
        assert "Redis" not in response
        assert active not in response and "Which part" not in response
        assert context.model_dump() == before
        m1.analyze_async.assert_not_called()
        orchestrator.decide_async.assert_not_called()
        graph.persist_turn_evaluation_async.assert_not_called()

    asyncio.run(run())
