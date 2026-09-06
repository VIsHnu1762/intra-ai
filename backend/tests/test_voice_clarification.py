"""Actual browser clarification utterances must never become scored answers."""

import asyncio

import pytest

from app.custom_llm.classifier import FastPathTurnClassifier, TurnIntent
from app.custom_llm.intent_policy import clarification_response
from tests.test_voice_intent_latency import make_turn, setup_adapter


LIVE_CLARIFICATIONS = [
    "Technical details and trade-off, in a sense, what we're asking: can you simplify?",
    "I can't understand what you're asking. Like, what do you mean by the technical detail and trade-offs?",
    "So that's called as a trade-off?",
]

FRESH_ROOM_CLARIFICATIONS = [
    "One simple example of the project that I worked on?",
    "What are you asking? I can't understand.",
    "For scalability of what?",
]


@pytest.mark.parametrize("utterance", LIVE_CLARIFICATIONS + FRESH_ROOM_CLARIFICATIONS + [
    "Could you simplify the question?",
    "Can you rephrase that in simpler terms?",
    "I don't understand your question.",
    "Like, what do you mean by scalability?",
    "Is that called a tradeoff?",
    "Please clarify the question.",
    "An example of my application?",
    "One concrete example of the system we built?",
    "Scalability of which project?",
    "Sorry, what are you asking me about",
])
def test_direct_clarification_request_precedes_technical_vocabulary(utterance):
    assert FastPathTurnClassifier().classify(utterance).intent == TurnIntent.CLARIFICATION


@pytest.mark.parametrize("utterance", [
    "I don't understand Kafka.",
    "I can't understand distributed consensus.",
    "I don't know how that works.",
    "I am not sure which database we used.",
    "We simplified the architecture by removing a queue.",
    "The customer asked: can you simplify?",
    "If you ask me to simplify, I would remove the cache.",
    "That is called a trade-off.",
    "We traded consistency for latency, and that's called a trade-off.",
    "I can't understand Kafka, but I implemented the API.",
    "Our client said what do you mean by scalability?",
    "That's called a trade-off. We made that choice because it reduced latency?",
    "One simple example of the project that I worked on.",
    "The customer asked: for scalability of what?",
    "The interviewer asked: one simple example of the project that I worked on?",
    "Our manager asked what are you asking?",
    "If you ask for scalability of what, I would say the database.",
    "We questioned the scalability of what we built?",
    "I don't understand scalability.",
    "I can't understand Kafka. We used it for event delivery.",
    "For scalability, I partitioned the database by customer ID.",
])
def test_ignorance_answers_and_reported_requests_remain_interview_content(utterance):
    assert FastPathTurnClassifier().classify(utterance).intent == TurnIntent.INTERVIEW_ANSWER


@pytest.mark.parametrize("utterance", [
    "Can you simplify? Actually, can we end the interview?",
    "What do you mean by trade-offs? I need to leave.",
    "I don't understand your question. Can we stop?",
])
def test_end_retains_priority_over_an_earlier_clarification(utterance):
    assert FastPathTurnClassifier().classify(utterance).intent == TurnIntent.END_INTERVIEW


def test_live_clarifications_do_not_score_change_difficulty_or_handoff():
    async def run():
        adapter, context, m1, orchestrator, graph = setup_adapter()
        context.metadata["active_interviewer_question"] = "Describe the technical details and trade-offs of your payment ledger."
        before = context.model_dump()
        for utterance in LIVE_CLARIFICATIONS:
            response, action = await adapter.process_turn_async(make_turn(adapter, utterance))
            assert action is None
            assert "benefit you gain" in response
            assert "cost or limitation" in response
            assert context.model_dump() == before
        m1.analyze_async.assert_not_called()
        orchestrator.decide_async.assert_not_called()
        graph.persist_turn_evaluation_async.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("term", ["trade-off", "trade-offs", "tradeoff", "tradeoffs", "trade off", "trade offs"])
def test_trade_off_singular_plural_and_asr_spellings_explain_same_concept(term):
    response = clarification_response(f"What do you mean by {term}?", None)
    assert response.startswith("A trade-off is a benefit you gain")
    assert "Which part" not in response


def test_simplification_uses_the_active_question_term_without_repeating_its_complexity():
    response = clarification_response("Can you simplify?", "Explain architectural trade-offs, throughput and recovery.")
    assert "benefit you gain" in response
    assert "Explain architectural" not in response


@pytest.mark.parametrize("utterance,question,competency,expected", [
    (FRESH_ROOM_CLARIFICATIONS[0], "Let's start with technical depth. Can you give one simple example?", "technical_depth", "what part did you personally build"),
    (FRESH_ROOM_CLARIFICATIONS[1], "Can you give one concrete example of Concrete coding problem example?", "coding_problem_solving", "one coding problem you solved yourself"),
    (FRESH_ROOM_CLARIFICATIONS[2], "For scalability, what was the first step you personally took?", "scalability", "ten times as many people"),
])
def test_fresh_clarification_asks_one_concrete_grounded_question(utterance, question, competency, expected):
    response = clarification_response(utterance, question, competency=competency, subject="your learning management system")
    assert expected in response
    assert "your learning management system" in response
    assert response.count("?") == 1
    assert "Which part" not in response
    assert question not in response
    assert "payment ledger" not in response


def test_clarification_without_supported_subject_invites_real_experience():
    response = clarification_response("What are you asking?", None, competency="coding_problem_solving")
    assert "a project you worked on" in response
    assert "one coding problem you solved yourself" in response
    assert response.count("?") == 1


def test_product_persona_generic_clarification_asks_about_user_problem():
    response = clarification_response("Can you simplify?", None, agent_role="Senior Product Manager", subject="your scheduling tool")
    assert response == "What problem did your scheduling tool solve for the people using it?"


@pytest.mark.parametrize("subject", [None, "", "What are you asking?", "x" * 151])
def test_invalid_subject_does_not_invent_or_echo_an_experience(subject):
    response = clarification_response("For scalability of what?", None, subject=subject)
    assert "In a project you worked on" in response
    assert response.count("?") == 1


@pytest.mark.parametrize("utterance", FRESH_ROOM_CLARIFICATIONS)
def test_fresh_browser_clarifications_never_score_or_modify_interview(utterance):
    async def run():
        adapter, context, m1, orchestrator, graph = setup_adapter()
        context.metadata["active_interviewer_question"] = "For scalability, what was the first step you personally took?"
        before = context.model_dump()
        response, action = await adapter.process_turn_async(make_turn(adapter, utterance))
        assert action is None
        assert response.count("?") == 1
        assert "Which part" not in response
        assert context.model_dump() == before
        m1.analyze_async.assert_not_called()
        orchestrator.decide_async.assert_not_called()
        graph.persist_turn_evaluation_async.assert_not_called()

    asyncio.run(run())
