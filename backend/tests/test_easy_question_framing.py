"""Keep low-difficulty spoken follow-ups to one accessible request."""

import pytest

from app.models.enums import DifficultyLevel
from app.orchestrator.questions import first_spoken_question, spoken_question_is_clear


def test_observed_architecture_and_ownership_prompt_is_not_an_easy_question():
    question = (
        'That sounds interesting. Could you walk me through the high-level architecture '
        'of that system and clarify which specific components you built yourself versus '
        'those you integrated from other services?'
    )
    assert not spoken_question_is_clear(question, DifficultyLevel.EASY)
    # The remaining architecture walkthrough is still too broad for this level.
    # Let the normal wording fallback choose a concrete objective instead.
    assert first_spoken_question(question, DifficultyLevel.EASY) is None


@pytest.mark.parametrize('second_request', [
    'clarify who uses it',
    'describe how you tested it',
    'explain why you chose it',
    'outline how you deployed it',
    'list the other components',
    'compare it with another feature',
    'summarize the deployment steps',
    'tell me how you tested it',
    'walk me through the deployment',
    'also explain who uses it',
    'then describe your tests',
    'where did you deploy it',
    'when did you deploy it',
    'can you explain your test cases',
    'could you describe your tests',
])
def test_acknowledged_compound_request_preserves_only_complete_first_question(second_request):
    question = f'That sounds interesting. Could you describe the LMS feature you built and {second_request}?'
    assert not spoken_question_is_clear(question, DifficultyLevel.EASY)
    assert first_spoken_question(question, DifficultyLevel.EASY) == (
        'Could you describe the LMS feature you built?'
    )


@pytest.mark.parametrize('question', [
    'What input and output does your login function handle?',
    'How did you test the integration between your app and Razorpay?',
    'Thanks. What did you change in the LMS login page?',
    'Which component of the overall architecture did you build?',
    'Why did you choose that high-level architecture?',
    'Could you describe one step you implemented in the login flow?',
])
def test_natural_single_questions_and_noun_conjunctions_remain_valid(question):
    assert spoken_question_is_clear(question, DifficultyLevel.EASY)


@pytest.mark.parametrize('question', [
    'Could you describe the overall system architecture?',
    'Could you explain your end-to-end design?',
    'What is the high-level architecture of the LMS?',
])
def test_overview_is_not_mistaken_for_easy_because_it_is_short(question):
    assert not spoken_question_is_clear(question, DifficultyLevel.EASY)
    assert spoken_question_is_clear(question, DifficultyLevel.MEDIUM)


@pytest.mark.parametrize('question', [
    'Your system stores grades. What did you build and how did you test it?',
    'Imagine that the login server fails. What would you inspect and why?',
    'That sounds interesting. You built login and how did it work?',
    'What did you build? Could you describe how you tested it?',
])
def test_no_truncation_of_scenario_statements_or_multiple_complete_questions(question):
    assert first_spoken_question(question, DifficultyLevel.EASY) is None


def test_acknowledgement_does_not_prevent_safe_interrogative_clause_split():
    question = 'Got it. What did you implement in the LMS and how did you test it?'
    assert first_spoken_question(question, DifficultyLevel.EASY) == 'What did you implement in the LMS?'


def test_complete_first_question_can_be_kept_before_explicit_second_request():
    question = 'What did you build? And describe how you tested it?'
    assert not spoken_question_is_clear(question, DifficultyLevel.EASY)
    assert first_spoken_question(question, DifficultyLevel.EASY) == 'What did you build?'
