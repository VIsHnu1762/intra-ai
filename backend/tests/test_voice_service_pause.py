"""Live 429s cannot become repeated assessment questions or scored retries."""
import asyncio

from app.agents.models import NextAction
from app.integrations.groq_client import GroqAPIError
from app.interview_intelligence.provider import M1ProviderError
from app.models.enums import ActionType, DifficultyLevel
from tests.test_voice_turn_cancellation import prepared_adapter
from tests.test_voice_intent_latency import make_turn


def test_provider_quota_pauses_without_scoring_and_retries_original_answer_only_on_resume():
    async def run():
        adapter, context, m1, orchestrator, kg = prepared_adapter()
        answer = 'Kafka consumers replay offsets with PostgreSQL idempotency keys.'
        provider_error = GroqAPIError('resource exhausted', category='RESOURCE_EXHAUSTED',
                                     provider_status_code=429, retry_after_seconds=30)
        wrapper = M1ProviderError('analysis unavailable')
        wrapper.__cause__ = provider_error
        m1.analyze_async.side_effect = wrapper
        before_questions = list(context.question_history)
        response, action = await adapter.process_turn_async(make_turn(adapter, answer))
        assert action is None and '?' not in response
        assert 'service is temporarily unavailable' in response
        assert context.metadata['service_pause']['provider_status'] == 429
        assert context.metadata['service_pause']['answer'] == answer
        assert context.question_history == before_questions
        assert context.accumulated_evidence == []
        assert await adapter.process_turn_async(make_turn(adapter, 'We used Kafka.')) == ('', None)
        early, _ = await adapter.process_turn_async(make_turn(adapter, 'continue'))
        assert 'Please wait' in early and '?' not in early
        m1.analyze_async.assert_awaited_once()
        orchestrator.decide_async.assert_not_awaited()
        kg.persist_turn_evaluation_async.assert_not_awaited()

        # The provider's cooldown elapsed; explicit continue retries the saved
        # answer and cannot evaluate the control word or duplicate an old score.
        context.metadata['service_pause']['retry_at'] = 0
        m1.analyze_async.side_effect = None
        orchestrator.decide_async.return_value = NextAction(action=ActionType.ASK_QUESTION,
            target_agent_id='alex', competency='system_design', difficulty=DifficultyLevel.MEDIUM,
            question_text='What happens if a worker stops before committing its offset?')
        response, action = await adapter.process_turn_async(make_turn(adapter, 'continue'))
        assert m1.analyze_async.await_args.args[0].answer_text == answer
        assert m1.analyze_async.await_count == 2
        assert 'service_pause' not in context.metadata and context.metadata['paused'] is False
        assert len(context.accumulated_evidence) == 1
        assert len(context.question_history) == len(before_questions) + 1
        await adapter.drain_background_tasks()
        kg.persist_turn_evaluation_async.assert_awaited_once()
    asyncio.run(run())
