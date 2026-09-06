"""Legacy free-text coding focus must still route to its configured owner."""
from copy import deepcopy

import pytest

from app.agents.registry import agent_registry
from app.custom_llm.adapter import generate_opening_question
from app.interview_context.models import InterviewAIContext
from app.sessions.models import InterviewConfiguration, InterviewSession
from app.sessions.service import InterviewSessionService


@pytest.mark.parametrize("source", ["required_competencies", "round_configs"])
def test_legacy_coding_focus_resolves_without_rewriting_round_snapshot(source):
    rounds = [{"type": "technical", "enabled": True, "agent_ids": ["alex", "jordan"],
               "focus_areas": ["coding", "debugging", "customer_understanding"]}]
    original = deepcopy(rounds)
    metadata = {"round_configs": rounds}
    if source == "required_competencies":
        metadata["required_competencies"] = ["Coding", "debugging", "customer_understanding"]
    session = InterviewSession.from_config(InterviewConfiguration(
        interview_id="legacy-coding", candidate_id="candidate", agent_ids=["alex", "jordan"],
        metadata=metadata))
    InterviewSessionService._prepare_context_metadata(session)
    assert session.metadata["required_competencies"] == [
        "coding_problem_solving", "debugging", "customer_understanding"]
    assert session.metadata["competency_aliases_applied"] == {"coding": "coding_problem_solving"}
    assert session.metadata["unassigned_competencies"] == []
    assert session.metadata["round_configs"] == original
    owned = set(agent_registry.get_profile("alex").focal_competencies)
    assert next(c for c in session.metadata["required_competencies"] if c in owned) == "coding_problem_solving"


def test_canonical_and_alias_deduplicate_but_unknown_focus_remains_visible():
    session = InterviewSession.from_config(InterviewConfiguration(
        interview_id="deduplicated-coding", candidate_id="candidate", agent_ids=["alex"],
        metadata={"required_competencies": ["coding", "coding_problem_solving", "custom_topic"]}))
    InterviewSessionService._prepare_context_metadata(session)
    assert session.metadata["required_competencies"] == ["coding_problem_solving", "custom_topic"]
    assert session.metadata["unassigned_competencies"] == ["custom_topic"]


def test_coding_alias_does_not_assign_an_unconfigured_technical_interviewer():
    session = InterviewSession.from_config(InterviewConfiguration(
        interview_id="product-only", candidate_id="candidate", agent_ids=["jordan"],
        metadata={"required_competencies": ["coding", "customer_understanding"]}))
    InterviewSessionService._prepare_context_metadata(session)
    assert session.metadata["required_competencies"] == ["coding", "customer_understanding"]
    assert session.metadata["unassigned_competencies"] == ["coding"]


def test_coding_cv_opening_targets_implementation_before_debugging():
    session = InterviewSession.from_config(InterviewConfiguration(
        interview_id="coding-opening", candidate_id="candidate", agent_ids=["alex", "jordan"],
        job_title="Software Developer Intern", metadata={
            "candidate_name": "Sriram",
            "parsed_resume": {"projects": [{"name": "Learning Management System (LMS)",
                                             "technologies": ["React", "FastAPI", "PostgreSQL"]}]},
            "required_competencies": ["coding", "debugging", "customer_understanding"]}))
    InterviewSessionService._prepare_context_metadata(session)
    context = InterviewAIContext(interview_id=session.interview_id, candidate_id=session.candidate_id,
        current_agent_id="alex", current_round_id="technical", metadata=session.metadata,
        missing_competencies=session.metadata["required_competencies"])
    opening = generate_opening_question(agent_registry.get_profile("alex"), context)
    assert "Learning Management System (LMS)" in opening
    assert "feature you personally implemented" in opening
    assert "bug you investigated" not in opening
