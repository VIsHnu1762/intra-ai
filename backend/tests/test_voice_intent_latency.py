"""Intent priority and measurable voice critical-path boundaries."""
import asyncio
from unittest.mock import AsyncMock
import pytest
from app.agents.models import ActionType, NextAction
from app.agent_context.builder import AgentTurnContextBuilder
from app.custom_llm.adapter import CustomLLMAdapter
from app.custom_llm.classifier import FastPathTurnClassifier, TurnIntent
from app.custom_llm.models import ChatCompletionRequest
from app.interview_context.store import InterviewSessionStore
from app.interview_intelligence.models import AnswerAnalysis
from app.knowledge_graph.memory_service import CandidateMemoryService
from app.knowledge_graph.repository import InMemoryKnowledgeGraphRepository
from app.models.enums import DifficultyLevel


@pytest.mark.parametrize('text', [
    'Can we end the interview?', 'I want to stop the interview.', 'Can we finish here?',
    "I'd like to end this.", "I don't want to continue.", 'Can we stop?',
    'I need to leave.', "Let's end the interview.",
    "I don't know Kafka. Can we end the interview?",
])
def test_explicit_end_takes_priority(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.END_INTERVIEW


@pytest.mark.parametrize('text', [
    'We stop the Kafka consumer before deployment.', 'Can we stop the server without losing messages?',
    "I don't want to end the interview.", 'If I need to leave, I notify the team.',
    'The customer said I want to stop the interview.',
])
def test_technical_hypothetical_and_negated_end_are_answers(text):
    assert FastPathTurnClassifier().classify(text).intent == TurnIntent.INTERVIEW_ANSWER


def setup_adapter():
    store = InterviewSessionStore()
    context = store.get_or_create('voice-policy', candidate_id='candidate-1', agent_id='alex',
        missing_competencies=['system_design'], metadata={
            'active_interviewer_question': 'How would you scale your Kafka payment system?',
            'job_description': 'Build reliable Kafka payment systems.',
            'candidate_profile': {'skills': ['Kafka', 'PostgreSQL']},
        })
    m1, orch, kg = AsyncMock(), AsyncMock(), AsyncMock()
    m1.analyze_async.return_value = AnswerAnalysis(answer_id='a1', overall_performance=.5,
        confidence=.9, vague=False, contradiction_detected=False)
    orch.decide_async.return_value = NextAction(action=ActionType.ASK_QUESTION,
        target_agent_id='alex', competency='system_design', difficulty=DifficultyLevel.MEDIUM,
        question_text='How would you recover a failed Kafka consumer?')
    builder = AgentTurnContextBuilder(memory_service=CandidateMemoryService(InMemoryKnowledgeGraphRepository()))
    return CustomLLMAdapter(session_store=store, m1_analyzer=m1, orchestrator=orch,
        kg_service=kg, context_builder=builder, background_kg_persistence=True), context, m1, orch, kg


def make_turn(adapter, text):
    return adapter.parse_turn(ChatCompletionRequest(messages=[
        {'role': 'assistant', 'content': 'How would you scale your Kafka payment system?'},
        {'role': 'user', 'content': text, 'turn_id': 7, 'timestamp': 1788642451407,
         'metadata': {'speech_timing': {'speech_end_ms': 1788642450460}}},
    ], turn_id=7), headers={'x-session-id': 'voice-policy', 'x-agent-id': 'alex'})


def test_end_completes_without_evaluating_or_asking_more():
    async def run():
        adapter, ctx, m1, orch, _ = setup_adapter()
        text, action = await adapter.process_turn_async(make_turn(adapter, 'Can we end the interview?'))
        assert action.action == ActionType.COMPLETE
        assert text == 'Absolutely. Thanks for your time today.'
        assert ctx.metadata['completed'] is True
        assert ctx.metadata['completion_reason'] == 'candidate_requested'
        assert ctx.accumulated_evidence == []
        m1.analyze_async.assert_not_called()
        orch.decide_async.assert_not_called()
        assert await adapter.process_turn_async(make_turn(adapter, 'Actually I used Kafka.')) == ('', None)
    asyncio.run(run())


@pytest.mark.parametrize('terminal', ['finish_reason', '[DONE]', 'non_stream'])
def test_end_lifecycle_survives_consumer_close_at_terminal(terminal):
    async def run():
        adapter, _, _, _, _ = setup_adapter()
        observer = AsyncMock()
        adapter._response_lifecycle = lambda *args: observer
        turn = make_turn(adapter, 'Can we end the interview?')
        if terminal == 'non_stream':
            await adapter.generate_response_async(turn)
        else:
            stream = adapter.generate_stream(turn)
            async for chunk in stream:
                if ((terminal == 'finish_reason' and '"finish_reason":"stop"' in chunk)
                        or (terminal == '[DONE]' and '[DONE]' in chunk)):
                    await stream.aclose()
                    break
        await adapter.drain_background_tasks()
        observer.assert_awaited_once()
    asyncio.run(run())


@pytest.mark.parametrize('utterance, expected', [
    ('Could you repeat that?', 'Kafka payment'),
    ('What do you mean by scalability?', 'more users'),
    ('Can we take a short break?', 'take your time'),
])
def test_controls_preserve_evidence_and_difficulty(utterance, expected):
    async def run():
        adapter, ctx, m1, orch, _ = setup_adapter()
        text, action = await adapter.process_turn_async(make_turn(adapter, utterance))
        assert expected in text and action is None
        assert not ctx.accumulated_evidence and ctx.difficulty == DifficultyLevel.MEDIUM
        m1.analyze_async.assert_not_called()
        orch.decide_async.assert_not_called()
    asyncio.run(run())


@pytest.mark.parametrize('utterance', ['Hello.', '  hello  ', 'Hi!', 'Hey?'])
def test_greeting_does_not_consume_an_answer_or_advance_question(utterance):
    async def run():
        adapter, ctx, m1, orch, _ = setup_adapter()
        previous = ctx.metadata['active_interviewer_question']
        text, action = await adapter.process_turn_async(make_turn(adapter, utterance))
        assert text == "I'm here and ready to listen."
        assert action is None and ctx.accumulated_evidence == []
        assert ctx.metadata['active_interviewer_question'] == previous
        m1.analyze_async.assert_not_called()
        orch.decide_async.assert_not_called()
    asyncio.run(run())


def test_greeting_with_substantive_answer_is_still_evaluated():
    assert FastPathTurnClassifier().classify(
        'Hello. I integrated the Razorpay SDK in our checkout page.'
    ).intent == TurnIntent.INTERVIEW_ANSWER


def test_reads_overlap_m1_and_graph_write_does_not_block_content():
    async def run():
        adapter, ctx, m1, orch, kg = setup_adapter()
        reading, analyzing, writing, release = (asyncio.Event() for _ in range(4))
        builder = adapter.context_builder.build_turn_context_async
        async def build(**kwargs):
            reading.set()
            await analyzing.wait()
            return await builder(**kwargs)
        analysis = m1.analyze_async.return_value
        async def analyze(data):
            analyzing.set()
            await reading.wait()
            assert data.job_description == ctx.metadata['job_description']
            assert data.candidate_profile['skills'] == ['Kafka', 'PostgreSQL']
            return analysis
        async def persist(**kwargs):
            writing.set()
            await release.wait()
            assert kwargs['context'].current_agent_id == 'alex'
        adapter.context_builder.build_turn_context_async = build
        m1.analyze_async.side_effect = analyze
        kg.persist_turn_evaluation_async.side_effect = persist
        turn = make_turn(adapter, 'Kafka consumers replay committed offsets using PostgreSQL idempotency keys.')
        async def consume():
            return [chunk async for chunk in adapter.generate_stream(turn)]
        chunks = await asyncio.wait_for(consume(), timeout=1)
        assert chunks[-1] == 'data: [DONE]\n\n' and 'Kafka' in ''.join(chunks)
        await writing.wait()
        assert adapter._background_tasks
        ctx.current_agent_id = 'jordan'
        release.set()
        await adapter.drain_background_tasks()
        orch.decide_async.assert_awaited_once()
        assert ctx.question_history[-1].question_text == 'How would you recover a failed Kafka consumer?'
        for stage in ('custom_llm_received', 'context_start', 'context_complete', 'm1_start', 'm1_complete',
                      'orchestrator_start', 'orchestrator_complete', 'first_response_chunk_sent', 'response_stream_complete'):
            assert stage in turn.metadata['timings']
        assert turn.metadata['agora_turn_id'] == 7
        assert turn.metadata['stt_final_timestamp_ms'] == 1788642451407
    asyncio.run(run())


def test_handoff_greeting_uses_evidence_instead_of_last_clarification():
    from app.custom_llm.adapter import generate_handoff_question
    from app.agents.registry import agent_registry
    _, context, _, _, _ = setup_adapter()
    context.metadata['last_candidate_answer'] = "So that's called as a trade-off?"
    jordan = agent_registry.get_profile('jordan')
    text = generate_handoff_question(jordan, context, 'product_sense')
    assert 'Earlier you' not in text and 'trade-off?' not in text
    assert 'Who was the main user' in text and text.count('?') == 1
    context.add_evidence({'competency': 'system_design', 'signal': 'Explained merchant payment processing with Kafka.',
                          'source_agent_id': 'alex', 'score': 8, 'metadata': {'subject': 'payment ledger'}})
    text = generate_handoff_question(jordan, context, 'product_sense')
    assert 'Earlier you described payment ledger.' in text
    assert 'Who was the main user of that work?' in text and text.count('?') == 1
