"""Recruiter CV/JD must reach the first greeting and reasoning turn together."""
from unittest.mock import AsyncMock

import pytest

from app.agent_context.builder import AgentTurnContextBuilder
from app.agent_context.personalization import candidate_first_name
from app.agents.registry import agent_registry
from app.custom_llm.adapter import CustomLLMAdapter, generate_opening_question, generate_handoff_question
from app.custom_llm.models import ChatCompletionRequest
from app.interview_context.store import InterviewSessionStore
from app.interview_intelligence.prompts import build_m1_user_prompt
from app.sessions.models import InterviewConfiguration
from app.sessions.service import InterviewSessionService
from app.sessions.store import SessionStore


@pytest.mark.parametrize('metadata,expected', [
    ({'candidate_name': 'Sriram Raj'}, 'Sriram'),
    ({'candidate_name': 'Dr. Ana-María Silva'}, 'Ana-María'),
    ({'candidate_name': '李 明'}, '李'),
    ({'candidate_name': 'Sriram Raj', 'candidate_first_name': 'Sri'}, 'Sri'),
    ({'parsed_resume': {'name': "D’Arcy Smith"}}, "D’Arcy"),
    ({'candidate_profile': {'parsed_resume': {'full_name': 'Sam Lee'}}}, 'Sam'),
    ({'candidate_name': 'candidate'}, None),
    ({'candidate_name': 'person@example.test'}, None),
    ({}, None),
])
def test_first_name_comes_from_profile_not_email_or_placeholder(metadata, expected):
    assert candidate_first_name(metadata) == expected


