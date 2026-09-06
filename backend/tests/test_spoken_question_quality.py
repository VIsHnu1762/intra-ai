"""Regression cases from broad, compound and unanchored live questions."""
import pytest

from app.interview_context.models import InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis
from app.models.enums import DifficultyLevel
from app.orchestrator.policies import build_adaptive_probe_question, build_fresh_competency_question
from app.orchestrator.questions import objective_questions, spoken_question_is_clear, first_spoken_question
from app.agents.registry import agent_registry


@pytest.mark.parametrize('question', [
    'Let\'s start with core concepts of technical depth. Can you give one simple example?',
    'Can you give one concrete example of Specific scalability strategies, trade-offs, performance metrics, real-world examples?',
    'What database did you use and why did you choose it?',
    'What trade-offs did you consider around failure cases, observability, consistency?',
])
def test_observed_abstract_or_compound_questions_are_not_valid_speech(question):
    assert not spoken_question_is_clear(question, DifficultyLevel.EASY)


@pytest.mark.parametrize('competency,words', [
    ('coding_problem_solving', ['function', 'list']),
    ('customer_understanding', ['users', 'project']),
    ('system_design', ['web app', 'database']),
])
def test_first_medium_question_introduces_its_scenario(competency, words):
    question = objective_questions(competency, DifficultyLevel.MEDIUM)[0][1]
    assert all(word in question for word in words)
    assert 'that difficulty' not in question and 'that database' not in question
    assert spoken_question_is_clear(question, DifficultyLevel.MEDIUM)


def test_gap_checklist_is_translated_to_a_single_failure_scenario():
    question = build_adaptive_probe_question('system_design',
        ['failure cases, observability, consistency'], None, agent_registry.get_profile('alex'))
    assert 'server failure' in question and 'database write' in question
    assert 'observability, consistency' not in question
    assert spoken_question_is_clear(question, DifficultyLevel.MEDIUM)


def test_new_gap_label_cannot_reopen_an_answered_objective():
    context = InterviewAIContext(interview_id='finite-gap', candidate_id='candidate',
        current_round_id='technical', current_agent_id='alex')
    context.add_question_history(QuestionHistoryItem(agent_id='alex', competency='scalability',
        difficulty=DifficultyLevel.MEDIUM, question_text='How would you invalidate an old cache value?',
        metadata={'objective_id': 'scalability:apply'}))
    analysis = AnswerAnalysis(answer_id='next', overall_performance=.6, confidence=.8,
        vague=False, contradiction_detected=False, missing_information=['Idempotency key generation strategy'])
    question = build_fresh_competency_question('scalability', DifficultyLevel.MEDIUM, context, analysis)
    assert question and 'retried payment' not in question
    assert spoken_question_is_clear(question, DifficultyLevel.MEDIUM)


def test_real_model_compound_followup_preserves_first_relevant_question():
    original = ('Could you walk me through how you handle consumer rebalancing and partition ownership in your Kafka setup, '
                'and how you generate and store idempotency keys to avoid duplicates during scaling events?')
    simplified = first_spoken_question(original, DifficultyLevel.MEDIUM)
    assert simplified == 'Could you walk me through how you handle consumer rebalancing and partition ownership in your Kafka setup?'
    assert spoken_question_is_clear(simplified, DifficultyLevel.MEDIUM)
    assert 'idempotency' not in simplified


@pytest.mark.parametrize('text', ['Core concepts of technical depth?', 'You built Kafka and how did it work?',
                                   'What are the concepts, metrics, trade-offs?'])
def test_invalid_statements_are_not_truncated_into_questions(text):
    assert first_spoken_question(text, DifficultyLevel.EASY) is None
