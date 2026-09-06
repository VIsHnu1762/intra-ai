"""Replay the observed LMS question scope without paid provider or voice calls."""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agent_context.models import AgentTurnContext, CandidateProfileContext, JobContext
from app.agents.registry import agent_registry
from app.core.config import settings
from app.interview_context.models import EvidenceItem, InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.knowledge_graph.memory_models import PersistentCandidateMemory
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator.policies import plan_competency_difficulty, question_has_grounding
from app.orchestrator.service import MetaOrchestrator


def inputs(question, answer, followup):
    ctx = InterviewAIContext(interview_id='lms-continuity', candidate_id='synthetic-candidate',
        current_agent_id='alex', current_round_id='technical',
        missing_competencies=['system_design', 'debugging', 'product_sense'],
        metadata={'configured_agent_ids': ['alex', 'jordan'],
                  'required_competencies': ['system_design', 'debugging', 'product_sense'],
                  'current_candidate_project': 'lms software', 'active_interviewer_question': question})
    ctx.add_question_history(QuestionHistoryItem(agent_id='alex', competency='system_design',
        difficulty=DifficultyLevel.MEDIUM, question_text=question))
    analysis = AnswerAnalysis(answer_id='current-answer', overall_performance=.3, confidence=.9,
        vague=True, contradiction_detected=False, recommended_follow_up=followup,
        evidence=[EvidenceItem(id='e1', competency='software_architecture', signal=answer, score=3)],
        competency_findings=[CompetencyFinding(competency_id='software_architecture',
            confidence=.9, assessment='A brief architecture-related answer', evidence_ids=['e1'])])
    turn = AgentTurnContext(candidate=CandidateProfileContext(candidate_id=ctx.candidate_id),
        job=JobContext(job_id='software-role', title='Software developer',
                       required_competencies=ctx.metadata['required_competencies']),
        persistent_memory=PersistentCandidateMemory(candidate_id=ctx.candidate_id),
        interview=ctx, agent=agent_registry.get_profile('alex'), current_answer=answer,
        current_question=question, answer_analysis=analysis)
    return ctx, analysis, turn


def decide(ctx, analysis, turn, followup, target='system_design'):
    model = AsyncMock(return_value={'action': 'ASK_QUESTION', 'target_agent_id': 'alex',
        'competency': target, 'question_text': followup, 'rationale': 'Follow up the latest answer.'})
    with patch.object(settings, 'ORCHESTRATOR_PROVIDER', 'aicredits'), \
         patch('app.orchestrator.graph.generate_intelligence', model), \
         patch('app.orchestrator.graph.call_groq', side_effect=AssertionError('No Groq call')):
        action = asyncio.run(MetaOrchestrator().decide_async(ctx, analysis,
            current_question_text=turn.current_question, turn_context=turn))
    return action, model


@pytest.mark.parametrize('question,answer,followup', [
    ('Thinking of a recent project, what did you personally build?',
     'I built a LMS software using FastAPI and Postgres backend.',
     'Which part of the LMS did you implement with FastAPI?'),
    ('You mentioned lms software. How would a login request from a web app reach its database?',
     'Through API.', 'What does your API do before it sends a request to Postgres?'),
    ('You mentioned lms software. How would you check whether the database is causing slow requests?',
     "I don't know, actually. Maybe the latency of the database, the processing time, so that we can add a caching layer like Redis, so that we can reduce the latency.",
     'What information would you cache in Redis for your LMS?'),
])
def test_live_lms_scope_retains_contextual_followup_instead_of_bank(question, answer, followup):
    ctx, analysis, turn = inputs(question, answer, followup)
    action, model = decide(ctx, analysis, turn, followup)
    model.assert_awaited_once()
    assert action.action == ActionType.ASK_QUESTION
    assert action.competency == 'system_design'
    assert action.question_text == followup
    assert action.difficulty == DifficultyLevel.EASY
    assert action.metadata['question_source'] == 'meta'
    assert not action.metadata.get('question_policy')
    assert action.metadata['coverage_policy']['answered_question_id'] == ctx.question_history[-1].id
    assert analysis.evidence[0].competency == 'software_architecture'
    prompt = model.call_args.kwargs['messages'][1]['content'].split('INTERVIEW STATE:', 1)[1]
    state = json.JSONDecoder().raw_decode(prompt.lstrip())[0]
    assert state['current_question'] == question and state['current_answer'] == answer
    assert state['difficulty_by_competency']['alex']['system_design'] == 'easy'


def test_api_and_previous_question_subject_anchor_a_short_linked_followup():
    ctx, analysis, turn = inputs('How does a request reach your LMS?', 'Through API.', '')
    assert question_has_grounding('Which API handles that step?', 'system_design', analysis, turn)
    assert question_has_grounding('What does the LMS receive?', 'system_design', analysis, turn)
    assert not question_has_grounding('Which planets influence astrological predictions?', 'system_design', analysis, turn)


def test_new_topic_still_rejects_reusing_the_old_questions_recommended_followup():
    followup = 'What does your API do before it sends a request to Postgres?'
    ctx, analysis, turn = inputs('How does the API store a record?', 'The API inserts the record in Postgres.', followup)
    analysis.overall_performance = .9
    analysis.vague = False
    analysis.competency_findings[0].competency_id = 'system_design'
    analysis.evidence[0].competency = 'system_design'
    action, _ = decide(ctx, analysis, turn, followup, target='debugging')
    assert action.competency == 'debugging'
    assert action.question_text != followup
    assert action.metadata['question_policy']['stale_followup_replaced']
    assert action.metadata['question_source'] == 'fallback'


def test_current_question_does_not_lower_an_older_unrelated_competencys_level():
    ctx, analysis, _ = inputs('How does the API store a record?', 'Through API.', '')
    ctx.add_question_history(QuestionHistoryItem(agent_id='alex', competency='debugging',
        difficulty=DifficultyLevel.MEDIUM, question_text='What failed in that test?'))
    level, _ = plan_competency_difficulty(ctx, analysis, agent_registry.get_profile('alex'),
        'system_design', current_question_text='What failed in that test?')
    assert level == DifficultyLevel.MEDIUM
