"""Empty Agora ASR turns must never replay an older answer or restart questions."""
import json
from unittest.mock import AsyncMock

import pytest
from structlog.testing import capture_logs

from app.custom_llm.adapter import CustomLLMAdapter, extract_candidate_turn
from app.custom_llm.classifier import FastPathTurnClassifier, TurnIntent
from app.custom_llm.models import ChatCompletionRequest, ChatMessage
from app.interview_context.store import InterviewSessionStore


@pytest.mark.parametrize('latest', ['', '   ', None])
def test_latest_blank_user_is_not_replaced_with_an_older_answer(latest):
    messages = [ChatMessage(role='assistant', content='How did Redis help?'),
                ChatMessage(role='user', content='We added a Redis cache.'),
                ChatMessage(role='assistant', content='How did you invalidate it?'),
                ChatMessage(role='user', content=latest)]
    assert extract_candidate_turn(messages) == ('', 'How did you invalidate it?')


def setup_adapter():
    store = InterviewSessionStore()
    ctx = store.get_or_create('empty-asr', candidate_id='empty-asr-candidate', agent_id='alex',
                             missing_competencies=['system_design'])
    m1, orch, kg, builder = (AsyncMock() for _ in range(4))
    adapter = CustomLLMAdapter(session_store=store, m1_analyzer=m1, orchestrator=orch,
                               kg_service=kg, context_builder=builder)
    return adapter, ctx, m1, orch, kg, builder


@pytest.mark.asyncio
@pytest.mark.parametrize('with_prior_answer', [False, True])
async def test_ongoing_blank_callback_emits_no_speech_and_leaves_context_untouched(with_prior_answer):
    adapter, ctx, m1, orch, kg, builder = setup_adapter()
    ctx.metadata.update(active_interviewer_question='How did you invalidate the cache?', paused=True)
    messages = []
    if with_prior_answer:
        messages += [{'role': 'assistant', 'content': 'Describe your caching system.'},
                     {'role': 'user', 'content': 'We used Redis cache-aside with transaction invalidation.'}]
    messages += [{'role': 'assistant', 'content': 'How did you invalidate the cache?'},
                 {'role': 'user', 'content': '', 'turn_id': 6}]
    turn = adapter.parse_turn(ChatCompletionRequest(messages=messages, turn_id=6),
                               headers={'x-session-id': ctx.interview_id, 'x-agent-id': 'alex'})
    before = ctx.model_dump()
    with capture_logs() as logs:
        chunks = [chunk async for chunk in adapter.generate_stream(turn)]
    assert turn.latest_user_message == ''
    assert ctx.model_dump() == before
    assert chunks[-1] == 'data: [DONE]\n\n'
    content = ''.join((json.loads(chunk[6:])['choices'][0]['delta'].get('content') or '')
                      for chunk in chunks if chunk.startswith('data: {'))
    assert content == ''
    assert any(log['event'] == '[EMPTY_CANDIDATE_TURN_IGNORED]' for log in logs)
    m1.analyze_async.assert_not_awaited()
    orch.decide_async.assert_not_awaited()
    kg.persist_turn_evaluation_async.assert_not_awaited()
    builder.build_turn_context_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_real_greeting_in_history_prevents_repeated_blank_opening():
    adapter, ctx, m1, _, _, _ = setup_adapter()
    # Session context has no evidence yet, but Agora already spoke the question.
    turn = adapter.parse_turn(ChatCompletionRequest(messages=[
        {'role': 'assistant', 'content': "Hello! I'm Alex. Could you describe your project?"},
        {'role': 'user', 'content': ''},
    ]), headers={'x-session-id': ctx.interview_id})
    assert await adapter.process_turn_async(turn) == ('', None)
    assert not ctx.question_history
    m1.analyze_async.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('seed', [[], [{'role': 'assistant', 'content': "Hello! I am Alex. I'm ready for our interview."}]])
async def test_initial_blank_handshake_still_gets_one_opening(seed):
    adapter, ctx, m1, _, _, _ = setup_adapter()
    request = ChatCompletionRequest(messages=[*seed, {'role': 'user', 'content': ''}])
    turn = adapter.parse_turn(request, headers={'x-session-id': ctx.interview_id})
    response, _ = await adapter.process_turn_async(turn)
    assert "I'm Alex" in response and '?' in response
    assert len(ctx.question_history) == 1
    repeat = adapter.parse_turn(request, headers={'x-session-id': ctx.interview_id})
    assert await adapter.process_turn_async(repeat) == ('', None)
    assert len(ctx.question_history) == 1
    m1.analyze_async.assert_not_awaited()


@pytest.mark.parametrize('text', [
    "I haven't worked on payment ledger, but I have worked on LMS system. One simple example of what?",
    'One simple example of what?', 'An example of what exactly',
])
def test_explicit_example_question_is_clarification(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.CLARIFICATION


@pytest.mark.parametrize('text', [
    "I haven't worked on payment ledger, but I have worked on LMS system.",
    'I gave one simple example of what the Redis cache stores.',
    'The interviewer asked: one simple example of what?',
])
def test_project_correction_or_reported_question_remains_answer(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.INTERVIEW_ANSWER
