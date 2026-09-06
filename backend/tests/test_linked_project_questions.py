"""Concrete follow-ups stay with the project the candidate just named."""

import pytest

from app.interview_context.models import EvidenceItem, InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis
from app.interview_intelligence.provider import extract_key_subject, is_project_subject
from app.models.enums import DifficultyLevel
from app.orchestrator.policies import build_competency_question_options, build_fresh_competency_question
from app.orchestrator.questions import objective_questions, spoken_question_is_clear


@pytest.mark.parametrize("answer,expected", [
    ("So, using Python, I built a LLM software.", "llm software"),
    ("I developed an LLM application for our team.", "llm application"),
    ("We implemented a machine learning model.", "machine learning model"),
    ("I worked on an ML model with Python.", "ml model"),
    ("We built a shopping cart application.", "shopping cart application"),
    ("I created the Atlas platform.", "atlas platform"),
])
def test_positive_current_project_is_extracted_instead_of_sentence_prefix(answer, expected):
    assert extract_key_subject(answer) == expected


@pytest.mark.parametrize("answer", [
    "I didn't build an LLM application.", "I did not create an ML model.",
    "My colleague built an LLM software.", "They developed a shopping cart application.",
    "I read about LLM software.", "So the customer", "I worked on the",
    "I don't understand LLM applications.",
])
def test_negated_reported_or_incomplete_project_claim_is_not_promoted(answer):
    assert extract_key_subject(answer) == ""


def fixture(competency="technical_depth"):
    context = InterviewAIContext(interview_id="linked-project", candidate_id="synthetic-linked",
        current_round_id="technical", current_agent_id="alex", difficulty=DifficultyLevel.EASY,
        missing_competencies=[competency], metadata={
            "current_candidate_subject": extract_key_subject("So, using Python, I built a LLM software.")})
    # A project mention need not be graded as technical evidence to ground a
    # follow-up. The staged subject is separate from the evidence array.
    analysis = AnswerAnalysis(answer_id="project-mention", overall_performance=.2,
        confidence=.8, vague=True, contradiction_detected=False)
    return context, analysis


def test_first_two_followups_refer_to_the_actual_llm_software_without_new_scenario():
    context, analysis = fixture()
    first = build_fresh_competency_question("technical_depth", DifficultyLevel.EASY, context, analysis)
    assert first == "What task does your LLM software help someone complete?"
    context.add_question_history(QuestionHistoryItem(agent_id="alex", competency="technical_depth",
        question_text=first, difficulty=DifficultyLevel.EASY,
        metadata={"objective_id": "technical_depth:purpose"}))
    second = build_fresh_competency_question("technical_depth", DifficultyLevel.EASY, context, analysis)
    assert second == "What input does your LLM software receive?"
    assert "one project" not in first + second and "web app" not in first + second
    assert analysis.evidence == []


@pytest.mark.parametrize("competency", ["technical_depth", "system_design", "software_architecture", "scalability", "debugging", "technical_decision_making", "product_sense", "customer_understanding", "customer_impact", "prioritization", "requirements_thinking", "trade_off_decisions", "communication_of_product_decisions"])
def test_related_objectives_keep_project_and_stable_finite_identity(competency):
    context, analysis = fixture(competency)
    options = build_competency_question_options(competency, DifficultyLevel.EASY, context, analysis)
    assert [key for key, _ in options] == [key for key, _ in objective_questions(competency, DifficultyLevel.EASY)]
    assert len(options) == 4
    for _, question in options:
        assert "LLM software" in question
        assert "web app" not in question
        assert spoken_question_is_clear(question, DifficultyLevel.EASY)


def test_unrelated_example_has_explicit_transition_and_preserves_objective_ids():
    context, analysis = fixture("coding_problem_solving")
    options = build_competency_question_options("coding_problem_solving", DifficultyLevel.EASY, context, analysis)
    original = objective_questions("coding_problem_solving", DifficultyLevel.EASY)
    assert [key for key, _ in options] == [key for key, _ in original]
    assert all(text.startswith("For a separate example: ") for _, text in options)
    assert all(spoken_question_is_clear(text, DifficultyLevel.EASY) for _, text in options)


def test_changing_project_name_does_not_reset_used_objective():
    context, analysis = fixture()
    context.add_question_history(QuestionHistoryItem(agent_id="alex", competency="technical_depth",
        question_text="What task does your LMS help someone complete?", difficulty=DifficultyLevel.EASY,
        metadata={"objective_id": "technical_depth:purpose"}))
    question = build_fresh_competency_question("technical_depth", DifficultyLevel.EASY, context, analysis)
    assert question == "What input does your LLM software receive?"


@pytest.mark.parametrize("dependency", ["redis", "kafka", "API", "jwt"])
def test_dependency_mention_does_not_replace_current_project(dependency):
    context, analysis = fixture()
    context.metadata.update(current_candidate_project="llm software", current_candidate_subject=dependency)
    options = build_competency_question_options("system_design", DifficultyLevel.EASY, context, analysis)
    assert all("LLM software" in text for _, text in options)
    assert all(f"your {dependency}" not in text for _, text in options)


def test_project_from_another_competency_remains_salient_over_new_dependency():
    context, analysis = fixture("scalability")
    context.metadata["current_candidate_subject"] = "redis"
    context.add_evidence(EvidenceItem(competency="technical_depth", signal="I built LLM software using Python.",
        metadata={"subject": "llm software"}))
    options = build_competency_question_options("scalability", DifficultyLevel.EASY, context, analysis)
    assert all("LLM software" in text for _, text in options)


def test_new_explicit_project_can_replace_previous_project_without_resetting_objectives():
    context, analysis = fixture()
    context.metadata["current_candidate_project"] = "payment ledger"
    new_subject = extract_key_subject("I built an LLM software.")
    assert is_project_subject(new_subject)
    context.metadata["current_candidate_project"] = new_subject
    assert build_fresh_competency_question("technical_depth", DifficultyLevel.EASY, context, analysis) == "What task does your LLM software help someone complete?"


def test_saved_project_has_priority_over_new_component_shaped_subject():
    context, analysis = fixture()
    context.metadata.update(current_candidate_project="llm software", current_candidate_subject="payment service")
    assert all("LLM software" in text for _, text in build_competency_question_options("product_sense", DifficultyLevel.EASY, context, analysis))