@pytest.mark.asyncio
async def test_recruiter_parsed_resume_is_loaded_before_cloud_start_and_first_m1(monkeypatch):
    contexts = InterviewSessionStore()
    monkeypatch.setattr('app.interview_context.store.interview_session_store', contexts)
    from app.core.config import settings
    monkeypatch.setattr(settings, 'AGORA_APP_ID', 'test-app')
    monkeypatch.setattr(settings, 'AGORA_APP_CERTIFICATE', 'test-cert')
    service = InterviewSessionService(store=SessionStore())
    session = service.create_session(InterviewConfiguration(
        interview_id='profile-start', candidate_id='cv-candidate', agent_ids=['alex', 'jordan'],
        job_title='Full Stack Engineer', metadata={
            'candidate_name': 'Sriram Raj', 'job_id': 'lms-job',
            'job_description': 'Build learning platforms with Redis caching and PostgreSQL.',
            'required_skills': ['Redis', 'PostgreSQL'],
            'required_competencies': ['system_design', 'product_sense'],
            'parsed_resume': {'skills': ['Python', 'Redis'], 'projects': [
                {'name': 'Portfolio', 'technologies': ['HTML']},
                {'name': 'LMS', 'technologies': ['Redis', 'PostgreSQL']},
            ], 'experience': [{'role': 'Engineer', 'company': 'Example', 'description': 'Built LMS.'}]},
        },
    ))
    m1, orch, kg, builder = (AsyncMock() for _ in range(4))
    adapter = CustomLLMAdapter(session_store=contexts, m1_analyzer=m1, orchestrator=orch,
                               kg_service=kg, context_builder=builder)
    startup_greetings = []

    async def cloud_start(**kwargs):
        context = contexts.get(session.interview_id)
        assert context.metadata['candidate_profile']['projects'][1]['name'] == 'LMS'
        assert context.metadata['job_description'].startswith('Build learning')
        assert context.metadata['native_greeting_pending'] is True
        startup_greetings.append(kwargs['greeting_text'])
        # A callback can arrive while /join is still awaiting its HTTP response.
        handshake = adapter.parse_turn(ChatCompletionRequest(messages=[{'role': 'user', 'content': ''}]),
                                       headers={'x-session-id': session.channel_name})
        assert await adapter.process_turn_async(handshake) == ('', None)
        return {'status': 'started', 'agora_agent_id': 'cloud-personalized'}

    monkeypatch.setattr('app.services.agora_agent_service.agora_agent_service.start_interview_agent', cloud_start)
    await service.start_session(session.interview_id)
    context = contexts.get(session.interview_id)
    assert startup_greetings[0].startswith("Hi Sriram! I'm Alex")
    assert 'LMS' in startup_greetings[0] and 'Portfolio' not in startup_greetings[0]
    assert 'Full Stack Engineer' in startup_greetings[0]
    assert len(context.question_history) == 1
    assert 'native_greeting_pending' not in context.metadata
    assert not context.accumulated_evidence  # CV claims aren't scored evidence.
    # Both profiles share the same job and parsed candidate snapshot.
    candidate = AgentTurnContextBuilder._candidate_from_metadata(context.metadata, session.candidate_id)
    job = AgentTurnContextBuilder._job_from_metadata(context.metadata, 'lms-job')
    assert candidate.name == 'Sriram Raj' and candidate.projects[1].name == 'LMS'
    assert job.description == context.metadata['job_description']
    assert generate_handoff_question(agent_registry.get_profile('jordan'), context, 'product_sense').startswith("Thanks, Sriram. I'm Jordan")

    # Inspect exactly what the first M1 call receives; stop before external work.
    seen = []
    async def inspect_m1(input_data):
        seen.append(input_data)
        raise RuntimeError('intentional test boundary after capturing M1 input')
    m1.analyze_async.side_effect = inspect_m1
    request = ChatCompletionRequest(messages=[
        {'role': 'assistant', 'content': startup_greetings[0]},
        {'role': 'user', 'content': 'I built Redis cache invalidation for LMS course updates.'},
    ])
    await adapter.process_turn_async(adapter.parse_turn(request, headers={'x-session-id': session.channel_name}))
    assert len(seen) == 1
    prompt = build_m1_user_prompt(seen[0])
    assert 'LMS' in prompt and 'Build learning platforms' in prompt
    assert seen[0].candidate_profile['name'] == 'Sriram Raj'
    assert not context.accumulated_evidence


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['Hi Alex', 'Hello Alex'])
async def test_acknowledging_native_greeting_does_not_repeat_introduction(text):
    contexts = InterviewSessionStore()
    context = contexts.get_or_create('greet-once', agent_id='alex', metadata={
        'active_interviewer_question': 'How did you design the LMS cache?',
    })
    adapter = CustomLLMAdapter(session_store=contexts)
    request = ChatCompletionRequest(messages=[{'role': 'user', 'content': text}])
    before = context.model_dump()
    answer, action = await adapter.process_turn_async(adapter.parse_turn(request, headers={'x-session-id': 'greet-once'}))
    assert "I'm Alex" not in answer and '?' not in answer
    assert action is None and context.model_dump() == before


def test_missing_profile_greeting_does_not_invent_candidate_or_project():
    context = InterviewSessionStore().get_or_create('unknown-person', agent_id='alex')
    text = generate_opening_question(agent_registry.get_profile('alex'), context)
    assert text.startswith("Hello! I'm Alex")
    assert 'a recent project' in text


@pytest.mark.parametrize('agent_id,competency', [
    ('alex', 'coding_problem_solving'), ('alex', 'debugging'),
    ('alex', 'system_design'), ('jordan', 'customer_understanding'),
])
def test_cv_project_is_explicit_in_every_opening_not_only_architecture(agent_id, competency):
    context = InterviewSessionStore().get_or_create('cv-opening-' + competency,
        agent_id=agent_id, missing_competencies=[competency], metadata={
            'candidate_name': 'Sriram', 'required_skills': ['FastAPI'],
            'parsed_resume': {'projects': [{'name': 'Learning Management System (LMS)',
                                            'technologies': ['FastAPI']}]},
        })
    text = generate_opening_question(agent_registry.get_profile(agent_id), context)
    assert 'Your CV mentions Learning Management System (LMS).' in text
    assert text.count('?') == 1
    assert text.count('Learning Management System (LMS)') == 1
    assert 'that project' in text
    assert context.accumulated_evidence == []


