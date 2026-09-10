"""Practice coaching uses actual native history and never official evaluation."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.voice import feedback
from app.voice.models import DashboardContext, utc_now
from tests.test_voice_sessions import browser_headers, voice_env


def history():
    return [
        {"role": "assistant", "content": "What did you build for your class project?"},
        {"role": "user", "content": "I built a course enrolment form using React and PostgreSQL."},
        {"role": "assistant", "content": "How did you validate the enrolment form?"},
        {"role": "user", "content": "I required an email and checked whether the course was already full."},
    ]


def model_feedback():
    return {
        "summary": "Your answers describe a clear project and a concrete validation step.",
        "criteria": [
            {"name": "clarity", "score": 70, "reason": "The project and implementation step were understandable."},
            {"name": "relevance", "score": 80, "reason": "Both answers directly address the questions asked."},
            {"name": "specificity", "score": 60, "reason": "You named the technology and one validation rule."},
        ],
        "strengths": ["You used a concrete class project."],
        "areas_to_improve": ["Explain how you tested the validation rule."],
        "better_answers": [{"answer_index": 1,
                            "example": "I checked email input and course capacity, then [add your actual test].",
                            "explanation": "Connect your validation rule to a test you actually performed."}],
    }


def marked_feedback(data=None, separator="\n"):
    data = data or model_feedback()
    values = {
        "INTRA_SUMMARY": data["summary"], "INTRA_STRENGTH": data["strengths"][0],
        "INTRA_IMPROVEMENT": data["areas_to_improve"][0],
        "INTRA_ANSWER_INDEX": str(data["better_answers"][0]["answer_index"]),
        "INTRA_EXAMPLE": data["better_answers"][0]["example"],
        "INTRA_EXPLANATION": data["better_answers"][0]["explanation"],
    }
    for criterion in data["criteria"]:
        values[f"INTRA_{criterion['name'].upper()}_SCORE"] = str(criterion["score"])
        values[f"INTRA_{criterion['name'].upper()}_REASON"] = criterion["reason"]
    return separator.join(field + (" " + values[field] if field in values else "")
                          for field in feedback.FEEDBACK_FIELDS)


def native_feedback(agora, contents=None):
    """Model acceptance and history are distinct, session-specific stages."""
    contents = contents if contents is not None else history()
    dispatch = {}

    async def request(*args, **kwargs):
        dispatch.update(kwargs)
        return {"status": "FEEDBACK_REQUEST_ACCEPTED"}

    async def get_history(*args):
        rows = deepcopy(contents)
        if dispatch:
            rows.extend([
                {"role": "user", "content": dispatch["text"]},
                {"role": "assistant", "content": marked_feedback()},
            ])
        return {"contents": rows}

    agora.request_practice_feedback = AsyncMock(side_effect=request)
    agora.get_history = AsyncMock(side_effect=get_history)


@pytest.mark.parametrize(("question", "answer"), [
    ("Which role would you like to practice?", "I would like a software developer internship."),
    ("How many years of experience do you have?", "I have two years of college experience."),
    ("How did you validate the form?", "Can you explain the question?"),
])
def test_role_setup_and_clarification_are_not_scored(question, answer):
    assert feedback.exchanges([{"role": "assistant", "content": question},
                               {"role": "user", "content": answer}]) == []


def test_genuine_attempts_include_uncertainty_and_preserve_actual_question():
    contents = history()[:2] + [
        {"role": "assistant", "content": "How did you test the validation rule?"},
        {"role": "user", "content": "I don’t know"},
    ]
    answers = feedback.exchanges(contents)
    assert len(answers) == 2
    assert answers[1] == {"question": contents[2]["content"], "answer": "I don’t know"}


def test_request_budget_samples_across_session_and_keeps_source_indices():
    source = [{"question": f"Question {i} " + ('中文 "\\' * 1000),
               "answer": f"Answer {i} " + ('résumé "\\' * 1000)} for i in range(12)]
    text, reviewed = feedback.feedback_request("synthetic-request", source,
        {"target_role": "Software Intern", "experience_level": "intern"})
    assert len(text.encode("utf-8")) <= 8192
    assert text.startswith(feedback.MARKER + "synthetic-request")
    assert reviewed == [source[i] for i in [0, 2, 4, 6, 8, 11]]
    data = json.loads(text.rsplit("\n", 1)[1])
    assert [item["answer_index"] for item in data["answer_excerpts"]] == list(range(6))
    assert data["practice"]["experience_level"] == "intern"
    assert "[add your actual ...]" in text
    assert "first-person" in text and "Do not add unstated database fields" in text
    assert "complete verbatim sentences" in text
    assert "discussing the same project alone is not enough" in text
    assert all(field in text for field in feedback.FEEDBACK_FIELDS)
    assert feedback.COMPLETION_MARKER not in text
    assert "110 words" in text and "not JSON" in text


def test_score_is_calculated_from_unique_criteria_and_examples_use_canonical_source():
    answers = feedback.exchanges(history())
    result = feedback.parse_feedback(json.dumps(model_feedback()), answers, 9)
    assert result["indicative_score"] == 70
    assert result["answered_questions"] == 9 and result["reviewed_answers"] == 2
    assert result["better_answers"][0]["question"] == answers[1]["question"]
    assert result["better_answers"][0]["answer_excerpt"] == answers[1]["answer"]
    assert "does not affect your application" in result["message"]


def test_source_sentences_and_explicit_prompts_are_retained_with_normalized_case_and_whitespace():
    source = feedback.exchanges(history())
    source[1]["answer"] = "I checked for blank titles. I tried spaces-only input."
    data = model_feedback()
    data["better_answers"][0]["example"] = (
        "I CHECKED  for blank titles. [add your actual reason for this validation] "
        "I tried spaces-only input. [add your actual observed result]"
    )
    result = feedback.parse_feedback(marked_feedback(data), source, 2)
    example = result["better_answers"][0]
    assert example["example_kind"] == "suggested_answer"
    assert example["example"] == data["better_answers"][0]["example"]
    assert example["answer_excerpt"] == source[1]["answer"]


@pytest.mark.parametrize("case", ["invented_date", "other_answer", "negation", "partial_sentence",
                                  "reordered", "placeholder_only", "unrecognized_placeholder"])
def test_ungrounded_rewrite_becomes_source_template_without_discarding_valid_score(case):
    source = feedback.exchanges(history())
    source[1]["answer"] = "I checked for blank titles. I tried spaces-only input."
    examples = {
        "invented_date": "I stored a created date for every task.",
        "other_answer": source[0]["answer"],
        "negation": "I did test invalid titles.",
        "partial_sentence": "implemented the database field validation",
        "reordered": "I tried spaces-only input. I checked for blank titles.",
        "placeholder_only": "[add your actual project and result]",
        "unrecognized_placeholder": "I checked for blank titles. [Add an invented field]",
    }
    if case == "negation":
        source[1]["answer"] = "I did not test invalid titles."
    if case == "partial_sentence":
        source[1]["answer"] = "My partner, not me, implemented the database field validation."
    data = model_feedback()
    data["better_answers"][0]["example"] = examples[case]
    data["better_answers"][0]["explanation"] = "The created date demonstrates traceability."
    result = feedback.parse_feedback(marked_feedback(data), source, 2)
    example = result["better_answers"][0]
    assert result["status"] == "ready" and result["indicative_score"] == 70
    assert example["example_kind"] == "template"
    assert example["example"].startswith(source[1]["answer"])
    assert "[add your actual reason" in example["example"]
    assert "[add your actual result" in example["example"]
    assert "created date" not in example["example"] + example["explanation"]
    assert example["answer_excerpt"] == source[1]["answer"]


def test_fallback_template_bounds_its_excerpt_without_altering_full_source_answer():
    source = feedback.exchanges(history())
    source[1]["answer"] = "I tested the title validation using empty input. " * 100
    result = feedback.parse_feedback(marked_feedback(), source, 2)
    example = result["better_answers"][0]
    assert example["example_kind"] == "template"
    assert len(example["example"]) < 1200
    assert example["answer_excerpt"] == source[1]["answer"]
    assert example["example"].startswith("Excerpt from your answer (see your full answer above):\n")
    copied = example["example"].split("\n", 2)[1]
    assert source[1]["answer"].startswith(copied)
    assert copied.endswith(".")


@pytest.mark.parametrize(("actual", "changed"), [
    ("C++", "C"), ("-5", "5"), ("value == 5", "value = 5"), ("5.0", "50"), ("x != y", "x = y"),
])
def test_technical_symbols_are_not_erased_by_grounding_normalization(actual, changed):
    source = feedback.exchanges(history())
    source[1]["answer"] = f"I used {actual} in the project."
    data = model_feedback()
    data["better_answers"][0]["example"] = f"I used {changed} in the project."
    result = feedback.parse_feedback(marked_feedback(data), source, 2)
    example = result["better_answers"][0]
    assert example["example_kind"] == "template"
    assert example["example"].startswith(source[1]["answer"])
    assert result["indicative_score"] == 70


def test_long_single_sentence_is_explicitly_labeled_excerpt_with_full_qualifier_preserved_separately():
    source = feedback.exchanges(history())
    source[1]["answer"] = "I considered " + "a possible improvement " * 80 + "but I did not implement it."
    result = feedback.parse_feedback(marked_feedback(), source, 2)
    example = result["better_answers"][0]
    assert "Excerpt from your answer (see your full answer above):" in example["example"]
    assert " …\n" in example["example"]
    assert example["answer_excerpt"].endswith("but I did not implement it.")


@pytest.mark.parametrize("separator", ["\n", ""])
def test_complete_marked_feedback_survives_removed_line_boundaries(separator):
    source = feedback.exchanges(history())
    result = feedback.parse_feedback(marked_feedback(separator=separator), source, 2)
    assert result == feedback.parse_feedback(json.dumps(model_feedback()), source, 2)
    assert result["indicative_score"] == 70
    assert result["better_answers"][0]["answer_excerpt"] == source[1]["answer"]


@pytest.mark.parametrize("alteration", ["missing", "duplicate", "out_of_order", "unknown", "prefix", "trailing", "legacy_suffix"])
def test_incomplete_or_ambiguous_marker_structure_is_rejected(alteration):
    text = marked_feedback()
    if alteration == "missing":
        text = text.replace("INTRA_SPECIFICITY_REASON", "")
    elif alteration == "duplicate":
        text = text.replace("INTRA_SUMMARY", "INTRA_SUMMARY INTRA_SUMMARY")
    elif alteration == "out_of_order":
        text = text.replace("INTRA_CLARITY_SCORE", "TEMP").replace("INTRA_RELEVANCE_SCORE", "INTRA_CLARITY_SCORE").replace("TEMP", "INTRA_RELEVANCE_SCORE")
    elif alteration == "unknown":
        text = text.replace("INTRA_EXAMPLE", "INTRA_NEW_FIELD anything INTRA_EXAMPLE")
    elif alteration == "prefix":
        text = "Here is your report. " + text
    elif alteration == "legacy_suffix":
        text += "\n" + feedback.COMPLETION_MARKER
    else:
        text += " Extra narration."
    with pytest.raises(ValueError):
        feedback.parse_feedback(text, feedback.exchanges(history()), 2)


@pytest.mark.parametrize("invalid", ["-1", "101", "70.0", "true", "٧٠", "7e1", "+70"])
def test_marked_scores_are_strict_ascii_integers_in_range(invalid):
    text = marked_feedback().replace("INTRA_CLARITY_SCORE 70", "INTRA_CLARITY_SCORE " + invalid)
    with pytest.raises(ValueError):
        feedback.parse_feedback(text, feedback.exchanges(history()), 2)


def test_marked_values_reuse_schema_bounds_and_canonical_source_validation():
    for field, replacement in [("answer_index", 99), ("example", "tiny"), ("explanation", "x" * 701)]:
        data = model_feedback()
        data["better_answers"][0][field] = replacement
        with pytest.raises(ValueError):
            feedback.parse_feedback(marked_feedback(data), feedback.exchanges(history()), 2)
    for index in ["1.0", "-1", "true", "١"]:
        text = marked_feedback().replace("INTRA_ANSWER_INDEX 1", "INTRA_ANSWER_INDEX " + index)
        with pytest.raises(ValueError):
            feedback.parse_feedback(text, feedback.exchanges(history()), 2)


@pytest.mark.parametrize("separator", ["\n", ""])
def test_exact_completion_suffix_preserves_strict_valid_json_result(separator):
    raw = json.dumps(model_feedback())
    expected = feedback.parse_feedback(raw, feedback.exchanges(history()), 2)
    marked = raw + separator + feedback.COMPLETION_MARKER
    assert feedback.parse_feedback(marked, feedback.exchanges(history()), 2) == expected
    assert feedback.COMPLETION_MARKER not in json.dumps(expected)


@pytest.mark.parametrize("malformed", [
    '{"summary":"A sentence with an unfinished closing quote.',
    '{"summary":"Closed string but missing remaining fields and braces"',
])
def test_completion_marker_never_repairs_incomplete_json(malformed):
    with pytest.raises(ValueError):
        feedback.parse_feedback(malformed + "\n" + feedback.COMPLETION_MARKER,
                                feedback.exchanges(history()), 2)


@pytest.mark.parametrize("suffix", [
    "\nUnwanted narration.",
    "\n" + feedback.COMPLETION_MARKER + " More text.",
    "\n" + feedback.COMPLETION_MARKER.rstrip("."),
    "\n" + feedback.COMPLETION_MARKER.lower(),
])
def test_unrecognized_trailing_text_is_not_discarded(suffix):
    with pytest.raises(ValueError):
        feedback.parse_feedback(json.dumps(model_feedback()) + suffix,
                                feedback.exchanges(history()), 2)


@pytest.mark.parametrize(("key", "value"), [
    ("score", -1), ("score", 101), ("score", True), ("score", "70"),
    ("name", "relevance"), ("reason", "x" * 701),
])
def test_invalid_score_rubric_or_reason_never_produces_feedback(key, value):
    data = model_feedback()
    data["criteria"][0][key] = value
    with pytest.raises(ValueError):
        feedback.parse_feedback(json.dumps(data), feedback.exchanges(history()), 2)


def test_invalid_source_index_and_invented_source_fields_are_rejected():
    for replacement in [{"answer_index": 99}, {"answer_index": True},
                        {"question": "An invented question?"}, {"answer_excerpt": "An invented answer."}]:
        data = model_feedback()
        data["better_answers"][0].update(replacement)
        with pytest.raises(ValueError):
            feedback.parse_feedback(json.dumps(data), feedback.exchanges(history()), 2)
    with pytest.raises(ValueError):
        feedback.parse_feedback(" " * 24001, feedback.exchanges(history()), 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["legacy_json", "marked_text"])
async def test_only_fresh_native_request_history_can_supply_feedback(voice_env, monkeypatch, format):
    env = voice_env
    started = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    session = await env.service.store.get(started["session_id"])
    monkeypatch.setattr(feedback, "uuid4", lambda: "fresh-request")
    monkeypatch.setattr(feedback.asyncio, "sleep", AsyncMock())
    stale = model_feedback()
    stale["summary"] = "STALE output must never be returned as feedback."
    old_output = {"role": "assistant", "content": json.dumps(stale)}
    env.agora.request_practice_feedback = AsyncMock(return_value={"status": "FEEDBACK_REQUEST_ACCEPTED"})
    env.agora.get_history = AsyncMock(side_effect=[
        {"contents": history()},
        {"contents": history() + [old_output]},
        {"contents": history() + [old_output,
            {"role": "user", "content": feedback.MARKER + "fresh-request"},
            {"role": "assistant", "content": '{"summary":'},
            {"role": "assistant", "content": marked_feedback() if format == "marked_text" else
             json.dumps(model_feedback()) + "\n" + feedback.COMPLETION_MARKER}]},
    ])
    result = await feedback.generate_feedback(env.agora, session)
    assert result["summary"] == model_feedback()["summary"]
    assert env.agora.get_history.await_count == 3
    dispatch = env.agora.request_practice_feedback.call_args
    assert dispatch.args == ("taylor", session.channel_name, session.cloud_agent_id)
    assert dispatch.kwargs["request_id"] == "fresh-request"
    assert dispatch.kwargs["text"].startswith(feedback.MARKER + "fresh-request")
    assert env.agora.request_practice_feedback.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("answer_count", [0, 1])
async def test_insufficient_answers_end_practice_without_model_request_or_score(voice_env, answer_count):
    env = voice_env
    native_feedback(env.agora, history()[:answer_count * 2])
    start = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    result = await env.service.finish_practice(start["session_id"], {"sub": "user-a"})
    assert result["status"] == "insufficient_evidence" and result["indicative_score"] is None
    assert result["answered_questions"] == answer_count
    env.agora.request_practice_feedback.assert_not_awaited()
    env.agora.stop_agent.assert_awaited_once()
    assert not await env.service.store.active_ids()
    assert env.db.writes == []


@pytest.mark.asyncio
async def test_finish_is_idempotent_and_get_returns_saved_result_without_official_mutations(voice_env, monkeypatch):
    from app.interview_context.store import interview_session_store
    monkeypatch.setattr(interview_session_store, "get_or_create", MagicMock(side_effect=AssertionError("No official store")))
    env = voice_env
    native_feedback(env.agora)
    # This fake materializes absent tables on read; include the new read-only profile table.
    env.db.rows.setdefault("candidate_profiles", [])
    original_rows = deepcopy(env.db.rows)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://test") as client:
        start = await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(), json={})
        url = f"/api/v1/voice/sessions/{start.json()['session_id']}/feedback"
        responses = await asyncio.gather(*[client.post(url, headers=browser_headers()) for _ in range(2)])
        assert all(response.status_code == 200 for response in responses)
        assert all(response.json()["status"] in {"ready", "requesting_feedback"} for response in responses)
        completed = next(response.json() for response in responses if response.json()["status"] == "ready")
        saved = await client.get(url, headers=browser_headers())
        assert saved.json() == completed
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_awaited_once()
    assert not await env.service.store.active_ids()
    assert env.db.rows == original_rows and env.db.writes == []


@pytest.mark.asyncio
async def test_retry_returns_pending_promptly_while_first_finish_holds_lock(voice_env):
    env = voice_env
    native_feedback(env.agora)
    accepted, release = asyncio.Event(), asyncio.Event()
    original_request = env.agora.request_practice_feedback.side_effect

    async def slow_request(*args, **kwargs):
        accepted.set()
        await release.wait()
        return await original_request(*args, **kwargs)

    env.agora.request_practice_feedback.side_effect = slow_request
    start = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    sid = start["session_id"]
    initial = asyncio.create_task(env.service.finish_practice(sid, {"sub": "user-a"}))
    try:
        await asyncio.wait_for(accepted.wait(), timeout=1)
        retry = await asyncio.wait_for(env.service.finish_practice(sid, {"sub": "user-a"}), timeout=0.1)
        assert retry["status"] == "requesting_feedback" and retry["indicative_score"] is None
        current = await env.service.store.get(sid)
        assert 60 < (current.feedback_deadline_at - utc_now()).total_seconds() <= 65
        assert "feedback_deadline_at" not in current.public()
        assert not initial.done()
    finally:
        release.set()
        completed = await initial
    assert completed["status"] == "ready"
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("recovery", ["get", "post", "reaper"])
async def test_restarted_worker_recovers_overdue_pending_without_model_retry(voice_env, recovery):
    from app.voice.service import VoiceAssistantService
    env = voice_env
    native_feedback(env.agora)
    start = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    sid = start["session_id"]
    interrupted = await env.service.store.get(sid)
    interrupted.status = "EXECUTING"
    interrupted.practice_feedback = feedback.outcome("requesting_feedback", "Preparing feedback.")
    interrupted.feedback_deadline_at = utc_now() - timedelta(seconds=1)
    interrupted.heartbeat_at = utc_now()  # Browser heartbeats cannot extend feedback's deadline.
    await env.service.store.put(interrupted)
    restarted = VoiceAssistantService(env.db, env.redis, agora=env.agora)
    if recovery == "reaper":
        await restarted.expire_sessions()
    else:
        reader = restarted.practice_feedback if recovery == "get" else restarted.finish_practice
        await reader(sid, {"sub": "user-a"})
    result = await restarted.practice_feedback(sid, {"sub": "user-a"})
    assert result["status"] == "unavailable" and result["indicative_score"] is None
    stored = await restarted.store.get(sid)
    assert stored.status == "DISCONNECTED" and stored.feedback_deadline_at is None
    env.agora.request_practice_feedback.assert_not_awaited()
    env.agora.get_history.assert_not_awaited()
    env.agora.stop_agent.assert_awaited_once()
    assert not await restarted.store.active_ids()
    assert env.db.writes == []


@pytest.mark.asyncio
async def test_legacy_pending_and_cleanup_failure_recover_without_losing_retry(voice_env):
    env = voice_env
    native_feedback(env.agora)
    start = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    sid = start["session_id"]
    interrupted = await env.service.store.get(sid)
    interrupted.status = "EXECUTING"
    interrupted.practice_feedback = feedback.outcome("requesting_feedback", "Preparing feedback.")
    interrupted.feedback_deadline_at = None  # Persisted by the previous implementation.
    await env.service.store.put(interrupted)
    env.agora.stop_agent.side_effect = RuntimeError("Synthetic cleanup outage")
    result = await env.service.practice_feedback(sid, {"sub": "user-a"})
    assert result["status"] == "unavailable"
    stored = await env.service.store.get(sid)
    assert stored.status == "ERROR" and stored.error_code == "VOICE_CLEANUP_PENDING"
    assert sid in await env.service.store.active_ids()
    env.agora.stop_agent.side_effect = None
    await env.service.expire_sessions()
    assert not await env.service.store.active_ids()
    env.agora.request_practice_feedback.assert_not_awaited()
    env.agora.get_history.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "post"])
async def test_feedback_requires_owner_and_rejects_morgan(voice_env, method):
    env = voice_env
    native_feedback(env.agora)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://test") as client:
        taylor = await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(), json={})
        url = f"/api/v1/voice/sessions/{taylor.json()['session_id']}/feedback"
        for headers, status in [({}, 401), (browser_headers("user-b"), 403), (browser_headers("recruiter-a"), 403)]:
            result = await getattr(client, method)(url, headers=headers)
            assert result.status_code == status
        morgan = await client.post("/api/v1/voice/morgan/sessions", headers=browser_headers("recruiter-a"), json={})
        result = await getattr(client, method)(f"/api/v1/voice/sessions/{morgan.json()['session_id']}/feedback",
                                              headers=browser_headers("recruiter-a"))
        assert result.status_code == 403
    env.agora.get_history.assert_not_awaited()
    env.agora.request_practice_feedback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TimeoutError(), RuntimeError("private-provider-details")])
async def test_native_failure_cleans_up_and_idempotent_retry_never_invents_score(voice_env, failure):
    env = voice_env
    native_feedback(env.agora)
    env.agora.request_practice_feedback.side_effect = failure
    start = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    result = await env.service.finish_practice(start["session_id"], {"sub": "user-a"})
    retry = await env.service.finish_practice(start["session_id"], {"sub": "user-a"})
    assert result == retry and result["status"] == "unavailable"
    assert result["indicative_score"] is None and "private-provider" not in json.dumps(result)
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_awaited_once()
    assert not await env.service.store.active_ids()


@pytest.mark.asyncio
async def test_accepted_request_without_fresh_output_times_out_and_cleans_up(voice_env, monkeypatch):
    from app.voice import service as service_module
    env = voice_env
    env.agora.get_history = AsyncMock(return_value={"contents": history()})
    env.agora.request_practice_feedback = AsyncMock(return_value={"status": "FEEDBACK_REQUEST_ACCEPTED"})

    async def short_deadline(awaitable, *, timeout):
        assert timeout == 35
        return await asyncio.wait_for(awaitable, timeout=0.01)

    # Exercise the actual deadline/cancellation path without waiting 35 seconds
    # or modifying the global asyncio module shared by pytest and HTTP clients.
    monkeypatch.setattr(service_module, "asyncio", SimpleNamespace(
        wait_for=short_deadline, shield=asyncio.shield, CancelledError=asyncio.CancelledError))
    start = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    result = await env.service.finish_practice(start["session_id"], {"sub": "user-a"})
    assert result["status"] == "unavailable" and result["indicative_score"] is None
    assert env.agora.get_history.await_count >= 2
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_awaited_once()
    assert not await env.service.store.active_ids()


@pytest.mark.asyncio
async def test_cancelled_request_stays_recoverable_then_expires_without_replay(voice_env):
    env = voice_env
    native_feedback(env.agora)
    env.agora.request_practice_feedback.side_effect = asyncio.CancelledError()
    start = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    with pytest.raises(asyncio.CancelledError):
        await env.service.finish_practice(start["session_id"], {"sub": "user-a"})
    saved = await env.service.practice_feedback(start["session_id"], {"sub": "user-a"})
    assert saved["status"] == "requesting_feedback" and saved["indicative_score"] is None
    env.agora.stop_agent.assert_not_awaited()
    interrupted = await env.service.store.get(start["session_id"])
    assert interrupted.feedback_checkpoint is not None
    interrupted.feedback_deadline_at = utc_now() - timedelta(seconds=1)
    await env.service.store.put(interrupted)
    saved = await env.service.practice_feedback(start["session_id"], {"sub": "user-a"})
    assert saved["status"] == "unavailable" and saved["indicative_score"] is None
    assert "interrupted" in saved["message"] and "Start a new practice session" in saved["message"]
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_awaited_once()
    assert not await env.service.store.active_ids()


async def cancelled_after_acceptance(env):
    """Dispatch succeeded, but its HTTP worker vanished before reading output."""
    native_feedback(env.agora)
    accepted = env.agora.request_practice_feedback.side_effect

    async def cancel(*args, **kwargs):
        await accepted(*args, **kwargs)
        raise asyncio.CancelledError()

    env.agora.request_practice_feedback.side_effect = cancel
    started = await env.service.start("taylor", {"sub": "user-a"}, DashboardContext())
    with pytest.raises(asyncio.CancelledError):
        await env.service.finish_practice(started["session_id"], {"sub": "user-a"})
    return started["session_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["get", "post", "reaper"])
async def test_restarted_worker_recovers_same_native_output_before_deadline(voice_env, reader):
    from app.voice.service import VoiceAssistantService
    env = voice_env
    sid = await cancelled_after_acceptance(env)
    saved = await env.service.store.get(sid)
    assert saved.feedback_checkpoint["reviewed_answers"] == feedback.exchanges(history())
    assert saved.feedback_checkpoint["request_id"] == saved.feedback_attempt_id
    assert saved.feedback_deadline_at > utc_now()
    for private in ["feedback_checkpoint", "feedback_attempt_id", "feedback_deadline_at"]:
        assert private not in saved.public()
    restarted = VoiceAssistantService(env.db, env.redis, agora=env.agora)
    if reader == "reaper":
        await restarted.expire_sessions()
    else:
        method = restarted.practice_feedback if reader == "get" else restarted.finish_practice
        await method(sid, {"sub": "user-a"})
    result = await restarted.practice_feedback(sid, {"sub": "user-a"})
    assert result["status"] == "ready" and result["indicative_score"] == 70
    assert result["better_answers"][0]["answer_excerpt"] == history()[3]["content"]
    terminal = await restarted.store.get(sid)
    assert terminal.status == "DISCONNECTED"
    assert terminal.feedback_checkpoint is None and terminal.feedback_deadline_at is None
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_awaited_once()
    assert not await restarted.store.active_ids() and env.db.writes == []


@pytest.mark.asyncio
async def test_checkpoint_is_saved_before_native_dispatch_and_preserves_full_sources(voice_env):
    env = voice_env
    rows = history()
    rows[1]["content"] += " I did not test concurrent submissions." * 30
    native_feedback(env.agora, rows)
    accepted = env.agora.request_practice_feedback.side_effect
    sid = (await env.service.start("taylor", {"sub": "user-a"}, DashboardContext()))["session_id"]

    async def inspect_checkpoint(*args, **kwargs):
        stored = await env.service.store.get(sid)
        assert stored.feedback_checkpoint["request_id"] == kwargs["request_id"]
        assert stored.feedback_checkpoint["reviewed_answers"] == feedback.exchanges(rows)
        return await accepted(*args, **kwargs)

    env.agora.request_practice_feedback.side_effect = inspect_checkpoint
    result = await env.service.finish_practice(sid, {"sub": "user-a"})
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_simultaneous_poll_and_original_worker_finalize_once(voice_env):
    env = voice_env
    native_feedback(env.agora)
    accepted = env.agora.request_practice_feedback.side_effect
    available, release = asyncio.Event(), asyncio.Event()

    async def delay_acceptance_response(*args, **kwargs):
        await accepted(*args, **kwargs)
        available.set()
        await release.wait()

    env.agora.request_practice_feedback.side_effect = delay_acceptance_response
    sid = (await env.service.start("taylor", {"sub": "user-a"}, DashboardContext()))["session_id"]
    worker = asyncio.create_task(env.service.finish_practice(sid, {"sub": "user-a"}))
    try:
        await asyncio.wait_for(available.wait(), timeout=1)
        results = await asyncio.wait_for(asyncio.gather(
            env.service.practice_feedback(sid, {"sub": "user-a"}),
            env.service.finish_practice(sid, {"sub": "user-a"})), timeout=1)
        assert results[0] == results[1] and results[0]["status"] == "ready"
        assert not worker.done()
        # The old worker subsequently fails to read its now-stopped agent.
        env.agora.get_history.side_effect = RuntimeError("agent already stopped")
    finally:
        release.set()
        final = await worker
    assert final == results[0]
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["attempt", "agent", "ended"])
async def test_late_native_worker_cannot_finalize_changed_session(voice_env, replacement):
    env = voice_env
    native_feedback(env.agora)
    accepted = env.agora.request_practice_feedback.side_effect
    waiting, release = asyncio.Event(), asyncio.Event()

    async def hold_response(*args, **kwargs):
        await accepted(*args, **kwargs)
        waiting.set()
        await release.wait()

    env.agora.request_practice_feedback.side_effect = hold_response
    sid = (await env.service.start("taylor", {"sub": "user-a"}, DashboardContext()))["session_id"]
    worker = asyncio.create_task(env.service.finish_practice(sid, {"sub": "user-a"}))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=1)
        current = await env.service.store.get(sid)
        if replacement == "attempt":
            current.feedback_attempt_id = "different-attempt"
        elif replacement == "agent":
            current.cloud_agent_id = "different-agent"
        else:
            current.status = "DISCONNECTED"
            current.practice_feedback = feedback.outcome("unavailable", "Explicitly ended")
        await env.service.store.put(current)
    finally:
        release.set()
        await worker
    stored = await env.service.store.get(sid)
    assert stored.practice_feedback == current.practice_feedback
    env.agora.stop_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_rechecks_account_access_after_provider_read(voice_env):
    from app.core.exceptions import UnauthorizedError
    env = voice_env
    sid = await cancelled_after_acceptance(env)
    read = env.agora.get_history.side_effect

    async def revoke_during_read(*args):
        data = await read(*args)
        next(user for user in env.db.rows["users"] if user["id"] == "user-a")["is_active"] = False
        return data

    env.agora.get_history.side_effect = revoke_during_read
    with pytest.raises(UnauthorizedError):
        await env.service.practice_feedback(sid, {"sub": "user-a"})
    stored = await env.service.store.get(sid)
    assert stored.practice_feedback["status"] == "requesting_feedback"
    env.agora.stop_agent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ["stale", "partial", "wrong_attempt"])
async def test_restarted_reader_rejects_unrelated_or_incomplete_history(voice_env, response):
    env = voice_env
    sid = await cancelled_after_acceptance(env)
    stored = await env.service.store.get(sid)
    prefix = [] if response == "stale" else [{"role": "user", "content": feedback.MARKER +
        ("some-other-attempt" if response == "wrong_attempt" else stored.feedback_attempt_id)}]
    text = "INTRA_FEEDBACK_BEGIN INTRA_SUMMARY Partial" if response == "partial" else marked_feedback()
    env.agora.get_history.side_effect = None
    env.agora.get_history.return_value = {"contents": history() + prefix + [{"role": "assistant", "content": text}]}
    result = await env.service.practice_feedback(sid, {"sub": "user-a"})
    assert result["status"] == "requesting_feedback" and result["indicative_score"] is None
    stored.feedback_deadline_at = utc_now() - timedelta(seconds=1)
    await env.service.store.put(stored)
    result = await env.service.practice_feedback(sid, {"sub": "user-a"})
    assert result["status"] == "unavailable" and result["indicative_score"] is None
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovered_result_is_saved_even_when_cleanup_fails(voice_env):
    env = voice_env
    sid = await cancelled_after_acceptance(env)
    env.agora.stop_agent.side_effect = RuntimeError("Synthetic cleanup outage")
    result = await env.service.practice_feedback(sid, {"sub": "user-a"})
    assert result["status"] == "ready"
    stored = await env.service.store.get(sid)
    assert stored.practice_feedback == result and stored.status == "ERROR"
    assert stored.error_code == "VOICE_CLEANUP_PENDING"
    env.agora.stop_agent.side_effect = None
    await env.service.expire_sessions()
    assert await env.service.practice_feedback(sid, {"sub": "user-a"}) == result
    assert not await env.service.store.active_ids()
    env.agora.request_practice_feedback.assert_awaited_once()


@pytest.mark.parametrize("next_user", [feedback.MARKER + "other-request", "Please ask another question."])
def test_later_turn_output_cannot_complete_saved_feedback_request(next_user):
    checkpoint = {"request_id": "saved-request", "reviewed_answers": feedback.exchanges(history()),
                  "answered_questions": 2}
    rows = history() + [
        {"role": "user", "content": feedback.MARKER + "saved-request"},
        {"role": "assistant", "content": "INTRA_FEEDBACK_BEGIN INTRA_SUMMARY Incomplete"},
        {"role": "user", "content": next_user},
        {"role": "assistant", "content": marked_feedback()},
    ]
    assert feedback.feedback_from_history({"contents": rows}, checkpoint) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["feedback_attempt_id", "cloud_agent_id"])
async def test_reaper_rechecks_attempt_and_agent_after_recovery_read(voice_env, field):
    env = voice_env
    sid = await cancelled_after_acceptance(env)
    read = env.agora.get_history.side_effect

    async def replace_during_read(*args):
        result = await read(*args)
        current = await env.service.store.get(sid)
        setattr(current, field, "replacement")
        await env.service.store.put(current)
        return result

    env.agora.get_history.side_effect = replace_during_read
    await env.service.expire_sessions()
    current = await env.service.store.get(sid)
    assert current.practice_feedback["status"] == "requesting_feedback"
    assert current.status == "EXECUTING" and getattr(current, field) == "replacement"
    env.agora.stop_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_timeout_keeps_recovery_pending_without_dispatching(voice_env):
    env = voice_env
    sid = await cancelled_after_acceptance(env)
    env.agora.get_history.side_effect = TimeoutError("synthetic read timeout")
    result = await env.service.practice_feedback(sid, {"sub": "user-a"})
    assert result["status"] == "requesting_feedback" and result["indicative_score"] is None
    assert "synthetic" not in json.dumps(result)
    env.agora.request_practice_feedback.assert_awaited_once()
    env.agora.stop_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_worker_returns_committed_result_during_slow_cleanup(voice_env):
    env = voice_env
    sid = await cancelled_after_acceptance(env)
    original = await env.service.store.get(sid)
    cleaning, release = asyncio.Event(), asyncio.Event()

    async def slow_cleanup(*_args):
        cleaning.set()
        await release.wait()

    env.agora.stop_agent.side_effect = slow_cleanup
    reader = asyncio.create_task(env.service.practice_feedback(sid, {"sub": "user-a"}))
    try:
        await asyncio.wait_for(cleaning.wait(), timeout=1)
        late = await asyncio.wait_for(env.service._finish_feedback(
            sid, original.feedback_attempt_id, feedback.outcome("unavailable", "late worker failure"),
            "practice_finished", agent_id=original.cloud_agent_id), timeout=0.1)
        assert late["status"] == "ready" and not reader.done()
    finally:
        release.set()
        completed = await reader
    assert late == completed
    env.agora.stop_agent.assert_awaited_once()
