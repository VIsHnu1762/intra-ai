"""Assistant lifecycle contracts using in-memory Redis and synthetic identities."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import ConflictError, ForbiddenError, register_exception_handlers
from app.core.security import create_access_token
from app.voice.agora import AgoraProjectConfig, AgoraStudioAgentConfig, AuxiliaryAgoraError, TrainingHRAgoraService
from app.voice.models import DashboardContext, utc_now
from app.voice.routes import router
from app.voice.security import verify_mcp_token
from app.voice.service import VoiceAssistantService
from app.voice.store import VoiceSessionStore
from tests.test_voice_tools import DB


class MemoryRedis:
    def __init__(self):
        self.values, self.sets, self.locks = {}, {}, {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    async def srem(self, key, value):
        self.sets.setdefault(key, set()).discard(value)

    async def smembers(self, key):
        return set(self.sets.get(key, set()))

    @asynccontextmanager
    async def lock(self, key, **_kwargs):
        async with self.locks.setdefault(key, asyncio.Lock()):
            yield


def browser_headers(user="user-a", **claims):
    return {"Authorization": "Bearer " + create_access_token({"sub": user, **claims})}


@pytest.fixture
def voice_env(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "synthetic-voice-test-signing-secret")
    monkeypatch.setattr(settings, "VOICE_ASSISTANT_PUBLIC_URL", "https://voice.example.test")
    monkeypatch.setattr(settings, "VOICE_ASSISTANT_SESSION_SECONDS", 600)
    monkeypatch.setattr(settings, "VOICE_ASSISTANT_IDLE_SECONDS", 120)
    monkeypatch.setattr(settings, "AGORA_APP_ID", "a" * 32)
    config = AgoraProjectConfig("1" * 32, "2" * 32,
        AgoraStudioAgentConfig("taylor", "training-pipeline", "201"),
        AgoraStudioAgentConfig("morgan", "hr-pipeline", "202"))
    db, redis = DB(), MemoryRedis()
    agora = TrainingHRAgoraService(config)
    agora.start_agent = AsyncMock(return_value={"agent_id": "cloud-agent", "status": "RUNNING"})
    agora.stop_agent = AsyncMock(return_value={"status": "STOPPED"})
    agora.query_agent = AsyncMock(return_value={"status": "RUNNING"})
    agora.announce_result = AsyncMock(return_value={"status": "ANNOUNCEMENT_ACCEPTED"})
    service = VoiceAssistantService(db, redis, agora=agora)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.state.voice_assistants = service
    return SimpleNamespace(db=db, redis=redis, agora=agora, service=service, app=app)


@pytest.mark.asyncio
async def test_training_lifecycle_isolated_and_browser_receives_only_join_tokens(voice_env, monkeypatch):
    from app.interview_context.store import interview_session_store
    from app.voice import service as service_module
    monkeypatch.setattr(interview_session_store, "get_or_create", MagicMock(side_effect=AssertionError("Official context must not be used")))
    monkeypatch.setattr(service_module, "issue_mcp_token", MagicMock(side_effect=AssertionError("Taylor must not receive MCP credentials")))
    env = voice_env
    next(row for row in env.db.rows["users"] if row["id"] == "user-a")["name"] = "Ada Lovelace"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(),
            json={"context": {"job_id": "job-a", "application_id": "application-a"}})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["app_id"] == "1" * 32 != settings.AGORA_APP_ID
        assert body["agent_name"] == "Taylor" and body["agent_type"] == "TAYLOR_TRAINING"
        assert body["rtc_token"].startswith("007") and body["rtm_token"].startswith("007")
        assert body["rtc_token"] != body["rtm_token"]
        assert not {"app_certificate", "api_token", "mcp_token", "cloud_agent_id"} & body.keys()
        session = await env.service.store.get(body["session_id"])
        dispatch = env.agora.start_agent.call_args
        assert dispatch.args[:3] == ("taylor", body["channel_name"], body["rtc_uid"])
        assert env.service.allowed_tools("taylor") == []
        assert not {"allowed_tools", "mcp_endpoint", "mcp_authorization"} & dispatch.kwargs.keys()
        prompt = dispatch.kwargs["system_prompt"]
        assert "Python" in prompt and "Engineer" in prompt and "Ada" in prompt
        assert "practice" in prompt.lower()
        assert "private-cross-job.pdf" not in prompt and '"private"' not in prompt
        assert body["practice"]["experience_level"] == "intern"
        assert (session.expires_at - session.started_at).total_seconds() <= 600
        for _ in range(2):
            ended = await client.post(f"/api/v1/voice/sessions/{session.session_id}/end", headers=browser_headers())
            assert ended.status_code == 200 and ended.json()["status"] == "DISCONNECTED"
        assert env.agora.stop_agent.await_count == 1
        assert not await env.service.store.active_ids()
    assert env.db.writes == []
    assert all(key.startswith(VoiceSessionStore.PREFIX) for key in [*env.redis.values, *env.redis.sets])


@pytest.mark.asyncio
async def test_taylor_start_needs_no_public_tool_endpoint_and_preserves_practice_options(voice_env, monkeypatch):
    monkeypatch.setattr(settings, "VOICE_ASSISTANT_PUBLIC_URL", "")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(), json={
            "context": {"application_id": "application-a"},
            "practice": {"target_role": "Frontend Intern", "experience_level": "intern"}})
    assert response.status_code == 201, response.text
    assert response.json()["practice"] == {"target_role": "Frontend Intern", "experience_level": "intern"}
    prompt = voice_env.agora.start_agent.call_args.kwargs["system_prompt"]
    assert "Frontend Intern" in prompt and "Python" in prompt
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_morgan_keeps_session_bound_mcp_credentials(voice_env):
    result = await voice_env.service.start("morgan", {"sub": "recruiter-a"}, DashboardContext())
    options = voice_env.agora.start_agent.call_args.kwargs
    assert options["mcp_endpoint"] == "https://voice.example.test/api/v1/voice/mcp"
    assert "schedule_interview" in options["allowed_tools"]
    assert "get_training_context" not in options["allowed_tools"]
    claims = verify_mcp_token(options["mcp_authorization"].removeprefix("Bearer "))
    assert (claims["sid"], claims["sub"], claims["persona"]) == (result["session_id"], "recruiter-a", "morgan")
    assert result["practice"] is None
    assert json.loads(options["system_prompt"].split("\nPAGE_CONTEXT_JSON\n", 1)[1]) == {"selected_resources": {}}


@pytest.mark.asyncio
async def test_morgan_start_preloads_authorized_selection_without_context_tool_call(voice_env):
    result = await voice_env.service.start("morgan", {"sub": "recruiter-a"},
        DashboardContext(candidate_id="candidate-a", application_id="application-a"))
    prompt = voice_env.agora.start_agent.call_args.kwargs["system_prompt"]
    page = json.loads(prompt.split("\nPAGE_CONTEXT_JSON\n", 1)[1])["selected_resources"]
    assert page["candidate"] == {"id": "candidate-a", "name": "Ada"}
    assert page["application"]["id"] == "application-a"
    assert page["job"] == {"id": "job-a", "title": "Engineer"}
    assert "private-cross-job.pdf" not in prompt
    assert voice_env.db.writes == []
    assert not (await voice_env.service.store.get(result["session_id"])).pending_action


@pytest.mark.asyncio
async def test_morgan_still_requires_public_tool_endpoint(voice_env, monkeypatch):
    monkeypatch.setattr(settings, "VOICE_ASSISTANT_PUBLIC_URL", "")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/morgan/sessions", headers=browser_headers("recruiter-a"), json={})
    assert response.status_code == 503
    voice_env.agora.start_agent.assert_not_awaited()
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_morgan_rejects_practice_options_before_cloud_dispatch(voice_env):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/morgan/sessions", headers=browser_headers("recruiter-a"),
            json={"practice": {"target_role": "Engineer", "experience_level": "junior"}})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "VALIDATION_ERROR"
    voice_env.agora.start_agent.assert_not_awaited()
    assert voice_env.db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("persona,user", [("morgan","user-a"), ("taylor","recruiter-a")])
async def test_persisted_role_blocks_wrong_assistant_before_cloud_dispatch(voice_env, persona, user):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/voice/{persona}/sessions",
            headers=browser_headers(user, role="admin"), json={})
    assert response.status_code == 403
    voice_env.agora.start_agent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer bad.jwt.value"}])
async def test_browser_endpoints_require_valid_auth(voice_env, headers):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/taylor/sessions", headers=headers, json={})
    assert response.status_code == 401
    voice_env.agora.start_agent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix,method,payload", [("","GET",None), ("/heartbeat","POST",None),
    ("/end","POST",None), ("/context","POST",{"context":{}}),
    ("/tools","POST",{"tool":"get_training_context","args":{}}),
    ("/confirm","POST",{"confirmation_id":"not-real","approved":True})])
async def test_cross_user_session_access_denied(voice_env, suffix, method, payload):
    session = await voice_env.service.start("taylor", {"sub":"user-a"}, DashboardContext())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.request(method, "/api/v1/voice/sessions/" + session["session_id"] + suffix,
            headers=browser_headers("user-b"), json=payload)
    assert response.status_code == 403
    voice_env.agora.stop_agent.assert_not_awaited()
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_duplicate_start_does_not_create_second_agent(voice_env):
    first = await voice_env.service.start("taylor", {"sub":"user-a"}, DashboardContext())
    with pytest.raises(ConflictError):
        await voice_env.service.start("taylor", {"sub":"user-a"}, DashboardContext())
    assert voice_env.agora.start_agent.await_count == 1
    assert await voice_env.service.store.active_ids() == [first["session_id"]]


@pytest.mark.asyncio
async def test_generated_uid_respects_provider_cap_and_retries_both_agent_collisions(voice_env, monkeypatch):
    from app.voice import service as service_module
    values = iter([200, 201, None])  # +1 first collides with Taylor, then Morgan.
    requested_bounds = []

    def randbelow(upper):
        requested_bounds.append(upper)
        assert upper == 2147483647
        value = next(values)
        return upper - 1 if value is None else value

    monkeypatch.setattr(service_module.secrets, "randbelow", randbelow)
    result = await voice_env.service.start("taylor", {"sub":"user-a"}, DashboardContext())
    assert requested_bounds == [2147483647] * 3
    assert result["rtc_uid"] == 2147483647
    assert voice_env.agora.start_agent.call_args.args[2] == 2147483647
    stored = await voice_env.service.store.get(result["session_id"])
    assert stored.rtc_uid == 2147483647
    assert str(stored.rtc_uid) not in {voice_env.agora.project.taylor.agent_rtc_uid,
                                    voice_env.agora.project.morgan.agent_rtc_uid}


@pytest.mark.asyncio
async def test_heartbeat_refreshes_idle_time_but_not_session_expiry(voice_env):
    result = await voice_env.service.start("taylor", {"sub":"user-a"}, DashboardContext())
    stored = await voice_env.service.store.get(result["session_id"])
    stored.heartbeat_at = utc_now() - timedelta(seconds=30)
    await voice_env.service.store.put(stored)
    before_expiry, before_heartbeat = stored.expires_at, stored.heartbeat_at
    await voice_env.service.get(stored.session_id, {"sub":"user-a"}, heartbeat=True)
    refreshed = await voice_env.service.store.get(stored.session_id)
    assert refreshed.heartbeat_at > before_heartbeat and refreshed.expires_at == before_expiry
    assert voice_env.agora.query_agent.await_count == 1
    await voice_env.service.get(stored.session_id, {"sub":"user-a"}, heartbeat=True)
    assert voice_env.agora.query_agent.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["expired", "idle"])
async def test_reaper_stops_expired_or_abandoned_cloud_session(voice_env, reason):
    result = await voice_env.service.start("taylor", {"sub":"user-a"}, DashboardContext())
    stored = await voice_env.service.store.get(result["session_id"])
    if reason == "expired":
        stored.expires_at = utc_now() - timedelta(seconds=1)
    else:
        stored.heartbeat_at = utc_now() - timedelta(seconds=121)
    await voice_env.service.store.put(stored)
    await voice_env.service.expire_sessions()
    assert (await voice_env.service.store.get(stored.session_id)).status == "DISCONNECTED"
    voice_env.agora.stop_agent.assert_awaited_once()
    with pytest.raises(ConflictError):
        await voice_env.service.call_tool(stored.session_id, {"sub":"user-a"}, "get_training_context", {})


@pytest.mark.asyncio
async def test_provider_start_failure_retained_as_error_without_tokens(voice_env):
    voice_env.agora.start_agent.side_effect = AuxiliaryAgoraError("VOICE_PROVIDER_TIMEOUT", "The voice provider timed out.", http_status=504)
    voice_env.agora.candidate_credentials = MagicMock(side_effect=AssertionError("A failed join must not issue browser credentials"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(), json={})
    assert response.status_code == 504
    assert not await voice_env.service.store.active_ids()
    records = [raw for key, raw in voice_env.redis.values.items() if ":session:" in key]
    assert len(records) == 1 and '"status":"ERROR"' in records[0]
    assert all(not {"rtc_token", "rtm_token", "mcp_token", "app_certificate", "api_token"} & json.loads(raw).keys()
               for raw in records)
    voice_env.agora.candidate_credentials.assert_not_called()


@pytest.mark.asyncio
async def test_failed_cloud_start_is_explicitly_stopped(voice_env):
    voice_env.agora.start_agent.return_value = {"agent_id":"cloud-failed", "status":"FAILED"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(), json={})
    assert response.status_code == 503
    assert voice_env.agora.stop_agent.call_args.args[-1] == "cloud-failed"
    assert not await voice_env.service.store.active_ids()


@pytest.mark.asyncio
async def test_candidate_token_failure_after_join_cleans_up_cloud_agent(voice_env):
    voice_env.agora.candidate_credentials = MagicMock(side_effect=AuxiliaryAgoraError("VOICE_TOKEN_ERROR", "Token generation failed."))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(), json={})
    assert response.status_code == 502
    voice_env.agora.stop_agent.assert_awaited_once()
    assert not await voice_env.service.store.active_ids()


@pytest.mark.asyncio
async def test_failed_cleanup_keeps_cloud_identifier_for_reaper_retry(voice_env):
    voice_env.agora.start_agent.return_value = {"agent_id":"cloud-failed", "status":"FAILED"}
    voice_env.agora.stop_agent.side_effect = AuxiliaryAgoraError("VOICE_PROVIDER_TIMEOUT", "Timeout")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(), json={})
    ids = await voice_env.service.store.active_ids()
    assert len(ids) == 1
    stored = await voice_env.service.store.get(ids[0])
    assert stored.status == "ERROR" and stored.cloud_agent_id == "cloud-failed"
    voice_env.agora.stop_agent.side_effect = None
    await voice_env.service.expire_sessions()
    assert not await voice_env.service.store.active_ids()


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_id", ["candidate-a", "candidate-b"])
async def test_taylor_context_remains_fixed_until_new_practice_session(voice_env, candidate_id):
    result = await voice_env.service.start("taylor", {"sub":"user-a"}, DashboardContext(application_id="application-a"))
    with pytest.raises(ConflictError):
        await voice_env.service.update_context(result["session_id"], {"sub":"user-a"}, DashboardContext(candidate_id=candidate_id))
    saved = await voice_env.service.store.get(result["session_id"])
    assert saved.dashboard_context.application_id == "application-a"
    assert voice_env.db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("context", [{"candidate_id": "candidate-b"}, {"application_id": "application-b"}, {"job_id": "job-b", "application_id": "application-a"}])
async def test_taylor_start_rejects_other_candidate_and_mismatched_context(voice_env, context):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/taylor/sessions", headers=browser_headers(), json={"context": context})
    assert response.status_code == 403, response.text
    voice_env.agora.start_agent.assert_not_awaited()
    assert not await voice_env.service.store.active_ids()
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_morgan_dashboard_navigation_reauthorizes_selected_candidate(voice_env):
    result = await voice_env.service.start("morgan", {"sub": "recruiter-a"}, DashboardContext(application_id="application-a"))
    with pytest.raises(ForbiddenError):
        await voice_env.service.update_context(result["session_id"], {"sub": "recruiter-a"}, DashboardContext(candidate_id="candidate-b"))
    saved = await voice_env.service.store.get(result["session_id"])
    assert saved.dashboard_context.application_id == "application-a"
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_confirmation_replay_reauthorizes_current_resource_access(voice_env):
    env = voice_env
    result = await env.service.start("morgan", {"sub":"recruiter-a"}, DashboardContext(application_id="application-a"))
    pending = await env.service.call_tool(result["session_id"], {"sub":"recruiter-a"}, "update_application_status",
                                        {"application_id":"application-a", "status":"invited"})
    confirmation_id = pending["pending_action"]["confirmation_id"]
    first = await env.service.confirm(result["session_id"], {"sub":"recruiter-a"}, confirmation_id, True)
    assert first["status"] == "executing"
    await asyncio.gather(*list(env.service._confirmation_tasks.values()))
    completed = await env.service.confirm(result["session_id"], {"sub":"recruiter-a"}, confirmation_id, True)
    assert completed["status"] == "succeeded"
    env.db.rows["jobs"][0]["created_by"] = "recruiter-b"
    with pytest.raises(ForbiddenError):
        await env.service.confirm(result["session_id"], {"sub":"recruiter-a"}, confirmation_id, True)


@pytest.mark.asyncio
async def test_pending_action_status_reauthorizes_action_resource_with_empty_dashboard(voice_env):
    env = voice_env
    result = await env.service.start("morgan", {"sub":"recruiter-a"}, DashboardContext())
    await env.service.call_tool(result["session_id"], {"sub":"recruiter-a"}, "update_application_status",
                               {"application_id":"application-a", "status":"invited"})
    env.db.rows["jobs"][0]["created_by"] = "recruiter-b"
    with pytest.raises(ForbiddenError):
        await env.service.call_tool(result["session_id"], {"sub":"recruiter-a"}, "get_action_status", {})
    assert env.db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("completed", [False, True])
async def test_get_session_withholds_cached_action_after_resource_access_revoked(voice_env, completed):
    env = voice_env
    result = await env.service.start("morgan", {"sub":"recruiter-a"}, DashboardContext())
    proposal = await env.service.call_tool(result["session_id"], {"sub":"recruiter-a"}, "update_application_status",
                                          {"application_id":"application-a", "status":"invited"})
    if completed:
        await env.service.confirm(result["session_id"], {"sub":"recruiter-a"},
                                  proposal["pending_action"]["confirmation_id"], True)
        await asyncio.gather(*list(env.service._confirmation_tasks.values()))
    env.db.rows["jobs"][0]["created_by"] = "recruiter-b"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/voice/sessions/{result['session_id']}", headers=browser_headers("recruiter-a"))
    # Returning the lifecycle view with redacted resource data or a scoped
    # access error is safe; returning the old cached action is not.
    assert response.status_code in {200, 403, 404}, response.text
    if response.status_code == 200:
        assert response.json()["pending_action"] is None
        assert response.json()["last_tool_result"] is None
    assert "application-a" not in response.text and "candidate-a" not in response.text


@pytest.mark.asyncio
async def test_new_service_can_read_and_end_stored_session_after_restart(voice_env):
    result = await voice_env.service.start("taylor", {"sub":"user-a"}, DashboardContext())
    replacement = VoiceAssistantService(voice_env.db, voice_env.redis, agora=voice_env.agora)
    visible = await replacement.get(result["session_id"], {"sub":"user-a"})
    assert visible["status"] == "CONNECTED"
    assert not {"rtc_token", "rtm_token", "cloud_agent_id", "channel_name"} & visible.keys()
    ended = await replacement.end(result["session_id"], {"sub":"user-a"})
    assert ended["status"] == "DISCONNECTED"
