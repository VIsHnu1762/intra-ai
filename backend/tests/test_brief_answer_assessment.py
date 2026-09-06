"""Brief relevant speech is not evidence that a competency cannot be assessed."""

import pytest

from app.interview_context.models import EvidenceItem, InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.models.enums import DifficultyLevel
from app.orchestrator.assessment import plan_insufficient_assessment


def context(competency="product_sense"):
    ctx = InterviewAIContext(interview_id="brief-assessment", candidate_id="isolated",
        current_round_id="product", current_agent_id="jordan", difficulty=DifficultyLevel.EASY)
    ctx.add_question_history(QuestionHistoryItem(agent_id="jordan", competency=competency,
        question_text="Who was the main user of that work?", difficulty=DifficultyLevel.EASY,
        metadata={"objective_id": f"{competency}:purpose"}))
    return ctx


def result(signals=(), *, competency="product_sense", assessment="Identifies the users"):
    evidence = [EvidenceItem(id=f"e-{i}", competency=competency, signal=text, score=1.5)
                for i, text in enumerate(signals)]
    return AnswerAnalysis(answer_id="a-brief", overall_performance=.15, confidence=.95,
        vague=True, contradiction_detected=False, missing_information=["More detail needed"],
        evidence=evidence, competency_findings=[CompetencyFinding(
            competency_id=competency, assessment=assessment, confidence=.95,
            evidence_ids=[item.id for item in evidence])])


@pytest.mark.parametrize("answer", [
    "Okay. For the LMS system, the one who studies like students, jobs, professors, or the users.",
    "Students and professors.",
    "I used FastAPI, React, PostgreSQL, and an external service like a—",
    "Canva.",
    "I'm not sure.",
    "I don't know React, but I built the backend in Django.",
    "I cannot explain that yet, but I can describe the API I implemented.",
    "I don't know. I implemented the checkout API.",
    "I don't know—",
    "I don't know...",
    "",
])
def test_short_relevant_uncertain_or_unfinished_speech_does_not_close(answer):
    assert plan_insufficient_assessment(context(), result([answer]), current_answer=answer) == {}


@pytest.mark.parametrize("answer", [
    "I don't know.", "I don’t know, actually.", "Sorry, I do not know the answer.",
    "I can't answer that.", "I cannot explain this.", "I have no idea.",
    "I actually don't know.", "I can't answer this, actually. I don't know.",
])
def test_explicit_standalone_inability_can_close_an_offered_simple_objective(answer):
    outcome = plan_insufficient_assessment(context(), result(), current_answer=answer)
    assert outcome["product_sense"]["status"] == "ASSESSED_INSUFFICIENT"
    assert outcome["product_sense"]["reason"] == "insufficient_response_to_simple_objective"
    assert outcome["product_sense"]["answer_id"] == "a-brief"


def test_no_raw_answer_and_no_evidence_is_not_inability_even_with_confident_low_score():
    assert plan_insufficient_assessment(context(), result()) == {}


def test_positive_user_identification_is_not_inability_for_legacy_callers():
    analysis = result(["students, jobs, professors, or the users"])
    assert plan_insufficient_assessment(context(), analysis) == {}


def test_explicit_supported_legacy_inability_remains_finite():
    analysis = result(["Candidate could not explain the requested simple task"],
        assessment="Cannot yet demonstrate this objective")
    assert plan_insufficient_assessment(context(), analysis)["product_sense"]["status"] == "ASSESSED_INSUFFICIENT"


def test_legacy_inability_finding_without_supporting_evidence_does_not_close():
    analysis = result(["Students and professors use the application"],
        assessment="Cannot yet demonstrate this objective")
    assert plan_insufficient_assessment(context(), analysis) == {}


def test_mixed_contribution_and_inability_evidence_needs_a_follow_up():
    analysis = result(["Candidate could not explain the requested simple task",
                       "Candidate identified the primary users as students"],
        assessment="Cannot yet demonstrate this objective")
    assert plan_insufficient_assessment(context(), analysis) == {}


@pytest.mark.parametrize("conjunction", ["but", "and"])
def test_legacy_compound_inability_and_attempted_answer_do_not_close(conjunction):
    analysis = result([f"Candidate could not explain the database {conjunction} described the API"],
        assessment="Cannot yet demonstrate this objective")
    assert plan_insufficient_assessment(context(), analysis) == {}


def test_raw_answer_takes_precedence_over_an_incorrect_inability_finding():
    analysis = result(["Candidate could not explain the requested simple task"],
        assessment="Cannot yet demonstrate this objective")
    assert plan_insufficient_assessment(context(), analysis,
        current_answer="The users are students and professors.") == {}


@pytest.mark.parametrize("scaffolded,difficulty,confidence", [
    (False, DifficultyLevel.EASY, .95),
    (True, DifficultyLevel.MEDIUM, .95),
    (True, DifficultyLevel.EASY, .4),
])
def test_standalone_inability_does_not_remove_existing_scaffolding_or_confidence_guards(
    scaffolded, difficulty, confidence,
):
    ctx, analysis = context(), result()
    ctx.question_history[-1].difficulty = difficulty
    if not scaffolded:
        ctx.question_history[-1].metadata.clear()
    analysis.confidence = confidence
    assert plan_insufficient_assessment(ctx, analysis, current_answer="I don't know.") == {}
