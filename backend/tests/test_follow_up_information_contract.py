"""Keep the selected candidate fact when Meta returns broad spoken prose."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from app.agent_context.models import AgentTurnContext, CandidateProfileContext, JobContext
from app.agents.registry import AgentRegistry
from app.core.config import settings
from app.interview_context.models import EvidenceItem, InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.knowledge_graph.memory_models import PersistentCandidateMemory
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator.questions import validate_follow_up_contract, repair_follow_up_question
from app.orchestrator.service import MetaOrchestrator


ANSWER = "It should store candidates' data and information so that it can authenticate and access the DB."
CONTRACT = {
    "answer_anchor": "authenticate and access the DB",
    "information_target": "the candidate field used for authentication",
    "expected_answer": "one field name",
    "objective": "apply",
}
SPECIFIC = "Which candidate field does your LMS use for authentication?"


@pytest.mark.parametrize('target', ['candidate field used for authentication', 'the candidate field used for authentication'])
def test_repaired_noun_phrase_has_natural_article(target):
    question = repair_follow_up_question({**CONTRACT, 'information_target': target}, DifficultyLevel.EASY)
    assert question.endswith('What is the candidate field used for authentication?')


def run_question(question, *, contract=CONTRACT, previous=None, m1_probe=SPECIFIC):
    registry = AgentRegistry()
    ctx = InterviewAIContext(
        interview_id="specific-conversation", candidate_id="candidate", current_round_id="technical",
        current_agent_id="alex", missing_competencies=["system_design"],
        metadata={"configured_agent_ids": ["alex"], "required_competencies": ["system_design"],
                  "current_candidate_project": "LMS"},
    )
    ctx.add_question_history(QuestionHistoryItem(
        agent_id="alex", competency="system_design", difficulty=DifficultyLevel.EASY,
        question_text="What information does your LMS need to keep?",
        metadata={"objective_id": "system_design:purpose"},
    ))
    for item in previous or []:
        ctx.add_question_history(item)
    analysis = AnswerAnalysis(answer_id="authentication", overall_performance=.5, confidence=.9,
        vague=False, contradiction_detected=False,
        evidence=[EvidenceItem(id="auth-evidence", competency="system_design", signal=ANSWER, score=5)],
        competency_findings=[CompetencyFinding(competency_id="system_design", assessment="Names stored candidate data",
                            confidence=.9, evidence_ids=["auth-evidence"])],
        missing_information=["The field checked for authentication"], recommended_follow_up=m1_probe)
    turn = AgentTurnContext(candidate=CandidateProfileContext(candidate_id=ctx.candidate_id),
        job=JobContext(job_id="intern-job", title="Software Developer Intern", required_competencies=["system_design"]),
        persistent_memory=PersistentCandidateMemory(candidate_id=ctx.candidate_id), interview=ctx,
        agent=registry.get_profile("alex"), current_answer=ANSWER,
        current_question=ctx.question_history[0].question_text)
    response = {"action": "ASK_QUESTION", "target_agent_id": "alex", "competency": "system_design",
                "rationale": "Clarify one authentication fact.", "question_text": question,
                "metadata": {"follow_up": deepcopy(contract)} if contract is not None else {}}
    model = AsyncMock(return_value=response)
    with patch.object(settings, "ORCHESTRATOR_PROVIDER", "aicredits"), \
         patch("app.orchestrator.graph.generate_intelligence", model), \
         patch("app.orchestrator.graph.call_groq", side_effect=AssertionError("No other provider")):
        action = asyncio.run(MetaOrchestrator(registry).decide_async(ctx, analysis,
            current_question_text=turn.current_question, turn_context=turn))
    return action, ctx, model


@pytest.mark.parametrize("prose", [
    "How does authentication work in your LMS, and how does that interact with database storage?",
    "What should happen if one part of your LMS stops working?",
    "Can you describe your overall architecture?",
    "How would you design a quantum computer?",
])
def test_valid_information_plan_repairs_broad_or_unrelated_meta_prose(prose):
    action, _, model = run_question(prose)
    model.assert_awaited_once()
    assert action.action == ActionType.ASK_QUESTION
    assert action.question_text == (
        "You mentioned authenticate and access the DB. What is the candidate field used for authentication?")
    assert action.metadata["follow_up_question_repaired"] is True
    assert action.metadata["follow_up"] == CONTRACT
    assert action.metadata["objective_id"] == "system_design:apply"
    assert action.metadata["question_source"] == "meta"


def test_specific_meta_question_keeps_actual_target_and_objective_in_history():
    action, ctx, model = run_question(SPECIFIC)
    model.assert_awaited_once()
    assert action.question_text == SPECIFIC
    assert "follow_up_question_repaired" not in action.metadata
    MetaOrchestrator.record_question(ctx, action)
    assert ctx.question_history[-1].metadata["follow_up"] == CONTRACT
    assert ctx.question_history[-1].metadata["objective_id"] == "system_design:apply"
    # History owns a snapshot, not the mutable model response.
    action.metadata["follow_up"]["information_target"] = "changed"
    assert ctx.question_history[-1].metadata["follow_up"] == CONTRACT


def test_invented_anchor_is_rejected_and_existing_m1_fact_is_used():
    invented = {**CONTRACT, "answer_anchor": "Redis payment queue"}
    action, _, model = run_question("What is stored in the Redis payment queue?", contract=invented)
    model.assert_awaited_once()
    assert action.question_text == SPECIFIC
    assert action.metadata["question_source"] == "m1"
    assert action.metadata["follow_up_rejected"] == "anchor_not_in_answer"
    assert "follow_up" not in action.metadata
    assert "Redis" not in action.question_text


@pytest.mark.parametrize("prose", [
    "What should happen if one part of your LMS stops working?",
    "If your LMS returned a wrong result, what would you check first?",
    "How does authentication work, and what data does the API store, and how is it validated?",
])
def test_legacy_meta_broad_prose_uses_m1_specific_fact_before_bank(prose):
    action, _, model = run_question(prose, contract=None)
    model.assert_awaited_once()
    assert action.question_text == SPECIFIC
    assert action.metadata["question_source"] == "m1"


def test_rewording_target_cannot_reopen_an_objective():
    old = QuestionHistoryItem(agent_id="alex", competency="system_design", difficulty=DifficultyLevel.EASY,
        question_text=SPECIFIC, metadata={"objective_id": "system_design:apply", "follow_up": CONTRACT})
    action, _, _ = run_question("What field does authentication use for a candidate?", previous=[old])
    assert action.question_text != SPECIFIC
    assert action.metadata.get("objective_id") != "system_design:apply"
    assert "follow_up" not in action.metadata


def test_rewording_objective_cannot_reopen_the_same_information_target():
    old = QuestionHistoryItem(agent_id="alex", competency="system_design", difficulty=DifficultyLevel.EASY,
        question_text=SPECIFIC, metadata={"objective_id": "system_design:apply", "follow_up": CONTRACT})
    reworded = {**CONTRACT, "objective": "verify"}
    action, _, _ = run_question("What field does authentication use for a candidate?", contract=reworded, previous=[old])
    assert "follow_up" not in action.metadata
    assert action.question_text != SPECIFIC


def test_all_four_objectives_remain_a_finite_limit():
    previous = [QuestionHistoryItem(agent_id="alex", competency="system_design", difficulty=DifficultyLevel.EASY,
        question_text=f"Earlier {objective} question?", exploration_status="PARTIAL",
        metadata={"objective_id": f"system_design:{objective}", "answered_by": f"old-{objective}"})
        for objective in ("apply", "verify", "limits")]
    action, _, _ = run_question(SPECIFIC, previous=previous)
    assert action.action == ActionType.COMPLETE
    assert "follow_up" not in action.metadata


@pytest.mark.parametrize("change,reason", [
    ({"answer_anchor": "auth"}, "anchor_not_in_answer"),
    ({"information_target": "the architecture and implementation of authentication"}, "target_not_single_fact"),
    ({"information_target": "How does authentication work"}, "target_not_single_fact"),
    ({"expected_answer": "an overview of the entire application"}, "unbounded_expected_answer"),
    ({"objective": "new-target"}, "invalid_objective"),
])
def test_contract_rejects_unbounded_or_unsupported_targets(change, reason):
    contract, error = validate_follow_up_contract({**CONTRACT, **change}, ANSWER)
    assert contract is None and error == reason


def test_anchor_matching_normalizes_case_and_whitespace_without_inventing_words():
    contract, error = validate_follow_up_contract(
        {**CONTRACT, "answer_anchor": "AUTHENTICATE  and access the DB"}, ANSWER)
    assert error is None
    assert contract["answer_anchor"] == "AUTHENTICATE and access the DB"
