"""A cloud revalidation must not invent a new spoken question."""
from unittest.mock import AsyncMock
import pytest
from app.sessions.models import InterviewConfiguration
from app.sessions.service import InterviewSessionService
from app.sessions.store import SessionStore
from app.interview_context.store import InterviewSessionStore

@pytest.mark.asyncio
async def test_same_cloud_generation_preserves_active_question_and_history(monkeypatch):
    contexts = InterviewSessionStore()
    monkeypatch.setattr('app.interview_context.store.interview_session_store', contexts)
    from app.core.config import settings
    monkeypatch.setattr(settings, 'AGORA_APP_ID', 'test_app_id')
    monkeypatch.setattr(settings, 'AGORA_APP_CERTIFICATE', 'test_cert_1234567890123456789012')
    start = AsyncMock(return_value={'status': 'started', 'agora_agent_id': 'cloud-original'})
    monkeypatch.setattr('app.services.agora_agent_service.agora_agent_service.start_interview_agent', start)
    service = InterviewSessionService(store=SessionStore())
    session = service.create_session(InterviewConfiguration(
        interview_id='refresh-test', candidate_id='candidate-test', agent_ids=['alex'],
        metadata={'required_competencies': ['product_sense', 'system_design']},
    ))
    await service.start_session(session.interview_id)
    context = contexts.get(session.interview_id)
    assert context.question_history[-1].competency == 'system_design'
    context.metadata['active_interviewer_question'] = 'How did Kafka retries prevent double charging?'
    history_before = list(context.question_history)
    await service.start_session(session.interview_id)
    assert context.metadata['active_interviewer_question'] == 'How did Kafka retries prevent double charging?'
    assert context.question_history == history_before
    assert start.await_count == 2
