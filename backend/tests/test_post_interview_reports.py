"""Persisted report lifecycle and candidate projection, with no live providers."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from threading import Event, RLock
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.integrations.aicredits_client import AICreditsError
from app.services import report_service
from app.services.report_evaluation import ReportEvidenceUnavailable
from app.services.report_service import ReportService, _ready, rating_from_score, _narrative_assessment
from tests.test_recruiter_workspace import headers, workspace


def sources():
    interview = {"id": "interview-a", "candidate_id": "candidate-a", "status": "completed",
        "candidates": {"id": "candidate-a", "name": "Fictional Sam", "email": "private@example.test"},
        "jobs": {"id": "job-a", "title": "Software Developer", "private_notes": "DO_NOT_COPY"},
        "template_snapshot": {"rounds": [
            {"id": "round-a", "type": "technical", "agent_ids": ["alex", "jordan"], "duration_minutes": 15},
            {"id": "round-b", "type": "behavioral", "agent_ids": ["alex", "jordan"], "duration_minutes": 15}]}}
    context = {"interview_id": "interview-a", "candidate_id": "candidate-a", "accumulated_evidence": []}
    answers = []
    for index, score in enumerate((2, 8, 4, 10)):
        rid, agent, aid = ("round-a" if index < 2 else "round-b"), ("alex" if index % 2 == 0 else "jordan"), f"answer-{index}"
        context["accumulated_evidence"].append({"id": f"evidence-{index}", "score": score,
            "signal": f"Observed finding {index}", "competency": "reasoning", "round_id": rid,
            "source_agent_id": agent, "metadata": {"answer_id": aid}})
        answers.append({"id": aid, "interview_id": "interview-a", "transcript": f"Actual answer {index}",
            "question_text": "Explain your approach.", "round_id": rid, "agent_id": agent})
    return interview, {"version": 1, "context": context, "transcripts": []}, answers


class PersistedReports:
    """Controlled durable repository honoring the production attempt-fencing contract.

    It exercises service orchestration; it does not claim to test PostgreSQL RPC
    locking itself. The same stored rows survive replacement service instances.
    """
    def __init__(self):
        self.interview, self.captured, self.answers = sources()
        self.report = None
        self.evaluations = []
        self.claims = self.finishes = 0
        self.progress = []
        self.lock = RLock()

    async def get_by_id(self, iid):
        return deepcopy(self.interview) if iid == self.interview["id"] else None

    async def get_report(self, iid):
        return deepcopy(self.report) if iid == self.interview["id"] else None

    async def get_report_by_id(self, rid):
        return deepcopy(self.report) if self.report and rid == self.report["id"] else None

    async def get_evaluations(self, _iid): return deepcopy(self.evaluations)
    async def get_answers(self, _iid): return deepcopy(self.answers)

    async def claim_report(self, _iid, attempt, source):
        with self.lock:
            self.claims += 1
            if self.report and self.report.get("candidate_feedback"):
                return {"status": "ready", "report_id": self.report["id"]}
            state = self.interview.get("report_generation") or {}
            if state.get("status") == "generating":
                started = datetime.fromisoformat(state["started_at"])
                if started > datetime.now(timezone.utc) - timedelta(minutes=5):
                    return deepcopy(state)
            state = {"status": "generating", "attempt_id": attempt, "started_at": datetime.now(timezone.utc).isoformat()}
            self.interview["report_generation"] = state
            if self.interview.get("report_source") is None:
                self.interview["report_source"] = deepcopy(source)
            return deepcopy(state)

    def _fence(self, attempt):
        state = self.interview.get("report_generation") or {}
        if state.get("attempt_id") != attempt or state.get("status") != "generating":
            raise ConflictError("Report generation attempt was superseded")

    async def save_report_progress(self, _iid, attempt, data):
        with self.lock:
            self._fence(attempt)
            json.dumps(data, allow_nan=False)
            self.interview.update(deepcopy(data))
            self.progress.append(deepcopy(data))

    async def finish_report(self, _iid, attempt, report):
        with self.lock:
            self._fence(attempt)
            self.finishes += 1
            self.report = deepcopy(report)
            self.interview["report_generation"] = {"status": "ready", "report_id": report["id"]}
            self.interview["report_draft"] = None
            return deepcopy(report)


def narrative():
    return {"overall_summary": "The candidate demonstrated mixed reasoning across both observed interview rounds.",
        "strengths": [{"text": "Explained an effective approach in the stronger answers.", "evidence_ids": ["evidence-1", "evidence-3"]}],
        "improvements": [{"text": "Develop clearer reasoning in the weaker answers.", "evidence_ids": ["evidence-0", "evidence-2"]}]}


def feedback():
    return {"strength": "You explained several useful approaches during the interview.",
            "improvement": "Practice explaining each decision and its trade-offs more clearly."}


def test_narrative_input_preserves_all_answers_evidence_and_coverage_without_duplicates():
    assessment = {
        "interview_id": "private-interview", "candidate_id": "private-candidate", "overall_score": 62,
        "answers": [{"answer_id": f"answer-{i}", "question_text": f"Question {i}",
                     "answer_text": f"Answer {i}", "agent_id": "alex" if i < 5 else "jordan"} for i in range(9)],
        "evidence": [{"id": f"evidence-{i}", "answer_id": f"answer-{i}", "score": i,
                      "signal": f"Evidence {i}"} for i in range(9)],
        "coverage": {"missing_answer_ids": [], "scored_answer_count": 9,
                     "observed_agent_ids": ["alex", "jordan"], "unobserved_rounds": ["culture"]},
        "transcripts": [{"text": "Duplicated spoken transcript"}],
        "question_history": [{"question_text": "Duplicated question"}],
        "provenance": {"source_interview_id": "private-interview"},
    }
    original = deepcopy(assessment)
    payload = _narrative_assessment(assessment)
    assert payload["answers"] == assessment["answers"]
    assert payload["evidence"] == assessment["evidence"]
    assert payload["coverage"] == assessment["coverage"]
    assert payload["overall_score"] == 62
    assert set(payload).isdisjoint({"transcripts", "question_history", "candidate_id", "interview_id", "provenance"})
    assert assessment == original  # Durable source and final detailed report stay complete.
    payload["evidence"][0]["signal"] = "Changed locally"
    assert assessment == original


def test_narrative_keeps_transcripts_when_answer_text_recovery_is_incomplete():
    assessment = {"answers": [{"answer_id": "a1", "answer_text": "First answer"}],
                  "coverage": {"missing_answer_ids": ["a2"]},
                  "transcripts": [{"text": "Second answer"}], "question_history": [{"question_text": "Question two"}]}
    payload = _narrative_assessment(assessment)
    assert payload["transcripts"] == assessment["transcripts"]
    assert payload["question_history"] == assessment["question_history"]


@pytest.fixture
def workflow(monkeypatch):
    repo = PersistedReports()
    monkeypatch.setattr(report_service, "_capture_source", lambda _iid: deepcopy(repo.captured))
    graph = Mock(side_effect=ReportEvidenceUnavailable())
    monkeypatch.setattr(ReportService, "_recover_graph", staticmethod(graph))
    nano, gemini = AsyncMock(return_value=narrative()), AsyncMock(return_value=feedback())
    monkeypatch.setattr(report_service.aicredits_client, "generate_report_narrative", nano)
    monkeypatch.setattr(report_service.aicredits_client, "generate_candidate_feedback", gemini)
    return SimpleNamespace(repo=repo, service=ReportService(repo, Mock()), nano=nano, gemini=gemini, graph=graph)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["scheduled", "in_progress", "cancelled"])
async def test_incomplete_interview_never_claims_or_calls_report_providers(workflow, status):
    w = workflow
    w.repo.interview["status"] = status
    assert (await w.service.status("interview-a")).status == "not_completed"
    for method in (w.service.generate_report, w.service.request_report):
        with pytest.raises(ConflictError):
            await method("interview-a")
    assert w.repo.claims == 0 and w.repo.report is None
    w.nano.assert_not_called(); w.gemini.assert_not_called(); w.graph.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_interview_returns_not_found(workflow):
    for method in (workflow.service.status, workflow.service.generate_report):
        with pytest.raises(NotFoundError):
            await method("missing")
    workflow.nano.assert_not_called()


@pytest.mark.asyncio
async def test_narrative_timeout_preserves_source_and_retries_to_both_projections(workflow):
    w = workflow
    w.nano.side_effect = AICreditsError("timeout", retryable=True)
    with pytest.raises(ValidationError):
        await w.service.generate_report("interview-a")
    status = await w.service.status("interview-a")
    assert status.status == "failed" and status.retryable
    assert status.error_code == "AICREDITS_TIMEOUT"
    assert "answers are saved" in status.message
    assert w.repo.interview["report_generation"]["stage"] == "narrative"
    saved = deepcopy(w.repo.interview["report_source"])
    assert saved["evaluation"]["coverage"]["scored_answer_count"] == 4
    assert (await w.service.candidate_performance("interview-a")).status == "failed"
    w.gemini.assert_not_called()
    w.nano.side_effect = None
    result = await w.service.generate_report("interview-a")
    candidate = await w.service.candidate_performance("interview-a")
    assert (await w.service.status("interview-a")).status == candidate.status == "ready"
    assert result.interview_id == candidate.interview_id == "interview-a"
    assert candidate.rating == result.candidate_rating and len(candidate.feedback) == 3
    assert w.repo.interview["report_source"] == saved
    assert w.nano.await_count == 2 and w.gemini.await_count == 1 and w.repo.finishes == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("state,expected", [
    ({}, "not_started"),
    ({"status": "generating", "attempt_id": "active", "started_at": datetime.now(timezone.utc).isoformat()}, "generating"),
    ({"status": "generating", "attempt_id": "old", "started_at": "2020-01-01T00:00:00+00:00"}, "failed"),
    ({"status": "generating", "started_at": "not a timestamp"}, "failed"),
    ({"status": "generating", "started_at": datetime.now(timezone.utc).isoformat()}, "failed"),
    ({"status": "failed", "error_code": "REPORT_OUTPUT_INVALID"}, "failed"),
])
async def test_report_status_is_explicit_and_read_only(workflow, state, expected):
    w = workflow
    w.repo.interview["report_generation"] = state
    result = await w.service.status("interview-a")
    candidate = await w.service.candidate_performance("interview-a")
    assert result.status == candidate.status == expected
    assert result.retryable is (expected in {"not_started", "failed"})
    assert candidate.rating is None and candidate.feedback is None
    assert candidate.message and w.repo.progress == [] and w.repo.claims == 0
    w.nano.assert_not_called(); w.gemini.assert_not_called()


@pytest.mark.asyncio
async def test_report_uses_all_rounds_agents_and_answers_and_persists_before_providers(workflow):
    w = workflow
    async def generate(assessment):
        assert w.repo.interview["report_source"]["evaluation"]["overall_score"] == 60
        assert assessment["overall_score"] == 60 and assessment["star_rating"] == 3.4
        assert assessment["coverage"]["scored_answer_count"] == 4
        return narrative()
    async def generate_feedback(assessment, draft):
        assert w.repo.interview["report_draft"] == draft
        assert assessment["overall_score"] == 60
        return feedback()
    w.nano.side_effect, w.gemini.side_effect = generate, generate_feedback
    result = await w.service.generate_report("interview-a")
    assert result.overall_score == 60 and result.candidate_rating == 3.4
    assert {row.round_id for row in result.round_assessments} == {"round-a", "round-b"}
    assert all(row.agent_ids == ["alex", "jordan"] for row in result.round_assessments)
    assert len(result.analysis["answers"]) == 4 and len(result.candidate_feedback) == 3
    assert result.candidate == {"id": "candidate-a", "name": "Fictional Sam"}
    assert result.job == {"id": "job-a", "title": "Software Developer"}
    assert w.repo.finishes == 1 and (await w.service.status("interview-a")).status == "ready"
    w.graph.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["one_answer", "one_scored_plus_answered_question", "unknown_links", "no_scores"])
async def test_insufficient_overall_coverage_never_creates_rating_or_calls_models(workflow, case):
    w = workflow
    context = w.repo.captured["context"]
    if case in {"one_answer", "one_scored_plus_answered_question"}:
        for item in context["accumulated_evidence"]:
            item["metadata"]["answer_id"] = "answer-0"
        if case.endswith("question"):
            context["question_history"] = [{"id": "question-other", "metadata": {"answered_by": "answer-1"}}]
    elif case == "unknown_links":
        for item in context["accumulated_evidence"]: item["metadata"] = {}
    else:
        for item in context["accumulated_evidence"]: item["score"] = None
    with pytest.raises(ValidationError):
        await w.service.generate_report("interview-a")
    assert (await w.service.status("interview-a")).error_code == "REPORT_EVIDENCE_UNAVAILABLE"
    assert w.repo.report is None and w.repo.finishes == 0
    assert (await w.service.candidate_performance("interview-a")).rating is None
    w.nano.assert_not_called(); w.gemini.assert_not_called()


@pytest.mark.asyncio
async def test_graph_only_enriches_exact_context_evidence_links_and_does_not_rescore(workflow):
    w = workflow
    recovery_context = deepcopy(w.repo.captured["context"])
    for item in w.repo.captured["context"]["accumulated_evidence"]: item["metadata"] = {}
    for item in recovery_context["accumulated_evidence"]: item["score"] = 10
    recovery_context["accumulated_evidence"].append({"id": "unrelated-evidence", "score": 10, "signal": "Not in context", "metadata": {"answer_id": "unrelated-answer"}})
    w.graph.side_effect = None
    w.graph.return_value = {"context": recovery_context, "answers": deepcopy(w.repo.answers)}
    result = await w.service.generate_report("interview-a")
    assert result.overall_score == 60 and len(result.analysis["evidence"]) == 4
    assert result.analysis["coverage"]["answer_identity_complete"] is True
    assert result.analysis["coverage"]["scored_answer_count"] == 4
    w.graph.assert_called_once()


@pytest.mark.asyncio
async def test_graph_cannot_replace_a_known_context_answer_identity(workflow):
    w = workflow
    recovery_context = deepcopy(w.repo.captured["context"])
    w.repo.captured["context"]["accumulated_evidence"][1]["metadata"] = {}
    recovery_context["accumulated_evidence"][0]["metadata"]["answer_id"] = "conflicting-answer"
    w.graph.side_effect = None
    w.graph.return_value = {"context": recovery_context, "answers": deepcopy(w.repo.answers)}
    with pytest.raises(ValidationError): await w.service.generate_report("interview-a")
    assert (await w.service.status("interview-a")).error_code == "REPORT_SOURCE_INVALID"
    w.nano.assert_not_called(); w.gemini.assert_not_called()


@pytest.mark.asyncio
async def test_complete_score_links_enrich_missing_actual_answer_text_from_exact_graph(workflow):
    w = workflow
    graph_answers = deepcopy(w.repo.answers)
    w.repo.answers = []
    w.graph.side_effect = None
    w.graph.return_value = {"context": {"metadata": {"graph_interview_ids": ["intra-interview-a"]}},
                           "answers": graph_answers + [{"id": "unrelated-answer", "transcript": "DO_NOT_COPY"}]}
    result = await w.service.generate_report("interview-a")
    assert result.overall_score == 60 and len(result.analysis["answers"]) == 4
    assert result.analysis["coverage"]["missing_answer_ids"] == []
    assert result.analysis["provenance"]["graph_interview_ids"] == ["intra-interview-a"]
    assert "DO_NOT_COPY" not in json.dumps(result.model_dump(mode="json"))
    w.graph.assert_called_once()


@pytest.mark.asyncio
async def test_missing_graph_transcripts_leave_honest_coverage_without_changing_existing_scores(workflow):
    w = workflow
    w.repo.answers = []
    result = await w.service.generate_report("interview-a")
    assert result.overall_score == 60 and result.analysis["answers"] == []
    assert len(result.analysis["coverage"]["missing_answer_ids"]) == 4
    assert result.analysis["coverage"]["warnings"]
    w.graph.assert_called_once()


@pytest.mark.asyncio
async def test_optional_graph_enrichment_cannot_overwrite_a_conflicting_existing_transcript(workflow):
    w = workflow
    graph_answers = deepcopy(w.repo.answers)
    w.repo.answers.pop()
    graph_answers[0]["transcript"] = "A conflicting account of the same answer."
    w.graph.side_effect = None
    w.graph.return_value = {"context": {}, "answers": graph_answers}
    with pytest.raises(ValidationError): await w.service.generate_report("interview-a")
    assert (await w.service.status("interview-a")).error_code == "REPORT_SOURCE_INVALID"
    w.nano.assert_not_called(); w.gemini.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["interview_id", "candidate_id"])
async def test_cached_assessment_is_bound_to_the_current_interview_and_candidate(workflow, field):
    w = workflow
    from app.services.report_evaluation import build_evaluation
    saved = build_evaluation(w.repo.interview, w.repo.captured["context"], [], w.repo.answers)
    saved[field] = "another-private-resource"
    w.repo.interview["report_source"] = {"evaluation": saved}
    with pytest.raises(ValidationError): await w.service.generate_report("interview-a")
    assert (await w.service.status("interview-a")).error_code == "REPORT_SOURCE_INVALID"
    assert w.repo.report is None
    w.nano.assert_not_called(); w.gemini.assert_not_called(); w.graph.assert_not_called()


def test_cached_coverage_counters_cannot_turn_one_scored_answer_into_an_overall_assessment():
    assessment = {"coverage": {"scored_answer_count": 12, "answer_identity_complete": True},
                  "evidence": [{"id": f"e-{i}", "score": 7, "answer_id": "same-answer"} for i in range(12)]}
    assert ReportService._overall_coverage(assessment) is False


@pytest.mark.asyncio
async def test_gemini_failure_persists_nano_draft_and_retry_reuses_immutable_source(workflow):
    w = workflow
    w.gemini.side_effect = [AICreditsError("credits_exhausted"), feedback()]
    with pytest.raises(ValidationError):
        await w.service.generate_report("interview-a")
    state = await w.service.status("interview-a")
    assert state.status == "failed" and state.error_code == "AICREDITS_CREDITS_EXHAUSTED"
    assert state.message and "exhausted" in state.message.lower()
    saved_source, saved_draft = deepcopy(w.repo.interview["report_source"]), deepcopy(w.repo.interview["report_draft"])
    assert saved_draft == narrative() and w.repo.report is None
    for item in w.repo.captured["context"]["accumulated_evidence"]: item["score"] = 10
    w.repo.answers = []
    restarted = ReportService(w.repo, Mock())
    result = await restarted.generate_report("interview-a")
    assert result.overall_score == 60 and w.repo.interview["report_source"] == saved_source
    assert w.nano.await_count == 1 and w.gemini.await_count == 2 and w.repo.finishes == 1


@pytest.mark.asyncio
async def test_successful_nano_phase_renews_lease_before_starting_gemini(workflow):
    w = workflow
    async def nano(_assessment):
        w.repo.interview["report_generation"]["started_at"] = "2020-01-01T00:00:00+00:00"
        return narrative()
    async def gemini(_assessment, _draft):
        state = w.repo.interview["report_generation"]
        assert datetime.fromisoformat(state["started_at"]) > datetime.now(timezone.utc) - timedelta(seconds=10)
        assert state["status"] == "generating"
        return feedback()
    w.nano.side_effect, w.gemini.side_effect = nano, gemini
    assert (await w.service.generate_report("interview-a")).overall_score == 60


@pytest.mark.asyncio
async def test_ready_report_replays_identically_without_new_model_or_graph_calls(workflow):
    w = workflow
    first = await w.service.generate_report("interview-a")
    persisted = deepcopy(w.repo.report)
    w.repo.answers = []
    w.repo.captured = {"context": None, "transcripts": []}
    second = await ReportService(w.repo, Mock()).generate_report("interview-a")
    performance = await w.service.candidate_performance("interview-a")
    assert first == second and w.repo.report == persisted
    assert performance.rating == 3.4 and performance.feedback == first.candidate_feedback
    assert w.nano.await_count == w.gemini.await_count == w.repo.finishes == 1
    assert (await w.service.request_report("interview-a")).status == "ready"
    w.graph.assert_not_called()


@pytest.mark.asyncio
async def test_current_generation_conflicts_but_stale_lease_can_retry(workflow):
    w = workflow
    w.repo.interview["report_generation"] = {"status": "generating", "attempt_id": "other",
        "started_at": datetime.now(timezone.utc).isoformat()}
    with pytest.raises(ConflictError): await w.service.generate_report("interview-a")
    w.nano.assert_not_called()
    w.repo.interview["report_generation"]["started_at"] = "2020-01-01T00:00:00+00:00"
    assert (await w.service.status("interview-a")).error_code == "REPORT_GENERATION_INTERRUPTED"
    assert (await w.service.generate_report("interview-a")).overall_score == 60
    assert w.repo.finishes == 1


@pytest.mark.asyncio
async def test_superseded_worker_cannot_publish_or_overwrite_new_attempt_failure_state(workflow):
    w = workflow
    await w.service._claim("interview-a", "old", deepcopy(w.repo.captured))
    w.repo.interview["report_generation"] = {"status": "generating", "attempt_id": "new",
        "started_at": datetime.now(timezone.utc).isoformat()}
    current = deepcopy(w.repo.interview["report_generation"])
    await w.service._generate_claimed("interview-a", "old")
    assert w.repo.interview["report_generation"] == current and w.repo.report is None
    w.nano.assert_not_called(); w.gemini.assert_not_called()


@pytest.mark.asyncio
async def test_background_request_returns_while_generating_and_concurrent_request_does_not_duplicate(workflow):
    w = workflow
    entered, release = Event(), Event()
    async def blocked_narrative(_assessment):
        entered.set()
        assert release.wait(timeout=5), "Test did not release the isolated report worker"
        return narrative()
    w.nano.side_effect = blocked_narrative
    try:
        first, second = await asyncio.gather(w.service.request_report("interview-a"), w.service.request_report("interview-a"))
        assert first.status == second.status == "generating"
        assert await asyncio.to_thread(entered.wait, 2)
        assert (await w.service.status("interview-a")).status == "generating"
        assert (await w.service.candidate_performance("interview-a")).rating is None
        assert w.nano.await_count == 1 and w.gemini.await_count == 0
    finally:
        release.set()
        workers = list(report_service._workers)
        if workers: await asyncio.wait_for(asyncio.gather(*workers), timeout=5)
    assert w.repo.finishes == 1 and (await w.service.status("interview-a")).status == "ready"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["unknown_citation", "missing_citation", "wrong_summary_type", "no_findings"])
async def test_invalid_narrative_cannot_be_published_or_sent_to_candidate_provider(workflow, bad):
    w = workflow
    output = narrative()
    if bad == "unknown_citation": output["strengths"][0]["evidence_ids"] = ["another-interview-evidence"]
    elif bad == "missing_citation": output["strengths"][0]["evidence_ids"] = []
    elif bad == "wrong_summary_type": output["overall_summary"] = {"raw": "private"}
    else: output["strengths"], output["improvements"] = [], []
    w.nano.return_value = output
    with pytest.raises(ValidationError): await w.service.generate_report("interview-a")
    assert (await w.service.status("interview-a")).error_code == "REPORT_OUTPUT_INVALID"
    assert not w.repo.interview.get("report_draft") and not w.repo.report
    w.gemini.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["Short", "First line\nSecond line", "First line\rSecond line", "Your salary expectation needs to be lower.", "The recruiter has rejected your application.", "The private recommendation is strong_hire.", "Your private answer-0 showed good reasoning.", "The finding evidence-1 was particularly clear.", {"not": "a sentence"}])
async def test_invalid_candidate_feedback_keeps_valid_draft_but_never_publishes(workflow, bad):
    w = workflow
    w.gemini.return_value = {**feedback(), "improvement": bad}
    with pytest.raises(ValidationError): await w.service.generate_report("interview-a")
    assert (await w.service.status("interview-a")).error_code == "REPORT_OUTPUT_INVALID"
    assert w.repo.interview["report_draft"] == narrative() and not w.repo.report
    candidate = await w.service.candidate_performance("interview-a")
    assert candidate.status == "failed" and candidate.rating is None and candidate.feedback is None


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_field", ["strengths", "improvements"])
async def test_candidate_feedback_cannot_invent_a_finding_absent_from_validated_narrative(workflow, empty_field):
    w = workflow
    grounded = narrative()
    grounded[empty_field] = []
    w.nano.return_value = grounded
    w.gemini.return_value = {"strength": "You demonstrated a foundational understanding of the technical concepts.",
                            "improvement": "Your communication needed stronger supporting examples."}
    result = await w.service.generate_report("interview-a")
    if empty_field == "strengths":
        assert result.candidate_feedback[1] == "This interview did not provide enough evidence to identify a clear overall strength."
        assert "foundational" not in result.candidate_feedback[1]
    else:
        assert result.candidate_feedback[2] == "Continue supporting your explanations with specific examples and measurable outcomes."
        assert "needed" not in result.candidate_feedback[2]
    assert len(result.candidate_feedback) == 3 and result.overall_score == 60


@pytest.mark.asyncio
async def test_unknown_provider_exception_never_persists_or_logs_raw_secret(workflow, capsys):
    w = workflow
    secret = "diagnostic-fake-secret-do-not-log"
    w.nano.side_effect = RuntimeError(f"upstream failure token={secret}")
    with pytest.raises(ValidationError) as error: await w.service.generate_report("interview-a")
    state = await w.service.status("interview-a")
    assert state.error_code == "REPORT_GENERATION_FAILED"
    assert secret not in json.dumps(w.repo.interview) + str(error.value) + capsys.readouterr().out
    assert w.repo.report is None


@pytest.mark.parametrize("score,rating", [(0, 1), (3.75, 1.2), (6.25, 1.3), (25, 2), (50, 3), (60, 3.4), (75, 4), (100, 5)])
def test_candidate_stars_are_deterministic_from_existing_overall_score(score, rating):
    assert rating_from_score(score) == rating


@pytest.mark.parametrize("score", [True, "75", None, float("nan"), float("inf"), -1, 101])
def test_rating_rejects_non_scores(score):
    with pytest.raises(ValidationError): rating_from_score(score)


@pytest.mark.parametrize("changes", [
    {"candidate_rating": 3}, {"candidate_rating": True}, {"candidate_rating": float("nan")},
    {"candidate_feedback": "scalar"}, {"candidate_feedback": ["a", "b"]},
    {"candidate_feedback": ["a", "b", "\n\t"]}, {"candidate_feedback": ["a", "b", 12]},
    {"analysis": None}, {"analysis": {}}, {"analysis": ["not an object"]},
    {"overall_score": 101}, {"overall_score": True},
])
@pytest.mark.asyncio
async def test_readiness_matches_sql_output_predicate_and_hides_partial_candidate_result(workflow, changes):
    w = workflow
    await w.service.generate_report("interview-a")
    w.repo.report.update(changes)
    assert _ready(w.repo.report) is False
    assert (await w.service.status("interview-a")).status == "failed"
    candidate = await w.service.candidate_performance("interview-a")
    assert candidate.status == "failed" and candidate.rating is None and candidate.feedback is None


def test_completion_snapshot_keeps_round_and_answer_links_but_excludes_nested_private_metadata(monkeypatch):
    from app.interview_context.store import interview_session_store
    from app.sessions.store import session_store
    from app.transcript.store import transcript_store
    _meeting, snapshot, _answers = sources()
    context = snapshot["context"]
    context["metadata"] = {"api_key": "DO_NOT_COPY", "round_configs": [
        {"id": "round-a", "type": "technical", "agent_ids": ["alex", "jordan"], "private_token": "DO_NOT_COPY"}],
        "handoff_history": [{"from_agent_id": "alex", "to_agent_id": "jordan", "status": "completed", "private_token": "DO_NOT_COPY"}]}
    context["accumulated_evidence"][0]["metadata"]["private_token"] = "DO_NOT_COPY"
    context["question_history"] = [{"id": "question-a", "metadata": {"answered_by": "answer-0",
        "round_id": "round-a", "private_token": "DO_NOT_COPY", "assessment_outcome": {
            "evidence_ids": ["evidence-0"], "answer_id": "answer-0", "private_token": "DO_NOT_COPY"}}}]
    before = deepcopy(context)
    monkeypatch.setattr(interview_session_store, "get", lambda _iid: SimpleNamespace(to_dict=lambda: context))
    monkeypatch.setattr(session_store, "get", lambda _iid: None)
    monkeypatch.setattr(transcript_store, "get_transcript", lambda _iid: [])
    result = report_service._capture_source("interview-a")
    assert "DO_NOT_COPY" not in json.dumps(result)
    assert result["context"]["metadata"]["round_configs"][0]["agent_ids"] == ["alex", "jordan"]
    assert result["context"]["question_history"][0]["metadata"]["assessment_outcome"]["evidence_ids"] == ["evidence-0"]
    assert context == before


@pytest.mark.parametrize("kind,canonicalized", [("registered", True), ("canonical", True), ("different_channel", False), ("different_candidate", False), ("missing_meeting", False)])
def test_live_snapshot_normalizes_only_the_proven_session_channel_alias(monkeypatch, kind, canonicalized):
    from app.interview_context.store import interview_session_store
    from app.sessions.store import session_store
    from app.transcript.store import transcript_store
    interview, captured, answers = sources()
    context = captured["context"]
    context["interview_id"] = "interview-a" if kind == "canonical" else "intra-interview-a"
    meeting = SimpleNamespace(interview_id="interview-a", channel_name="intra-interview-a", candidate_id="candidate-a")
    if kind == "different_channel": context["interview_id"] = "intra-other-interview"
    elif kind == "different_candidate": context["candidate_id"] = "other-candidate"
    elif kind == "missing_meeting": meeting = None
    before = deepcopy(context)
    monkeypatch.setattr(interview_session_store, "get", lambda _iid: SimpleNamespace(to_dict=lambda: context))
    monkeypatch.setattr(session_store, "get", lambda _iid: meeting)
    monkeypatch.setattr(transcript_store, "get_transcript", lambda _iid: [])
    result = report_service._capture_source("interview-a")
    from app.services.report_evaluation import ReportSourceInvalid, build_evaluation
    if canonicalized:
        evaluation = build_evaluation(interview, result["context"], [], answers)
        assert evaluation["overall_score"] == 60
        assert result["context"]["interview_id"] == "interview-a"
        assert evaluation["provenance"]["source_interview_id"] == before["interview_id"]
    else:
        with pytest.raises(ReportSourceInvalid): build_evaluation(interview, result["context"], [], answers)
    assert context == before


def ready_http_report(db):
    meeting = next(row for row in db.rows["scheduled_interviews"] if row["id"] == "interview-a")
    meeting["status"] = "completed"
    report = next(row for row in db.rows["reports"] if row["id"] == "report-a")
    report.update({"candidate_rating": 4, "candidate_feedback": ["Your overall performance was good.", feedback()["strength"], feedback()["improvement"]],
        "analysis": {"internal_evidence": "HR_PRIVATE_EVIDENCE", "answers": ["HR_PRIVATE_TRANSCRIPT"]},
        "salary_recommendation": {"min": 100, "max": 200, "justification": "HR_PRIVATE_COMPENSATION"}})
    return report


@pytest.mark.asyncio
async def test_candidate_receives_only_own_minimal_ready_projection_and_no_recruiter_fields(workspace):
    app, db = workspace
    saved = ready_http_report(db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/interviews/interview-a/performance", headers=headers("user-a", "candidate"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rating"] == 4 and body["feedback"] == saved["candidate_feedback"] and body["status"] == "ready"
    assert set(body) == {"interview_id", "status", "rating", "feedback", "created_at", "message"}
    assert "HR_PRIVATE" not in response.text and "recommendation" not in response.text and "overall_score" not in response.text
    assert db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("actor,role,path", [
    ("user-a", "candidate", "/api/v1/reports/report-a"),
    ("user-a", "candidate", "/api/v1/interviews/interview-a/report"),
    ("user-a", "candidate", "/api/v1/interviews/interview-a/report/pdf"),
    ("user-a", "candidate", "/api/v1/reports/report-a/status"),
    ("user-b", "candidate", "/api/v1/interviews/interview-a/performance"),
    ("hr-b", "recruiter", "/api/v1/reports/report-a"),
    ("hr-b", "recruiter", "/api/v1/reports/report-a/status"),
    ("hr-a", "recruiter", "/api/v1/interviews/interview-a/performance"),
])
async def test_report_projections_enforce_persisted_role_and_resource_owner(workspace, actor, role, path):
    app, db = workspace
    ready_http_report(db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path, headers=headers(actor, role))
    assert response.status_code == 403, response.text
    assert "HR_PRIVATE" not in response.text and not db.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("actor,role", [("user-a", "candidate"), ("hr-b", "recruiter")])
async def test_generation_is_denied_before_any_work_for_candidate_or_foreign_recruiter(workspace, actor, role):
    app, db = workspace
    ready_http_report(db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/interviews/interview-a/report/generate", headers=headers(actor, role))
    assert response.status_code == 403 and db.writes == []
