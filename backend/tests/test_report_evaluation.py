"""Post-interview aggregation covers mode/provenance boundaries without models."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services.report_evaluation import (
    MAX_SOURCE_RECORDS, ReportEvidenceUnavailable, ReportSourceInvalid,
    build_evaluation, recover_source_from_graph,
)


def source(round_count=1, agents=("alex",)):
    rounds = [{"id": f"round-{index}", "type": "technical", "name": f"Technical {index}",
               "agent_ids": list(agents), "duration_minutes": 15, "enabled": True}
              for index in range(round_count)]
    interview = {"id": "interview-a", "candidate_id": "candidate-a", "status": "completed",
                 "template_snapshot": {"rounds": rounds, "template_version": 1}}
    context = {"interview_id": "interview-a", "candidate_id": "candidate-a", "current_round_id": rounds[-1]["id"],
               "accumulated_evidence": [], "metadata": {"api_token": "DO_NOT_COPY", "candidate_profile": {"private": "DO_NOT_COPY"}}}
    answers = []
    for row in rounds:
        for agent in agents:
            for number, score in enumerate((2, 8)):
                aid = f"answer-{row['id']}-{agent}-{number}"
                context["accumulated_evidence"].append({"id": f"evidence-{aid}", "competency": "coding", "score": score,
                    "signal": f"Observed reasoning {aid}", "round_id": row["id"], "source_agent_id": agent,
                    "metadata": {"answer_id": aid, "private": "DO_NOT_COPY"}})
                answers.append({"id": aid, "interview_id": "interview-a", "round_id": row["id"], "agent_id": agent,
                    "transcript": f"Actual answer {aid}", "question_text": "Explain your choice."})
    return interview, context, answers


@pytest.mark.parametrize("round_count,agents", [(1, ("alex",)), (2, ("alex",)), (1, ("alex", "jordan")), (2, ("alex", "jordan"))])
def test_all_four_modes_aggregate_all_answers_and_keep_rounds_independent_from_agents(round_count, agents):
    interview, context, answers = source(round_count, agents)
    before = deepcopy((interview, context, answers))
    result = build_evaluation(interview, context, [], answers)
    assert result["overall_score"] == 50  # Both weak and strong answers, not only the final score of8.
    assert result["scoring_method"] == "m1_evidence_mean"
    assert len(result["round_assessments"]) == round_count
    assert {row["round_id"] for row in result["round_assessments"]} == {f"round-{index}" for index in range(round_count)}
    assert all(row["round_type"] == "technical" and row["agent_ids"] == list(agents) for row in result["round_assessments"])
    assert len(result["evidence"]) == len(result["answers"]) == round_count * len(agents) * 2
    assert result["coverage"]["unobserved_rounds"] == result["coverage"]["missing_answer_ids"] == []
    assert result["counts"]["evaluated_answers"] == len(answers)
    assert result["coverage"]["evaluated_answer_count"] == result["coverage"]["scored_answer_count"] == len(answers)
    assert result["coverage"]["answer_identity_complete"] is True
    assert len(result["competency_findings"]) == 1
    assert set(result["competency_findings"][0]["evidence_ids"]) == {row["id"] for row in result["evidence"]}
    assert "DO_NOT_COPY" not in json.dumps(result)
    assert (interview, context, answers) == before


def test_duplicate_evidence_id_does_not_double_weight_an_answer():
    interview, context, answers = source()
    context["accumulated_evidence"].append(deepcopy(context["accumulated_evidence"][0]))
    result = build_evaluation(interview, context, [], answers)
    assert result["overall_score"] == 50 and result["counts"]["scored_evidence"] == 2


def test_multiple_competency_findings_from_one_answer_never_imply_multiple_answers():
    interview, context, answers = source()
    context["accumulated_evidence"][1]["metadata"]["answer_id"] = answers[0]["id"]
    context["accumulated_evidence"][1]["competency"] = "communication"
    result = build_evaluation(interview, context, [], answers)
    assert result["counts"]["scored_evidence"] == 2
    assert result["coverage"]["evaluated_answer_count"] == result["coverage"]["scored_answer_count"] == 1


def test_unknown_answer_links_are_incomplete_even_with_several_scores_and_transcripts():
    interview, context, answers = source()
    for row in context["accumulated_evidence"]:
        row["metadata"] = {}
    result = build_evaluation(interview, context, [], answers)
    assert result["overall_score"] == 50
    assert result["counts"]["answers"] == 2
    assert result["coverage"]["evaluated_answer_count"] == result["coverage"]["scored_answer_count"] == 0
    assert result["coverage"]["answer_identity_complete"] is False
    assert len(result["coverage"]["unlinked_scored_evidence_ids"]) == 2


def test_recorded_assessment_recovers_exact_evidence_answer_link_and_deduplicates_answers():
    interview, context, answers = source()
    first, second = context["accumulated_evidence"]
    first["metadata"] = {}
    context["question_history"] = [{"id": "q-a", "question_text": "Explain?", "metadata": {
        "answered_by": answers[0]["id"], "assessment_outcome": {"evidence_ids": [first["id"]]}}},
        {"id": "q-b", "question_text": "Explain next?", "metadata": {"answered_by": answers[1]["id"]}},
        {"id": "q-unanswered", "question_text": "Unused question?"}]
    result = build_evaluation(interview, context, [], answers)
    assert result["coverage"]["evaluated_answer_count"] == result["coverage"]["scored_answer_count"] == 2
    assert result["coverage"]["answer_identity_complete"] is True
    assert result["evidence"][0]["answer_id"] == answers[0]["id"]
    context["question_history"][0]["metadata"]["assessment_outcome"]["evidence_ids"] = [second["id"]]
    with pytest.raises(ReportSourceInvalid):
        build_evaluation(interview, context, [], answers)


def test_answered_question_without_evidence_link_does_not_inflate_scored_answer_count():
    interview, context, answers = source()
    context["accumulated_evidence"] = context["accumulated_evidence"][:1]
    context["question_history"] = [{"id": "q-a", "metadata": {"answered_by": answers[1]["id"]}}]
    result = build_evaluation(interview, context, [], answers)
    assert result["coverage"]["evaluated_answer_count"] == 2
    assert result["coverage"]["scored_answer_count"] == 1


@pytest.mark.parametrize("value", [None, True, "7", float("nan"), float("inf"), -1, 11])
def test_absent_invalid_or_unscored_evidence_never_becomes_a_zero_score(value):
    interview, context, answers = source()
    for row in context["accumulated_evidence"]:
        row["score"] = value
    with pytest.raises(ReportEvidenceUnavailable):
        build_evaluation(interview, context, [], answers)
    with pytest.raises(ReportEvidenceUnavailable):
        build_evaluation(interview, None, [], answers)


def test_actual_scored_zero_is_retained_and_unscored_items_are_not_weaknesses():
    interview, context, answers = source()
    context["accumulated_evidence"][0]["score"] = 0
    context["accumulated_evidence"][1]["score"] = None
    result = build_evaluation(interview, context, [], answers)
    assert result["overall_score"] == 0
    assert result["counts"]["evidence"] == 2 and result["counts"]["scored_evidence"] == 1
    assert result["improvements"] == [context["accumulated_evidence"][0]["signal"]]


def test_snapshot_round_plan_overrides_edited_job_and_keeps_unobserved_rounds_unscored():
    interview, context, answers = source(2)
    context["accumulated_evidence"] = context["accumulated_evidence"][:2]
    interview["jobs"] = {"interview_rounds": [{"id": "new-round", "type": "behavioral", "agent_ids": ["jordan"]}]}
    result = build_evaluation(interview, context, [], answers)
    assert len(result["round_assessments"]) == 1
    assert result["coverage"]["unobserved_rounds"][0]["round_id"] == "round-1"
    assert {row["round_id"] for row in result["coverage"]["configured_rounds"]} == {"round-0", "round-1"}


def test_round_with_unscored_evidence_remains_only_in_coverage():
    interview, context, answers = source(2)
    for row in context["accumulated_evidence"][2:]:
        row["score"] = None
    result = build_evaluation(interview, context, [], answers)
    assert len(result["round_assessments"]) == 1
    assert result["coverage"]["unobserved_rounds"][0]["round_id"] == "round-1"
    assert len(result["evidence"]) == 4


def test_repeated_round_types_do_not_invent_observed_distinct_rounds_or_agent_handoffs():
    interview, context, _ = source(2, ("alex", "jordan"))
    context["accumulated_evidence"][0]["round_id"] = "technical"
    context["accumulated_evidence"] = context["accumulated_evidence"][:1]
    result = build_evaluation(interview, context, [], [])
    assert result["round_assessments"][0]["round_id"] == "technical"
    assert result["round_assessments"][0]["identity_resolution"] == "unresolved"
    assert len(result["coverage"]["unobserved_rounds"]) == 2
    assert result["handoffs"] == []
    assert result["coverage"]["missing_answer_ids"]


def test_missing_provenance_is_not_relabelled_with_the_final_round_or_agent():
    interview, context, _ = source()
    for row in context["accumulated_evidence"]:
        row.pop("round_id")
        row.pop("source_agent_id")
    context["current_agent_id"] = "jordan"
    result = build_evaluation(interview, context, [], [])
    assert result["round_assessments"][0]["round_id"] == "unknown"
    assert result["round_assessments"][0]["round_type"] == "unknown"
    assert result["coverage"]["observed_agent_ids"] == []


def test_recorded_question_and_handoff_provenance_are_allowlisted():
    interview, context, answers = source()
    context["question_history"] = [{"id": "question-a", "agent_id": "alex", "question_text": "Explain your choice.",
        "metadata": {"round_id": "round-0", "answered_by": answers[0]["id"], "api_token": "DO_NOT_COPY"}}]
    context["metadata"]["handoff_history"] = [{"from_agent_id": "alex", "to_agent_id": "jordan", "status": "completed",
                                               "round_id": "round-0", "api_token": "DO_NOT_COPY"}]
    result = build_evaluation(interview, context, [], answers)
    assert result["question_history"][0]["answer_id"] == answers[0]["id"]
    assert result["handoffs"] == [{"from_agent_id": "alex", "to_agent_id": "jordan", "status": "completed", "round_id": "round-0"}]
    assert "DO_NOT_COPY" not in json.dumps(result)


def test_snapshot_is_strict_json_with_datetimes_and_does_not_copy_objects_in_whitelisted_fields():
    interview, context, answers = source()
    now = datetime(2026, 9, 6, tzinfo=timezone.utc)
    answers[0]["created_at"] = context["accumulated_evidence"][0]["timestamp"] = now
    answers[0]["duration_seconds"] = float("nan")
    context["question_history"] = [{"id": {"secret": "DO_NOT_COPY"}, "timestamp": now,
                                    "exploration_status": {"secret": "DO_NOT_COPY"}}]
    context["metadata"]["handoffs"] = [{"from_agent_id": {"secret": "DO_NOT_COPY"}, "timestamp": now}]
    interview["template_snapshot"]["rounds"][0]["agent_ids"].append({"secret": "DO_NOT_COPY"})
    interview["template_snapshot"]["rounds"][0]["duration_minutes"] = {"secret": "DO_NOT_COPY"}
    result = build_evaluation(interview, context, [], answers)
    serialized = json.dumps(result, allow_nan=False)
    assert "DO_NOT_COPY" not in serialized
    assert result["answers"][0]["created_at"] == now.isoformat()
    assert result["evidence"][0]["timestamp"] == now.isoformat()
    assert result["handoffs"][0]["timestamp"] == now.isoformat()


@pytest.mark.parametrize("part", ["context", "evidence", "answer", "evaluation", "question"])
def test_cross_interview_sources_fail_closed(part):
    interview, context, answers = source()
    evaluations = []
    if part == "context":
        context["interview_id"] = "other-interview"
    elif part == "evidence":
        context["accumulated_evidence"][0]["candidate_id"] = "other-candidate"
    elif part == "answer":
        answers[0]["interview_id"] = "other-interview"
    elif part == "question":
        answers[0]["interview_questions"] = {"interview_id": "other-interview"}
    else:
        evaluations = [{"id": "eval", "interview_id": "other-interview", "overall": 9}]
    with pytest.raises(ReportSourceInvalid):
        build_evaluation(interview, context, evaluations, answers)


def test_legacy_overall_keeps_type_mean_weighting_while_display_preserves_distinct_round_ids():
    interview, _, _ = source(2)
    evaluations = []
    for index, (rid, kind, score) in enumerate([("tech-a", "technical", 2), ("tech-b", "technical", 4), ("behavior-a", "behavioral", 9)]):
        evaluations.append({"id": f"evaluation-{index}", "interview_id": interview["id"], "overall": score,
            "answer_id": f"answer-{index}", "feedback": f"Actual finding {index}",
            "candidate_answers": {"id": f"answer-{index}", "interview_id": interview["id"], "transcript": f"Actual response {index}",
                "interview_questions": {"round_id": rid, "round_type": kind, "text": "Explain?", "agent_id": "alex"}}})
    result = build_evaluation(interview, None, evaluations, [])
    assert result["overall_score"] == 60  # Mean(technical mean3, behavioral mean9) *10, not turn mean5.
    assert result["scoring_method"] == "legacy_round_type_mean"
    assert len(result["round_assessments"]) == 3 and len(result["answers"]) == 3
    assert [row["round_type"] for row in result["round_assessments"]] == ["technical", "technical", "behavioral"]
    assert result["coverage"]["scored_answer_count"] == 3


def graph_fixture():
    rounds = [{"round_id": "kg-round-a", "candidate_id": "candidate-a", "interview_id": "interview-a", "round_type": "technical"},
              {"round_id": "kg-old-round", "candidate_id": "candidate-a", "interview_id": "old-interview", "round_type": "technical"}]
    evidence = {"evidence_id": "kg-evidence", "answer_id": "kg-answer", "candidate_id": "candidate-a", "round_id": "kg-round-a",
                "source_agent_id": "alex", "competency": "coding", "signal": "Actual observed tradeoff", "score": 7}
    answer = {"answer_id": "kg-answer", "question_id": "kg-question", "candidate_id": "candidate-a", "round_id": "kg-round-a", "answer_text": "I used a transaction."}
    question = {"question_id": "kg-question", "round_id": "kg-round-a", "agent_id": "alex", "question_text": "How did you protect data?"}
    return SimpleNamespace(get_candidate_interview_rounds=Mock(return_value=rounds),
        get_candidate_evidence=Mock(return_value=[evidence]), get_answer=Mock(return_value=answer), get_question=Mock(return_value=question))


def test_graph_recovery_fetches_only_verified_same_interview_round_evidence():
    interview, _, _ = source()
    graph = graph_fixture()
    recovered = recover_source_from_graph(interview, graph)
    graph.get_candidate_evidence.assert_called_once_with("candidate-a", round_id="kg-round-a", limit=MAX_SOURCE_RECORDS + 1)
    result = build_evaluation(interview, recovered["context"], recovered["evaluations"], recovered["answers"])
    assert result["overall_score"] == 70
    assert result["answers"][0]["answer_text"] == "I used a transaction."
    assert result["round_assessments"][0]["round_id"] == "kg-round-a"
    assert "old-interview" not in json.dumps(result)


def test_graph_recovery_accepts_only_exact_durable_channel_alias_for_same_candidate():
    interview, _, _ = source()
    graph = graph_fixture()
    graph.get_candidate_interview_rounds.return_value[0]["interview_id"] = "intra-interview-a"
    graph.get_candidate_interview_rounds.return_value += [
        {"round_id": "wrong-prefix", "interview_id": "foreign-intra-interview-a", "candidate_id": "candidate-a"},
        {"round_id": "wrong-suffix", "interview_id": "intra-interview-a-other", "candidate_id": "candidate-a"}]
    recovered = recover_source_from_graph(interview, graph)
    assert recovered["context"]["interview_id"] == interview["id"]
    assert recovered["context"]["metadata"]["graph_interview_ids"] == ["intra-interview-a"]
    graph.get_candidate_evidence.assert_called_once_with("candidate-a", round_id="kg-round-a", limit=MAX_SOURCE_RECORDS + 1)
    evaluated = build_evaluation(interview, recovered["context"], [], recovered["answers"])
    assert evaluated["overall_score"] == 70
    assert evaluated["provenance"]["graph_interview_ids"] == ["intra-interview-a"]
    graph.get_candidate_interview_rounds.return_value[0]["candidate_id"] = "foreign-candidate"
    with pytest.raises(ReportSourceInvalid): recover_source_from_graph(interview, graph)


def test_graph_recovery_rejects_one_answer_claimed_by_two_distinct_rounds():
    interview, _, _ = source()
    graph = graph_fixture()
    graph.get_candidate_interview_rounds.return_value[1] = {
        "round_id": "kg-round-b", "candidate_id": "candidate-a", "interview_id": "interview-a", "round_type": "behavioral"}
    original = deepcopy(graph.get_candidate_evidence.return_value)
    graph.get_candidate_evidence.side_effect = [original, [{**original[0], "round_id": "kg-round-b"}]]
    with pytest.raises(ReportSourceInvalid): recover_source_from_graph(interview, graph)


@pytest.mark.parametrize("part", ["round", "evidence", "answer", "question", "answer_id", "question_id"])
def test_graph_recovery_rejects_mismatched_provenance(part):
    interview, _, _ = source()
    graph = graph_fixture()
    if part == "round":
        graph.get_candidate_interview_rounds.return_value[0]["candidate_id"] = "other"
    elif part == "evidence":
        graph.get_candidate_evidence.return_value[0]["round_id"] = "other"
    elif part == "answer":
        graph.get_answer.return_value["candidate_id"] = "other"
    elif part == "answer_id":
        graph.get_answer.return_value["answer_id"] = "other"
    elif part == "question_id":
        graph.get_question.return_value["question_id"] = "other"
    else:
        graph.get_question.return_value["round_id"] = "other"
    with pytest.raises(ReportSourceInvalid):
        recover_source_from_graph(interview, graph)


@pytest.mark.parametrize("part", ["rounds", "evidence"])
def test_graph_recovery_refuses_silent_truncation(part):
    interview, _, _ = source()
    graph = graph_fixture()
    if part == "rounds":
        graph.get_candidate_interview_rounds.return_value *= MAX_SOURCE_RECORDS
    else:
        graph.get_candidate_evidence.return_value *= MAX_SOURCE_RECORDS + 1
    with pytest.raises(ReportSourceInvalid):
        recover_source_from_graph(interview, graph)
