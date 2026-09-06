"""Replay spoken-name corrections without consuming an assessed answer."""
import pytest

from app.custom_llm.context_correction import project_name_correction
from app.interview_context.models import QuestionHistoryItem
from app.models.enums import DifficultyLevel
from tests.test_answer_question_identity import interview, speak


@pytest.mark.parametrize('text,expected', [
    ('So it is not a webmaster application, it is a LMS application.', ('webmaster application', 'LMS application')),
    ("Sorry, it's not a booking app, it is a library platform.", ('booking app', 'library platform')),
    ('It is not a payment system, it is a course management system.', ('payment system', 'course management system')),
    ('Not SQL, we used NoSQL.', None),
    ('It is not a synchronous system, it is an asynchronous system and we use Kafka.', None),
    ('It is not a synchronous system, it is an asynchronous system.', None),
    ('It is not a payment system, it is a course system. The API validates a JWT.', None),
])
def test_only_complete_project_name_corrections_take_fast_path(text, expected):
    assert project_name_correction(text) == expected


@pytest.mark.asyncio
async def test_correction_preserves_question_target_and_never_scores_it(interview):
    question = 'What information does your webmaster application need to keep?'
    interview.context.metadata['active_interviewer_question'] = question
    interview.context.metadata['candidate_profile'] = {'projects': [{'name': 'Original CV claim'}]}
    item = QuestionHistoryItem(agent_id='alex', competency='system_design',
        question_text=question, difficulty=DifficultyLevel.EASY)
    interview.context.add_question_history(item)
    before_id = item.id
    history = [{'role': 'assistant', 'content': question}]
    text, action = await speak(interview, history,
        'So it is not a webmaster application, it is a LMS application.')
    assert action is None
    assert text == 'Thanks for correcting me. What information does your LMS application need to keep?'
    interview.m1.analyze_async.assert_not_awaited()
    interview.orchestrator.decide_async.assert_not_awaited()
    assert not interview.context.accumulated_evidence
    assert interview.context.question_history[-1].id == before_id
    assert item.metadata['original_spoken_question'] == question
    assert item.exploration_status != 'SUFFICIENT'
    assert interview.context.metadata['candidate_profile']['projects'][0]['name'] == 'Original CV claim'
    assert interview.context.metadata['current_candidate_project'] == 'LMS application'
    await speak(interview, history, 'It stores candidate data for authentication.')
    evaluated = interview.m1.analyze_async.await_args.args[0]
    assert evaluated.question_text == 'What information does your LMS application need to keep?'
    assert evaluated.context.metadata['current_candidate_project'] == 'LMS application'


@pytest.mark.asyncio
async def test_positive_project_restatement_reaches_m1_before_evaluation(interview):
    interview.context.metadata['current_candidate_project'] = 'webmaster application'
    history = [{'role': 'assistant', 'content': 'What did you build?'}]
    await speak(interview, history, 'So recently I have worked on a LMS software.')
    evaluated = interview.m1.analyze_async.await_args.args[0]
    assert evaluated.context.metadata['current_candidate_project'] == 'lms software'
    assert evaluated.context is not interview.context
