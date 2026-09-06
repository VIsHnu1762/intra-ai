"""The service name after a cut-off answer belongs to the original question."""
from copy import deepcopy

import pytest

from app.custom_llm.adapter import extract_candidate_turn
from app.custom_llm.classifier import FastPathTurnClassifier, TurnIntent
from app.custom_llm.models import ChatCompletionRequest, ChatMessage
from tests.test_voice_intent_latency import setup_adapter


QUESTION = 'Which parts of your application did you implement yourself?'
FRAGMENT = ('Regarding the LLM system, I built it with FastAPI, React front-end, '
            'Postgres backend, and for question generation we used an external service like a—')


def messages(*texts):
    return [ChatMessage(role='assistant', content=QUESTION),
            *[ChatMessage(role='user', content=text) for text in texts]]


@pytest.mark.parametrize('text', [FRAGMENT, 'Our API calls an external service using…',
                                  'I used React. The model is provided through the—'])
def test_explicit_unfinished_connector_is_not_an_assessable_completed_turn(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.INCOMPLETE_ANSWER


def test_short_continuation_is_joined_to_original_answer_even_with_empty_assistant():
    history = messages(FRAGMENT)
    history += [ChatMessage(role='assistant', content=''), ChatMessage(role='user', content='Canva.')]
    answer, question = extract_candidate_turn(history)
    assert answer == FRAGMENT[:-1] + ' Canva.'
    assert question == QUESTION


def test_full_restatement_replaces_unfinished_prefix_without_duplication():
    complete = FRAGMENT[:-1] + ' hosted model.'
    assert extract_candidate_turn(messages(FRAGMENT, complete))[0] == complete


@pytest.mark.parametrize('new_answer', ['', 'Stop the interview.', 'Can you repeat the question?'])
def test_empty_or_control_turn_never_replays_an_unfinished_answer(new_answer):
    assert extract_candidate_turn(messages(FRAGMENT, new_answer))[0] == new_answer


def test_completed_answers_and_spoken_assistant_responses_are_hard_boundaries():
    assert extract_candidate_turn(messages('We used Redis—', 'Canva.'))[0] == 'Canva.'
    history = messages(FRAGMENT) + [ChatMessage(role='assistant', content='What did you test?'),
                                  ChatMessage(role='user', content='Canva.')]
    assert extract_candidate_turn(history) == ('Canva.', 'What did you test?')


@pytest.mark.asyncio
async def test_partial_then_service_name_calls_analysis_once_for_original_question():
    adapter, context, m1, orchestrator, kg = setup_adapter()
    context.metadata['active_interviewer_question'] = QUESTION
    before = deepcopy(context.model_dump())
    history = messages(FRAGMENT)
    turn = adapter.parse_turn(ChatCompletionRequest(messages=history),
        headers={'x-session-id': context.interview_id, 'x-agent-id': 'alex'})
    text, action = await adapter.process_turn_async(turn)
    assert text == '' and action is None
    assert context.model_dump() == before
    m1.analyze_async.assert_not_called()
    orchestrator.decide_async.assert_not_called()
    kg.persist_turn_evaluation_async.assert_not_called()

    history += [ChatMessage(role='user', content='Canva.')]
    turn = adapter.parse_turn(ChatCompletionRequest(messages=history),
        headers={'x-session-id': context.interview_id, 'x-agent-id': 'alex'})
    await adapter.process_turn_async(turn)
    await adapter.drain_background_tasks()
    m1.analyze_async.assert_awaited_once()
    input_data = m1.analyze_async.call_args.args[0]
    assert input_data.question_text == QUESTION
    assert input_data.answer_text == FRAGMENT[:-1] + ' Canva.'
    orchestrator.decide_async.assert_awaited_once()
    kg.persist_turn_evaluation_async.assert_awaited_once()