def test_incomplete_cv_uses_existing_text_and_shared_job_skill_without_inventing_projects():
    from app.interview_intelligence.models import InterviewAnswerInput, AnswerAnalysis
    from app.agent_context.models import AgentTurnContext
    from app.knowledge_graph.memory_models import PersistentCandidateMemory
    from app.orchestrator.prompts import build_nemotron_routing_messages
    from app.knowledge_graph.repository import InMemoryKnowledgeGraphRepository
    from app.knowledge_graph.memory_service import CandidateMemoryService
    service = InterviewSessionService(store=SessionStore())
    session = service.create_session(InterviewConfiguration(
        interview_id='raw-cv', candidate_id='raw-candidate', agent_ids=['alex', 'jordan'],
        metadata={'candidate_name': 'Sam Lee', 'required_skills': ['Redis'],
                  'job_description': 'Build learning software using Redis caching.',
                  'parsed_resume': {'skills': ['Python', 'Redis'], 'experience': [], 'projects': [],
                                    'raw_text': 'Built LMS course caching with Redis at Example.'}},
    ))
    service._prepare_context_metadata(session)
    context = InterviewSessionStore().get_or_create('raw-cv', candidate_id='raw-candidate',
        agent_id='alex', metadata=session.metadata)
    alex = agent_registry.get_profile('alex')
    greeting = generate_opening_question(alex, context)
    assert 'where you used Redis' in greeting and 'LMS' not in greeting
    candidate = AgentTurnContextBuilder._candidate_from_metadata(context.metadata, 'raw-candidate')
    job = AgentTurnContextBuilder._job_from_metadata(context.metadata, 'raw-job')
    assert candidate.projects == [] and candidate.experience == []
    memory = CandidateMemoryService(repository=InMemoryKnowledgeGraphRepository()).get_candidate_memory('raw-candidate')
    turn_context = AgentTurnContext(candidate=candidate, job=job, interview=context,
        agent=alex, persistent_memory=memory, current_answer='I used Redis cache-aside.')
    m1_prompt = build_m1_user_prompt(InterviewAnswerInput(
        answer_id='raw-answer', question_text=greeting, answer_text='I used Redis cache-aside.',
        context=context, agent_profile=alex, candidate_profile=context.metadata['candidate_profile'],
        job_description=job.description,
    ))
    assert 'Built LMS course caching' in m1_prompt
    assert 'NOT CURRENT-ANSWER EVIDENCE' in m1_prompt
    analysis = AnswerAnalysis(answer_id='raw-answer', overall_performance=.4, confidence=.7,
                              vague=False, contradiction_detected=False)
    messages = build_nemotron_routing_messages(context, analysis, agent_registry, turn_context=turn_context)
    assert 'Built LMS course caching' in str(messages)
    assert 'Build learning software' in str(messages)
    assert context.accumulated_evidence == []


def test_scheduled_interview_selects_cv_for_this_application(monkeypatch):
    from app.services.scheduling_service import SchedulingService
    service = InterviewSessionService(store=SessionStore())
    monkeypatch.setattr('app.sessions.service.interview_session_service', service)
    SchedulingService._ensure_live_session({
        'id': 'applied-lms', 'candidate_id': 'candidate-many-jobs',
        'candidates': {'name': 'Sam Lee', 'parsed_resumes': [
            {'id': 'other-cv', 'application_id': 'other-job', 'skills': ['Accounting'], 'created_at': '2026-09-06'},
            {'id': 'lms-cv', 'application_id': 'applied-lms', 'skills': ['Redis'], 'created_at': '2026-09-05'},
        ]},
        'jobs': {'id': 'lms-job', 'title': 'LMS Engineer', 'description': 'Build learning software.', 'required_skills': ['Redis']},
    }, {'id': 'scheduled-cv', 'application_id': 'applied-lms'})
    session = service.get_session('scheduled-cv')
    assert session.metadata['resume_id'] == 'lms-cv'
    service._prepare_context_metadata(session)
    assert session.metadata['candidate_profile']['skills'] == ['Redis']
    assert session.metadata['job_id'] == 'lms-job'
    assert 'Accounting' not in str(session.metadata['candidate_profile'])
