"""Live transcript regressions: sentence starts must not become project names."""

import pytest

from app.interview_context.models import EvidenceItem, InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.interview_intelligence.provider import extract_key_subject
from app.models.enums import DifficultyLevel
from app.orchestrator.policies import build_fresh_competency_question, substantive_subject


@pytest.mark.parametrize("text", [
    "For system design, I started with what architecture methods are commonly used.",
    "So the customer",
    "I worked on the",
    "I do not know Redis.",
    "I am not sure about the payment ledger.",
    "I don't understand the LMS.",
    "Hello Alex",
    "",
])
def test_unrecognized_or_ignorance_utterance_has_no_invented_subject(text):
    assert extract_key_subject(text) == ""


@pytest.mark.parametrize("text,expected", [
    ("I used Redis to reduce reads to the database.", "redis"),
    ("We designed an LMS using FastAPI and PostgreSQL.", "lms"),
    ("I built a learning management system for the university.", "learning management system"),
    ("I designed the payment ledger with double-entry accounting.", "payment ledger"),
    ("The payment service used idempotency keys.", "payment service"),
])
def test_explicit_grounded_subject_is_retained(text, expected):
    assert extract_key_subject(text) == expected
    assert substantive_subject(expected) == expected


@pytest.mark.parametrize("fragment", [
    "For system design, I", "So the customer", "I worked on the", "We designed a",
    "This was the", "The customer was", "Actually the project", "I don't know Redis",
])
def test_model_or_legacy_metadata_fragments_are_not_subjects(fragment):
    assert substantive_subject(fragment) is None


def _question(fragment, *, previous=None, missing_information=None):
    evidence = EvidenceItem(
        id="current", competency="system_design", signal=fragment,
        metadata={"subject": fragment}, score=2,
    )
    context = InterviewAIContext(
        interview_id="grounding-session", candidate_id="grounding-candidate",
        current_round_id="technical", current_agent_id="alex",
    )
    if previous:
        context.add_evidence(EvidenceItem(
            id="prior", competency="system_design", signal=f"I built the {previous}.",
            metadata={"subject": previous}, score=8,
        ))
    result = AnswerAnalysis(
        answer_id="current-answer", overall_performance=0.2, confidence=0.9,
        vague=True, contradiction_detected=False, evidence=[evidence],
        missing_information=missing_information or [],
        competency_findings=[CompetencyFinding(
            competency_id="system_design", assessment="Incomplete explanation",
            confidence=0.9, evidence_ids=["current"],
        )],
    )
    return build_fresh_competency_question("system_design", DifficultyLevel.EASY, context, result)


@pytest.mark.parametrize("fragment", ["For system design, I", "So the customer", "I don't know Redis"])
def test_question_omits_false_example_and_can_reuse_real_prior_subject(fragment):
    question = _question(fragment)
    assert fragment not in question
    assert "example you mentioned" not in question
    for previous in ("redis", "lms", "payment ledger"):
        grounded = _question(fragment, previous=previous)
        assert previous in grounded.lower()
        if previous in {"lms", "payment ledger"}:
            assert "web app" not in grounded.lower()
        assert fragment not in grounded
        assert grounded.count("?") == 1


@pytest.mark.parametrize("gap", [
    "Specific design steps taken for the caching layer",
    "Detailed explanation of product sense beyond customer focus",
    "Specific scalability strategies, trade-offs, performance metrics, real-world examples",
])
def test_observed_gap_labels_cannot_turn_into_spoken_checklists(gap):
    question = _question("For system design, I", missing_information=[gap])
    assert gap not in question
    assert question == "For a small web app, where would you store its user data?"
    assert question.count("?") == 1
    assert len(question.split()) <= 32
