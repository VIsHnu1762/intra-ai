"""A spoken question carries one assessable target through Meta and M1."""

import json

from app.agent_context.models import AgentTurnContext, CandidateProfileContext, JobContext
from app.agents.registry import AgentRegistry
from app.interview_context.models import InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis, InterviewAnswerInput
from app.interview_intelligence.prompts import build_m1_system_prompt, build_m1_user_prompt
from app.knowledge_graph.memory_models import PersistentCandidateMemory
from app.models.enums import DifficultyLevel
from app.orchestrator.prompts import build_nemotron_routing_messages


def context_with_question():
    contract = {
        "answer_anchor": "authenticate and access the DB",
        "information_target": "the check that permits database access",
        "expected_answer": "one authentication check",
        "objective": "apply",
    }
    ctx = InterviewAIContext(
        interview_id="specific-target", candidate_id="candidate", current_round_id="technical",
        current_agent_id="alex", missing_competencies=["system_design"],
        metadata={"configured_agent_ids": ["alex"], "required_competencies": ["system_design"],
                  "current_candidate_project": "LMS application", "current_candidate_subject": "authentication",
                  "candidate_context_correction": {"previous": "webmaster application", "current": "LMS application"}},
    )
    question = QuestionHistoryItem(
        agent_id="alex", competency="system_design", difficulty=DifficultyLevel.EASY,
        question_text="What does your API check before allowing database access?",
        metadata={"follow_up": contract, "unrelated_runtime_details": "must not enter the target"},
    )
    ctx.add_question_history(question)
    return ctx, question, contract


def meta_state(messages):
    body = messages[1]["content"].split("INTERVIEW STATE:\n", 1)[1]
    return json.JSONDecoder().raw_decode(body)[0]


def m1_context(prompt):
    body = prompt.split("### INTERVIEW CONTEXT\n", 1)[1]
    return json.JSONDecoder().raw_decode(body)[0]


def test_meta_gets_corrected_project_and_previous_information_target():
    ctx, question, contract = context_with_question()
    registry = AgentRegistry()
    analysis = AnswerAnalysis(answer_id="access-answer", overall_performance=.65, confidence=.8,
                              vague=False, contradiction_detected=False)
    turn = AgentTurnContext(
        candidate=CandidateProfileContext(candidate_id=ctx.candidate_id),
        job=JobContext(job_id="intern-job", title="Software Developer Intern", required_competencies=["system_design"]),
        persistent_memory=PersistentCandidateMemory(candidate_id=ctx.candidate_id),
        interview=ctx, agent=registry.get_profile("alex"),
        current_question=question.question_text, current_answer="It checks the candidate's password.",
    )
    messages = build_nemotron_routing_messages(ctx, analysis, registry,
        current_question_text=question.question_text, turn_context=turn,
        selected_priority="probe_missing_info", selected_target_competency="system_design")
    state = meta_state(messages)
    assert state["active_project"] == "LMS application"
    assert state["current_subject"] == "authentication"
    assert state["candidate_context_correction"] == ctx.metadata["candidate_context_correction"]
    assert state["question_history"][0]["follow_up"] == contract
    assert state["current_answer"] == turn.current_answer
    assert "unrelated_runtime_details" not in messages[1]["content"]
    assert "metadata.follow_up is REQUIRED for ASK_QUESTION" in messages[0]["content"]


def test_m1_uses_the_answered_question_contract_not_an_unanswered_newer_question():
    ctx, question, contract = context_with_question()
    ctx.add_question_history(QuestionHistoryItem(
        agent_id="alex", competency="system_design", difficulty=DifficultyLevel.EASY,
        question_text="Where do you store the password?",
        metadata={"follow_up": {"information_target": "password storage", "expected_answer": "one location"}},
    ))
    input_data = InterviewAnswerInput(answer_id="resume-answer", question_text=question.question_text,
        answer_text="The password.", context=ctx, agent_profile=AgentRegistry().get_profile("alex"))
    prompt = build_m1_user_prompt(input_data)
    state = m1_context(prompt)
    assert state["current_question_contract"] == contract
    assert state["active_project"] == "LMS application"
    assert state["candidate_context_correction"]["current"] == "LMS application"
    assert "one fact, not whether it demonstrates the entire competency" in build_m1_system_prompt(input_data.agent_profile)


def test_m1_does_not_borrow_a_target_when_the_question_is_absent_from_history():
    ctx, _, _ = context_with_question()
    input_data = InterviewAnswerInput(answer_id="opening-answer", question_text="What did you personally build?",
        answer_text="An LMS application.", context=ctx, agent_profile=AgentRegistry().get_profile("alex"))
    assert m1_context(build_m1_user_prompt(input_data))["current_question_contract"] is None


def test_unstructured_legacy_follow_up_metadata_is_safe_to_ignore():
    ctx, question, _ = context_with_question()
    question.metadata["follow_up"] = "legacy annotation"
    ctx.question_history = [question]
    input_data = InterviewAnswerInput(answer_id="legacy-answer", question_text=question.question_text,
        answer_text="The password.", context=ctx, agent_profile=AgentRegistry().get_profile("alex"))
    assert m1_context(build_m1_user_prompt(input_data))["current_question_contract"] is None
    analysis = AnswerAnalysis(answer_id="legacy-answer", overall_performance=.6, confidence=.8,
                              vague=False, contradiction_detected=False)
    assert meta_state(build_nemotron_routing_messages(ctx, analysis, AgentRegistry()))["question_history"][0]["follow_up"] is None
