"""Same-room voice lifecycle, generation safety, and context continuity."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.agents.models import NextAction
from app.core.exceptions import ValidationError
from app.interview_context.models import QuestionHistoryItem
from app.interview_context.store import InterviewSessionStore
from app.models.enums import ActionType, DifficultyLevel
from app.sessions.models import InterviewConfiguration, SessionStatus
from app.sessions.response_lifecycle import completed_response, finish_response
from app.sessions.service import InterviewSessionService
from app.sessions.store import SessionStore


@pytest.fixture
def meeting(monkeypatch):
    contexts = InterviewSessionStore()
    monkeypatch.setattr("app.interview_context.store.interview_session_store", contexts)
    service = InterviewSessionService(store=SessionStore())
    session = service.create_session(InterviewConfiguration(
        interview_id="handoff-test", candidate_id="candidate-1", agent_ids=["alex", "jordan"],
        metadata={"job_id": "payments", "job_description": "Build reliable payment systems",
                  "candidate_profile": {"skills": ["Kafka", "PostgreSQL"]}},
    ))
    session.status = SessionStatus.IN_PROGRESS
    session.started_agents = {"alex": "cloud-alex-1"}
    context = contexts.get_or_create(
        session.channel_name, candidate_id=session.candidate_id, agent_id="alex", metadata=session.metadata,
    )
    context.add_evidence({"competency": "architecture", "signal": "Explained Kafka with PostgreSQL",
                          "source_agent_id": "alex", "score": 8})
    context.add_question_history(QuestionHistoryItem(
        agent_id="alex", competency="architecture", question_text="Describe your payment system.",
        difficulty=DifficultyLevel.MEDIUM,
    ))
    context.open_questions = ["How do retries avoid double charging?"]
    context.metadata["candidate_memory"] = {"prior_evidence": "Maintained a payment service"}
    calls = []

    async def stop(**kwargs):
        calls.append(("stop", kwargs))
        await asyncio.sleep(0)
        return {"status": "stopped"}

    async def start(**kwargs):
        calls.append(("start", kwargs))
        await asyncio.sleep(0)
        return {"status": "started", "agora_agent_id": f"cloud-{kwargs['agent_id']}-{len(calls)}"}

    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.stop_interview_agent", AsyncMock(side_effect=stop))
    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.start_interview_agent", AsyncMock(side_effect=start))
    return service, session, context, contexts, calls


@pytest.mark.asyncio
async def test_alex_jordan_alex_same_room_preserves_context(meeting):
    service, session, context, contexts, calls = meeting
    before = context.model_dump(exclude={"current_agent_id"})
    for index, target in enumerate(("jordan", "alex")):
        result = await service.handoff_agent(
            session.channel_name, target, greeting_text="Earlier you mentioned Kafka. How do you handle retries?",
        )
        assert result["status"] == "switched"
        assert session.current_agent_id == context.current_agent_id == target
        assert list(session.started_agents) == [target]
        after = context.model_dump(exclude={"current_agent_id"})
        recorded = after["metadata"].pop("handoff_history")
        assert after == before
        assert len(recorded) == index + 1
        assert recorded == session.metadata["handoff_history"]
        assert recorded[-1]["from_agent_id"] == ("alex" if index == 0 else "jordan")
        assert recorded[-1]["to_agent_id"] == target
        assert recorded[-1]["round_id"] == context.current_round_id
        assert recorded[-1]["status"] == "completed"
        assert datetime.fromisoformat(recorded[-1]["timestamp"]).tzinfo is not None
        assert contexts.get(session.channel_name) is context
    assert [call[0] for call in calls] == ["stop", "start", "stop", "start"]
    assert {call[1]["interview_id"] for call in calls} == {session.channel_name}
    assert calls[1][1]["greeting_text"].startswith("Earlier you mentioned Kafka")


@pytest.mark.asyncio
async def test_jordan_complete_stops_voice_and_retains_evidence(meeting):
    service, session, context, _, calls = meeting
    await service.handoff_agent(session.channel_name, "jordan")
    result = await service.stop_session(session.channel_name)
    assert session.status == SessionStatus.COMPLETED
    assert result["stopped_agents"] == ["jordan"]
    assert not session.started_agents
    assert context.metadata["completed"] is True
    assert context.accumulated_evidence[0].signal == "Explained Kafka with PostgreSQL"
    assert calls[-1][1]["agent_id"] == "jordan"
    with pytest.raises(ValidationError, match="active interview"):
        await service.handoff_agent(session.channel_name, "alex")


@pytest.mark.asyncio
async def test_failed_leave_does_not_start_target_or_change_context(meeting, monkeypatch):
    service, session, context, _, calls = meeting
    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.stop_interview_agent",
                        AsyncMock(return_value={"status": "error", "error": "HTTP 503"}))
    with pytest.raises(ValidationError, match="503"):
        await service.handoff_agent(session.channel_name, "jordan")
    assert not calls
    assert context.current_agent_id == session.current_agent_id == "alex"
    assert session.started_agents == {"alex": "cloud-alex-1"}
    with pytest.raises(ValidationError, match="stop interview audio"):
        await service.stop_session(session.channel_name)
    assert session.status == SessionStatus.IN_PROGRESS
    assert not session.metadata.get("handoff_history") and not context.metadata.get("handoff_history")


@pytest.mark.asyncio
async def test_failed_target_start_leaves_retryable_meeting(meeting, monkeypatch):
    service, session, context, _, calls = meeting
    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.start_interview_agent",
                        AsyncMock(return_value={"status": "error", "error": "unavailable"}))
    with pytest.raises(ValidationError, match="unavailable"):
        await service.handoff_agent(session.channel_name, "jordan")
    assert [call[0] for call in calls] == ["stop"]
    assert session.status == SessionStatus.READY
    assert not session.started_agents
    assert context.current_agent_id == session.current_agent_id == "alex"
    assert not session.metadata.get("handoff_history") and not context.metadata.get("handoff_history")


@pytest.mark.asyncio
async def test_alias_and_id_share_lifecycle_lock(meeting):
    service, session, context, _, calls = meeting
    assert service._store.get_lock(session.channel_name) is service._store.get_lock(session.interview_id)
    await asyncio.gather(
        service.handoff_agent(session.interview_id, "jordan"),
        service.handoff_agent(session.channel_name, "jordan"),
    )
    assert [call[0] for call in calls] == ["stop", "start"]
    assert len(session.metadata["handoff_history"]) == len(context.metadata["handoff_history"]) == 1
    assert (await service.handoff_agent(session.interview_id, "jordan"))["status"] == "unchanged"
    assert len(session.metadata["handoff_history"]) == len(context.metadata["handoff_history"]) == 1


@pytest.mark.asyncio
async def test_stale_generation_cannot_stop_replacement(meeting):
    service, session, context, _, calls = meeting
    assert (await service.stop_session(session.channel_name, expected_agora_agent_id="obsolete"))["status"] == "stale"
    assert (await service.handoff_agent(session.channel_name, "jordan", expected_agora_agent_id="obsolete"))["status"] == "stale"
    assert not calls
    assert not session.metadata.get("handoff_history") and not context.metadata.get("handoff_history")


@pytest.mark.asyncio
async def test_registry_driven_third_agent_handoff(meeting, monkeypatch):
    from app.agents.registry import AgentRegistry
    service, session, context, _, _ = meeting
    registry = AgentRegistry()
    profile = registry.get_profile("jordan").model_copy(update={"agent_id": "morgan", "display_name": "Morgan"})
    registry.register(profile, registry.get_agora_mapping("jordan"))
    monkeypatch.setattr("app.agents.registry.agent_registry", registry)
    monkeypatch.setattr("app.interview_context.models.agent_registry", registry)
    session.agent_ids.append("morgan")
    await service.handoff_agent(session.channel_name, "morgan")
    assert session.current_agent_id == context.current_agent_id == "morgan"


def history(text="Thank you for your time.", start=1010, end=2000, **metadata):
    return {"agent_id": "cloud-alex-1", "channel": "intra-handoff-test", "contents": [
        {"role": "assistant", "content": text, "speech_start_ms": start,
         "speech_end_ms": end, "turn_id": 4, "metadata": metadata},
    ]}


@pytest.mark.parametrize("payload", [
    history(start=1, end=100), history(end=None), history(text="A different response"), history(interrupted=True),
])
def test_text_or_earlier_audio_is_not_completed_current_response(payload):
    assert completed_response(payload, response_text="Thank you for your time.", response_started_at_ms=1000) is None


@pytest.mark.asyncio
async def test_lifecycle_waits_for_current_speech_end_before_handoff(meeting):
    service, session, context, contexts, calls = meeting
    observed_calls = []

    async def get_history(_):
        observed_calls.append(list(calls))
        return history(end=None) if len(observed_calls) == 1 else history()

    agora = type("Agora", (), {})()
    agora.get_agent_history = AsyncMock(side_effect=get_history)
    context.metadata["pending_voice_action"] = "SWITCH_AGENT"
    result = await finish_response(
        session.channel_name, NextAction(action=ActionType.SWITCH_AGENT, target_agent_id="jordan"),
        "Thank you for your time.", response_started_at_ms=1000,
        expected_agent_id="alex", expected_agora_agent_id="cloud-alex-1", greeting_text="Earlier you mentioned Kafka.",
        poll_interval_seconds=0, session_service=service, agora_service=agora, context_store=contexts,
    )
    assert result["status"] == "applied"
    assert observed_calls == [[], []]
    assert [call[0] for call in calls] == ["stop", "start"]
    assert context.current_agent_id == "jordan"
    assert "pending_voice_action" not in context.metadata


@pytest.mark.asyncio
async def test_audio_timeout_and_wrong_channel_never_stop_voice(meeting):
    service, session, context, contexts, calls = meeting
    agora = type("Agora", (), {})()
    agora.get_agent_history = AsyncMock(return_value=history(end=None))
    kwargs = dict(response_started_at_ms=1000, expected_agent_id="alex", expected_agora_agent_id="cloud-alex-1",
                  timeout_seconds=0.001, poll_interval_seconds=0, session_service=service,
                  agora_service=agora, context_store=contexts)
    action = NextAction(action=ActionType.SWITCH_AGENT, target_agent_id="jordan")
    assert (await finish_response(session.channel_name, action, "Thank you for your time.", **kwargs))["status"] == "audio_confirmation_timeout"
    agora.get_agent_history.return_value = {**history(), "channel": "another-candidate"}
    kwargs["timeout_seconds"] = 1
    assert (await finish_response(session.channel_name, action, "Thank you for your time.", **kwargs))["status"] == "history_identity_mismatch"
    assert not calls


@pytest.mark.asyncio
async def test_lifecycle_complete_after_audio(meeting):
    service, session, context, contexts, calls = meeting
    agora = type("Agora", (), {})()
    agora.get_agent_history = AsyncMock(return_value=history())
    result = await finish_response(
        session.channel_name, NextAction(action=ActionType.COMPLETE), "Thank you for your time.",
        response_started_at_ms=1000, expected_agent_id="alex", expected_agora_agent_id="cloud-alex-1",
        session_service=service, agora_service=agora, context_store=contexts,
    )
    assert result["status"] == "applied"
    assert session.status == SessionStatus.COMPLETED
    assert len(calls) == 1 and calls[0][0] == "stop"


@pytest.mark.asyncio
async def test_end_request_supersedes_pending_handoff_without_clearing_it(meeting):
    service, session, context, contexts, calls = meeting
    context.metadata.update(pending_voice_action="COMPLETE", pending_voice_request_id="new-end", completed=True)
    agora = type("Agora", (), {})()
    agora.get_agent_history = AsyncMock(return_value=history())
    result = await finish_response(
        session.channel_name, NextAction(action=ActionType.SWITCH_AGENT, target_agent_id="jordan"),
        "Thank you for your time.", response_started_at_ms=1000,
        expected_agent_id="alex", expected_agora_agent_id="cloud-alex-1", request_id="old-switch",
        session_service=service, agora_service=agora, context_store=contexts,
    )
    assert result["status"] == "stale"
    assert context.metadata["pending_voice_action"] == "COMPLETE"
    assert context.metadata["pending_voice_request_id"] == "new-end"
    assert not calls
    assert (await service.handoff_agent(
        session.channel_name, "jordan", expected_voice_request_id="old-switch",
    ))["status"] == "stale"


@pytest.mark.asyncio
async def test_initial_context_is_hydrated_before_cloud_callback(meeting, monkeypatch):
    _, _, _, contexts, _ = meeting
    from app.core.config import settings
    monkeypatch.setattr(settings, "AGORA_APP_ID", "test_app_id")
    monkeypatch.setattr(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012")
    service = InterviewSessionService(store=SessionStore())
    session = service.create_session(InterviewConfiguration(
        interview_id="initial-grounding", candidate_id="candidate-real", agent_ids=["alex", "jordan"],
        job_title="Payments Engineer", company="Example",
        metadata={"job_id": "payment-role", "required_skills": ["Python", "React"],
                  "required_competencies": ["System Design", "Customer Impact"],
                  "current_round_id": "panel-round", "candidate_profile": {"skills": ["Kafka"]}},
    ))

    async def cloud_start(**kwargs):
        live = contexts.get(kwargs["interview_id"])
        assert live is not None and live.candidate_id == "candidate-real"
        assert live.current_round_id == "panel-round"
        assert live.missing_competencies == ["system_design", "customer_impact"]
        assert live.metadata["job_title"] == "Payments Engineer"
        assert live.metadata["company"] == "Example"
        assert live.metadata["configured_agent_ids"] == ["alex", "jordan"]
        assert live.metadata["candidate_profile"]["skills"] == ["Kafka"]
        return {"status": "started", "agora_agent_id": "initial-cloud"}

    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.start_interview_agent", AsyncMock(side_effect=cloud_start))
    await service.start_session(session.interview_id)
    assert contexts.get(session.interview_id) is contexts.get(session.channel_name)


def test_skills_do_not_become_routing_competencies():
    from app.agents.registry import agent_registry
    service = InterviewSessionService(store=SessionStore())
    session = service.create_session(InterviewConfiguration(
        interview_id="skill-only", candidate_id="candidate", agent_ids=["jordan"],
        metadata={"required_skills": ["Python", "React"]},
    ))
    service._prepare_context_metadata(session)
    assert session.metadata["required_competencies"] == agent_registry.get_profile("jordan").focal_competencies
    assert "python" not in session.metadata["required_competencies"]


def test_public_session_info_exposes_lifecycle_without_context_data(meeting):
    from app.routes.sessions import _session_to_info
    _, session, context, _, _ = meeting
    context.metadata.update(pending_voice_action="COMPLETE", completed=True,
                            voice_lifecycle={"status": "waiting_for_audio"})
    result = _session_to_info(session).model_dump()
    assert result["completed"] is True
    assert result["status"] == "IN_PROGRESS"
    assert result["pending_voice_action"] == "COMPLETE"
    assert result["voice_lifecycle_status"] == "waiting_for_audio"
    assert "candidate_profile" not in str(result)
    assert "Kafka" not in str(result)


@pytest.mark.asyncio
async def test_end_arriving_during_old_voice_stop_prevents_target_dispatch(meeting, monkeypatch):
    service, session, context, contexts, calls = meeting
    entered, release = asyncio.Event(), asyncio.Event()
    context.metadata.update(pending_voice_action="SWITCH_AGENT", pending_voice_request_id="switch-1")

    async def stop(**kwargs):
        calls.append(("stop", kwargs))
        entered.set()
        await release.wait()
        return {"status": "stopped"}

    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.stop_interview_agent", AsyncMock(side_effect=stop))
    agora = type("Agora", (), {})()
    agora.get_agent_history = AsyncMock(return_value=history())
    task = asyncio.create_task(finish_response(
        session.channel_name, NextAction(action=ActionType.SWITCH_AGENT, target_agent_id="jordan"),
        "Thank you for your time.", response_started_at_ms=1000,
        expected_agent_id="alex", expected_agora_agent_id="cloud-alex-1", request_id="switch-1",
        session_service=service, agora_service=agora, context_store=contexts,
    ))
    await entered.wait()
    context.metadata.update(completed=True, completion_reason="candidate_requested",
                            pending_voice_action="COMPLETE", pending_voice_request_id="end-2")
    release.set()
    result = await task
    assert result["status"] == "stale"  # The obsolete SWITCH never reports success.
    assert result["result"]["reason"] == "completion_requested_during_handoff"
    assert session.status == SessionStatus.COMPLETED
    assert context.current_agent_id == session.current_agent_id == "alex"
    assert context.metadata["completed"] is True
    assert session.metadata["completion_reason"] == "candidate_requested"
    assert [call[0] for call in calls] == ["stop"]
    assert not session.started_agents
    assert not session.metadata.get("handoff_history") and not context.metadata.get("handoff_history")


@pytest.mark.asyncio
async def test_end_arriving_during_target_join_stops_target_without_committing_persona(meeting, monkeypatch):
    service, session, context, _, calls = meeting
    entered, release = asyncio.Event(), asyncio.Event()
    context.metadata.update(pending_voice_action="SWITCH_AGENT", pending_voice_request_id="switch-1")

    async def start(**kwargs):
        calls.append(("start", kwargs))
        entered.set()
        await release.wait()
        return {"status": "started", "agora_agent_id": "cloud-jordan-inflight"}

    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.start_interview_agent", AsyncMock(side_effect=start))
    task = asyncio.create_task(service.handoff_agent(
        session.channel_name, "jordan", expected_voice_request_id="switch-1",
    ))
    await entered.wait()
    context.metadata.update(completed=True, completion_reason="candidate_requested",
                            pending_voice_action="COMPLETE", pending_voice_request_id="end-2")
    release.set()
    result = await task
    assert result["status"] == "superseded"
    assert session.status == SessionStatus.COMPLETED
    assert context.current_agent_id == session.current_agent_id == "alex"
    assert [call[0] for call in calls] == ["stop", "start", "stop"]
    assert calls[-1][1]["agora_agent_id"] == "cloud-jordan-inflight"
    assert not session.started_agents
    assert not session.metadata.get("handoff_history") and not context.metadata.get("handoff_history")


@pytest.mark.asyncio
async def test_failed_cleanup_keeps_target_generation_and_end_request_for_retry(meeting, monkeypatch):
    service, session, context, _, _ = meeting

    async def start(**kwargs):
        context.metadata.update(completed=True, pending_voice_action="COMPLETE", pending_voice_request_id="end-2")
        return {"status": "started", "agora_agent_id": "cloud-jordan-inflight"}

    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.start_interview_agent", AsyncMock(side_effect=start))
    monkeypatch.setattr("app.services.agora_agent_service.agora_agent_service.stop_interview_agent", AsyncMock(side_effect=[
        {"status": "stopped"}, {"status": "error", "error": "HTTP 503"}, {"status": "stopped"},
    ]))
    with pytest.raises(ValidationError, match="503"):
        await service.handoff_agent(session.channel_name, "jordan", expected_voice_request_id="switch-1")
    assert session.current_agent_id == context.current_agent_id == "alex"
    assert session.started_agents == {"jordan": "cloud-jordan-inflight"}
    assert context.metadata["pending_voice_action"] == "COMPLETE"
    assert context.metadata["pending_voice_request_id"] == "end-2"
    await service.stop_session(session.channel_name, expected_voice_request_id="end-2")
    assert not session.started_agents and session.status == SessionStatus.COMPLETED


@pytest.mark.asyncio
async def test_complete_with_confirmed_already_stopped_generation_does_not_wait_for_impossible_audio(meeting):
    service, session, context, contexts, calls = meeting
    session.started_agents.clear()
    session.metadata["confirmed_stopped_agora_agents"] = ["cloud-alex-1"]
    context.metadata.update(completed=True, pending_voice_action="COMPLETE", pending_voice_request_id="end-2")
    agora = type("Agora", (), {})()
    agora.get_agent_history = AsyncMock()
    result = await finish_response(
        session.channel_name, NextAction(action=ActionType.COMPLETE), "Thank you for your time.",
        response_started_at_ms=1000, expected_agent_id="alex", expected_agora_agent_id="cloud-alex-1", request_id="end-2",
        session_service=service, agora_service=agora, context_store=contexts,
    )
    assert result["status"] == "applied" and result["audio_note"] == "agent_already_stopped"
    assert session.status == SessionStatus.COMPLETED
    agora.get_agent_history.assert_not_awaited()
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize("cloud_history,expected_note", [
    (history(end=None), "farewell_audio_unconfirmed"),
    (history(interrupted=True), "farewell_interrupted"),
    ({**history(), "channel": "wrong-channel"}, "history_identity_unconfirmed"),
    (None, "farewell_audio_unconfirmed"),
])
async def test_end_stops_after_unconfirmed_or_interrupted_farewell(meeting, cloud_history, expected_note):
    service, session, context, contexts, calls = meeting
    context.metadata.update(completed=True, pending_voice_action="COMPLETE", pending_voice_request_id="end-2")
    agora = type("Agora", (), {})()
    agora.get_agent_history = AsyncMock(side_effect=TimeoutError("history unavailable")) if cloud_history is None else AsyncMock(return_value=cloud_history)
    result = await finish_response(
        session.channel_name, NextAction(action=ActionType.COMPLETE), "Thank you for your time.",
        response_started_at_ms=1000, expected_agent_id="alex", expected_agora_agent_id="cloud-alex-1", request_id="end-2",
        timeout_seconds=0.001, poll_interval_seconds=0, session_service=service, agora_service=agora, context_store=contexts,
    )
    assert result["status"] == "applied" and result["audio_note"] == expected_note
    assert session.status == SessionStatus.COMPLETED
    assert [call[0] for call in calls] == ["stop"]
