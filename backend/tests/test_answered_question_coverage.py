"""Answers follow the actual asked question, independently of M1's labels."""

from copy import deepcopy

import pytest

from app.agents.models import NextAction
from app.interview_context.models import InterviewAIContext, QuestionHistoryItem
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator.service import MetaOrchestrator


def context():
    ctx = InterviewAIContext(interview_id="question-association", candidate_id="candidate",
        current_round_id="technical", current_agent_id="alex")
    for identifier, competency, text in [
        ("earlier-architecture", "software_architecture", "What were the main parts of the app?"),
        ("answered-design", "system_design", "How does a request move through your LMS?"),
        ("later-design", "system_design", "What information does your LMS store?"),
    ]:
        ctx.add_question_history(QuestionHistoryItem(id=identifier, agent_id="alex",
            competency=competency, question_text=text, difficulty=DifficultyLevel.MEDIUM))
    return ctx


def action(*, competencies=None, sufficient=False, **changes):
    coverage = {
        "answered_question_id": "answered-design",
        "answered_competency": "system_design",
        "competencies": competencies if competencies is not None else ["software_architecture"],
        "sufficient": sufficient,
        "answer_id": "api-answer",
        **changes,
    }
    return NextAction(action=ActionType.ASK_QUESTION, target_agent_id="alex",
        competency="system_design", difficulty=DifficultyLevel.EASY,
        question_text="Which API receives that request?", rationale="Clarify the stated API path.",
        metadata={"coverage_policy": coverage})


def test_exact_asked_question_receives_answer_instead_of_older_finding_or_latest_question():
    ctx = context()
    before = deepcopy(ctx.question_history)
    result = action()

    MetaOrchestrator.record_assessment(ctx, result)

    assert ctx.question_history[1].metadata["answered_by"] == "api-answer"
    assert ctx.question_history[1].exploration_status == "PARTIAL"
    assert ctx.question_history[0] == before[0]
    assert ctx.question_history[2] == before[2]
    assert result.metadata["coverage_policy"]["competencies"] == ["software_architecture"]


@pytest.mark.parametrize("sufficient", [False, True])
def test_broader_finding_does_not_claim_mastery_of_the_asked_competency(sufficient):
    ctx = context()

    MetaOrchestrator.record_assessment(ctx, action(sufficient=sufficient))

    assert ctx.question_history[1].exploration_status == "PARTIAL"
    assert ctx.question_history[1].metadata["answered_by"] == "api-answer"


@pytest.mark.parametrize("label", ["system_design", "System Design"])
def test_sufficient_evidence_for_the_asked_competency_marks_exact_question_sufficient(label):
    ctx = context()

    MetaOrchestrator.record_assessment(ctx, action(competencies=[label], sufficient=True))

    assert ctx.question_history[1].exploration_status == "SUFFICIENT"
    assert ctx.question_history[1].metadata["answered_by"] == "api-answer"
    assert "answered_by" not in ctx.question_history[0].metadata
    assert "answered_by" not in ctx.question_history[2].metadata


def test_missing_exact_question_does_not_attach_answer_to_another_question():
    ctx = context()
    before = deepcopy(ctx.question_history)

    MetaOrchestrator.record_assessment(ctx, action(answered_question_id="unknown-question"))

    assert ctx.question_history == before


def test_legacy_coverage_without_question_identity_keeps_existing_association():
    ctx = context()
    result = action(competencies=["software_architecture"], sufficient=True)
    del result.metadata["coverage_policy"]["answered_question_id"]
    del result.metadata["coverage_policy"]["answered_competency"]

    MetaOrchestrator.record_assessment(ctx, result)

    assert ctx.question_history[0].metadata["answered_by"] == "api-answer"
    assert ctx.question_history[0].exploration_status == "SUFFICIENT"
    assert "answered_by" not in ctx.question_history[1].metadata
