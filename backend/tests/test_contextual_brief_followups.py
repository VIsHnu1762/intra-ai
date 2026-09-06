"""Regressions from the Razorpay voice turn that fell into payment templates."""
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
from app.orchestrator.service import MetaOrchestrator


def fixture(*, weak=False):
    answer = ('By seeing the server logs.' if weak else
              'I created a payment gateway using Razorpay SDK.')
    target = 'debugging' if weak else 'system_design'
    # M1 may label the SDK answer with a broader persona skill that the HR
    # configuration did not select. Routing must retain the configured target.
    finding = target if weak else 'software_architecture'
    question = ('How would you check whether the write succeeded?' if weak else
                'What did you personally build?')
    ctx = InterviewAIContext(interview_id='brief-followup', candidate_id='candidate',
        current_round_id='technical', current_agent_id='alex',
        missing_competencies=[target, 'product_sense'],
        metadata={'configured_agent_ids': ['alex', 'jordan'],
                  'required_competencies': [target, 'product_sense']})
    analysis = AnswerAnalysis(answer_id='brief-answer', overall_performance=.2 if weak else .5,
        confidence=.9, vague=not weak, vague_reason=None if weak else 'More detail needed',
        contradiction_detected=False,
        evidence=[EvidenceItem(id='e1', competency=finding, signal=answer, score=2 if weak else 5)],
        competency_findings=[CompetencyFinding(competency_id=finding, assessment='Brief answer',
                                               confidence=.9, evidence_ids=['e1'])],
        missing_information=['Specific integration steps' if not weak else 'Which log entry to inspect'])
    turn = AgentTurnContext(candidate=CandidateProfileContext(candidate_id='candidate'),
        job=JobContext(job_id='job', title='Software Engineer',
                       required_competencies=[target, 'product_sense']),
        persistent_memory=PersistentCandidateMemory(candidate_id='candidate'),
        interview=ctx, agent=agent_registry.get_profile('alex'),
        current_question=question, current_answer=answer, answer_analysis=analysis)
    return ctx, analysis, turn, target


def run(ctx, analysis, turn, target, text, **changes):
    response = {'action': 'ASK_QUESTION', 'target_agent_id': 'alex', 'competency': target,
                'rationale': 'Clarify the candidate’s stated contribution.', 'question_text': text,
                **changes}
    model = AsyncMock(return_value=response)
    with patch.object(settings, 'ORCHESTRATOR_PROVIDER', 'aicredits'), \
         patch('app.orchestrator.graph.generate_intelligence', model), \
         patch('app.orchestrator.graph.call_groq', side_effect=AssertionError('No Groq fallback')):
        action = asyncio.run(MetaOrchestrator().decide_async(ctx, analysis,
            current_question_text=turn.current_question, turn_context=turn))
    return action, model


@pytest.mark.parametrize('weak,question', [
    (False, 'What did you implement between your app and the Razorpay SDK?'),
    (True, 'Which entry in the server logs would show whether the write succeeded?'),
])
def test_brief_or_weak_answer_keeps_one_contextual_model_question(weak, question):
    ctx, analysis, turn, target = fixture(weak=weak)
    action, model = run(ctx, analysis, turn, target, question)
    model.assert_awaited_once()
    assert action.action == ActionType.ASK_QUESTION
    assert action.target_agent_id == 'alex' and action.competency == target
    assert action.question_text == question
    assert action.difficulty == DifficultyLevel.EASY
    assert action.metadata['orchestrator_model_used'] is True
    state_text = model.call_args.kwargs['messages'][1]['content'].split('INTERVIEW STATE:', 1)[1]
    state = json.JSONDecoder().raw_decode(state_text.lstrip())[0]
    assert state['current_answer'] == turn.current_answer
    assert state['current_question'] == turn.current_question
    assert state['selected_policy']['target_competency'] == target


@pytest.mark.parametrize('kind,agent,competency', [
    ('SWITCH_AGENT', 'jordan', 'product_sense'),
    ('COMPLETE', 'alex', None),
    ('ASK_QUESTION', 'alex', 'scalability'),
])
def test_model_cannot_escape_required_clarification(kind, agent, competency):
    ctx, analysis, turn, target = fixture()
    action, model = run(ctx, analysis, turn, target, 'Jordan will take over now.',
                        action=kind, target_agent_id=agent, competency=competency)
    model.assert_awaited_once()
    assert action.action == ActionType.ASK_QUESTION
    assert action.target_agent_id == 'alex' and action.competency == target
    assert action.metadata['orchestrator_model_used'] is False
    assert action.difficulty == DifficultyLevel.EASY


def test_contextual_model_question_cannot_repeat_previous_question():
    ctx, analysis, turn, target = fixture()
    repeated = 'What did you implement between your app and the Razorpay SDK?'
    ctx.add_question_history(QuestionHistoryItem(agent_id='alex', competency=target,
        question_text=repeated, difficulty=DifficultyLevel.EASY))
    action, _ = run(ctx, analysis, turn, target, repeated)
    assert action.question_text != repeated
    assert action.metadata['question_policy']['repetition_prevented'] is True


def test_ungrounded_model_question_is_still_rejected():
    ctx, analysis, turn, target = fixture()
    unrelated = 'How do quantum particles interact inside a stellar nebula?'
    action, _ = run(ctx, analysis, turn, target, unrelated)
    assert action.question_text != unrelated
    assert action.metadata['question_policy']['ungrounded_question_replaced'] is True
