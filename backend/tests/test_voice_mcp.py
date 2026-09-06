"""Stateless Streamable HTTP MCP authorization with synthetic session data."""
from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import httpx
from jose import jwt
import pytest

from app.core.config import settings
from app.voice.models import DashboardContext
from app.voice.security import issue_mcp_token
from app.voice.service import VoiceAssistantService
from app.voice import routes as voice_routes
from app.voice.tools import tool_schemas
from tests.test_voice_sessions import browser_headers, voice_env


async def new_session(env, persona="morgan"):
    user = "user-a" if persona == "taylor" else "recruiter-a"
    result = await env.service.start(persona, {"sub": user}, DashboardContext(application_id="application-a", candidate_id="candidate-a"))
    session = await env.service.store.get(result["session_id"])
    return session, {"Authorization": "Bearer " + issue_mcp_token(session),
                     "Accept": "application/json, text/event-stream"}


def rpc(method, params=None, rpc_id=1):
    return {"jsonrpc":"2.0", "id":rpc_id, "method":method, "params":params or {}}


def forged_claims(session, **changes):
    claims = {"sub":session.user_id, "sid":session.session_id, "persona":session.persona,
        "iss":"intra-ai", "aud":"intra-voice-mcp", "exp":int(session.expires_at.timestamp())}
    claims.update(changes)
    return {"Authorization": "Bearer " + jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)}


@pytest.fixture
def mcp_batch(voice_env):
    db = voice_env.db
    db.rows["applications"][0]["status"] = "applied"
    db.rows["candidates"].append({"id": "candidate-c", "name": "Chris", "email": "chris@example.test"})
    db.rows["applications"].append({"id": "application-c", "job_id": "job-a", "candidate_id": "candidate-c", "status": "applied"})
    db.rows["interview_templates"] = [{"id": "template-a", "name": "Practice interview", "description": "Synthetic",
        "created_by": "recruiter-a", "tenant_id": None, "version": 1, "archived_at": None,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        "duration_minutes": 20, "rounds": [{"id": "intro", "type": "introduction", "name": "Introduction",
            "enabled": True, "duration_minutes": 20, "agent_ids": ["alex", "jordan"], "focus_areas": ["Communication"]}]}]
    return ["application-a", "application-c"]


def bulk_arguments(tool, application_ids):
    args = {"application_ids": application_ids}
    if tool == "bulk_schedule_interviews":
        args.update(job_id="job-a", template_id="template-a", start_at="2099-01-01T15:30:00+05:30",
                    timezone="Asia/Kolkata", gap_minutes=5)
    return args


def test_mcp_bulk_schema_encoding_does_not_mutate_canonical_schema(monkeypatch):
    canonical = tool_schemas()
    before = deepcopy(canonical)
    # A shared cache must be safe too; repeated transport adaptation cannot
    # replace the list contracts consumed by the service or browser endpoint.
    monkeypatch.setattr(voice_routes, "tool_schemas", lambda: canonical)
    for _ in range(2):
        adapted = {item["name"]: item for item in voice_routes.mcp_tools("morgan")}
        for item in before:
            if item["name"] in {"bulk_shortlist_candidates", "bulk_schedule_interviews"}:
                original = item["inputSchema"]["properties"]["application_ids"]
                encoded = adapted[item["name"]]["inputSchema"]["properties"]["application_ids"]
                assert original["type"] == "array" and encoded["type"] == "string"
                assert encoded["maxLength"] == 8192
                restored = deepcopy(adapted[item["name"]])
                restored["inputSchema"]["properties"]["application_ids"] = original
                assert restored == item
            else:
                assert adapted[item["name"]] == item
        assert canonical == before
    assert voice_routes.mcp_tools("taylor") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["bulk_shortlist_candidates", "bulk_schedule_interviews"])
async def test_mcp_encoded_bulk_ids_and_canonical_lists_produce_same_review_without_writes(voice_env, mcp_batch, tool):
    session, headers = await new_session(voice_env)
    reviews = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        catalog = await client.post("/api/v1/voice/mcp", headers=headers, json=rpc("tools/list"))
        schema = next(item for item in catalog.json()["result"]["tools"] if item["name"] == tool)
        assert schema["inputSchema"]["properties"]["application_ids"]["type"] == "string"
        for ids in [json.dumps(mcp_batch), mcp_batch, ",".join(mcp_batch), "  " + " ,  ".join(mcp_batch) + "  "]:
            response = await client.post("/api/v1/voice/mcp", headers=headers,
                json=rpc("tools/call", {"name": tool, "arguments": bulk_arguments(tool, ids)}))
            assert response.status_code == 200 and response.json()["result"]["isError"] is False, response.text
            proposed = json.loads(response.json()["result"]["content"][0]["text"])
            assert proposed["status"] == "confirmation_required"
            pending = proposed["pending_action"]
            assert pending["tool"] == tool and pending["details"]["eligible_count"] == 2
            reviews.append(pending["details"])
            assert voice_env.db.writes == []
            persisted = await voice_env.service.store.get(session.session_id)
            assert persisted.pending_action["confirmation_id"] == pending["confirmation_id"]
            declined = await client.post(f"/api/v1/voice/sessions/{session.session_id}/confirm",
                headers=browser_headers("recruiter-a"),
                json={"confirmation_id": pending["confirmation_id"], "approved": False})
            assert declined.status_code == 200
    assert all(review == reviews[0] for review in reviews)
    assert voice_env.db.writes == []
    assert {row["status"] for row in voice_env.db.rows["applications"] if row["id"] in mcp_batch} == {"applied"}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["bulk_shortlist_candidates", "bulk_schedule_interviews"])
async def test_mcp_scalar_single_application_id_is_a_one_item_review(voice_env, mcp_batch, tool):
    session, headers = await new_session(voice_env)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name": tool, "arguments": bulk_arguments(tool, " application-a ")}))
    result = json.loads(response.json()["result"]["content"][0]["text"])
    assert response.json()["result"]["isError"] is False and result["status"] == "confirmation_required"
    assert result["pending_action"]["details"]["eligible_count"] == 1
    assert voice_env.db.writes == []
    await voice_env.service.confirm(session.session_id, {"sub": "recruiter-a"}, result["pending_action"]["confirmation_id"], False)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["bulk_shortlist_candidates", "bulk_schedule_interviews"])
@pytest.mark.parametrize("encoded", [
    '["application-a",', '{"application_ids":["application-a"]}', '"application-a"', "null", "true", "1",
    " " * 8192 + "[]", "[]", '["application-a","application-a"]', '[123]', '[null]', '[NaN]',
    '["application-a;DROP"]', json.dumps([f"application-{index}" for index in range(51)]),
    "", " ", "application-a,", ",application-a", "application-a,,application-c", "application-a,  ,application-c",
    "application-a,application-a", "'application-a','application-c'", "['application-a','application-c']",
    "application-a,application-c;DROP", "application-a," + "b" * 129,
])
async def test_mcp_bulk_input_errors_never_propose_or_write(voice_env, mcp_batch, tool, encoded):
    session, headers = await new_session(voice_env)
    before = deepcopy(voice_env.db.rows)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name": tool, "arguments": bulk_arguments(tool, encoded)}))
    assert response.status_code == 200 and response.json()["result"]["isError"] is True
    result = json.loads(response.json()["result"]["content"][0]["text"])
    assert result["code"] == "VALIDATION_ERROR"
    assert result["message"] in {"Invalid tool arguments", voice_routes._MCP_APPLICATION_IDS_ERROR}
    assert not (await voice_env.service.store.get(session.session_id)).pending_action
    assert voice_env.db.writes == [] and voice_env.db.rows == before


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["bulk_shortlist_candidates", "bulk_schedule_interviews"])
@pytest.mark.parametrize("encoding", ["list", "json", "csv"])
async def test_mcp_bulk_decoding_preserves_resource_authorization(voice_env, mcp_batch, tool, encoding):
    session, headers = await new_session(voice_env)
    ids = ["application-a", "application-b"]  # application-b belongs to recruiter-b.
    encoded = {"list": ids, "json": json.dumps(ids), "csv": ",".join(ids)}[encoding]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name": tool, "arguments": bulk_arguments(tool, encoded)}))
    assert response.status_code == 200 and response.json()["result"]["isError"] is True
    result = json.loads(response.json()["result"]["content"][0]["text"])
    assert result["code"] == "FORBIDDEN"
    assert "Bea" not in response.text and "b@example.test" not in response.text
    assert not (await voice_env.service.store.get(session.session_id)).pending_action
    assert voice_env.db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,count", [("bulk_shortlist_candidates", 51), ("bulk_schedule_interviews", 26)])
@pytest.mark.parametrize("encoding", ["json", "csv"])
async def test_mcp_encoded_bulk_ids_keep_distinct_canonical_batch_limits(voice_env, tool, count, encoding):
    session, headers = await new_session(voice_env)
    ids = [f"application-{index}" for index in range(count)]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name": tool, "arguments": bulk_arguments(tool,
                json.dumps(ids) if encoding == "json" else ",".join(ids))}))
    result = json.loads(response.json()["result"]["content"][0]["text"])
    assert response.json()["result"]["isError"] is True and result["code"] == "VALIDATION_ERROR"
    assert not (await voice_env.service.store.get(session.session_id)).pending_action
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_mcp_encoded_list_adaptation_does_not_change_browser_tool_contract(voice_env, mcp_batch):
    session, _ = await new_session(voice_env)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/voice/sessions/{session.session_id}/tools",
            headers=browser_headers("recruiter-a"), json={"tool": "bulk_shortlist_candidates",
                "args": {"application_ids": json.dumps(mcp_batch)}})
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"
    assert not (await voice_env.service.store.get(session.session_id)).pending_action
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_streamable_initialization_tools_listing_and_readonly_dashboard(voice_env):
    session, headers = await new_session(voice_env)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        initialized = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("initialize", {"protocolVersion":"2025-03-26", "clientInfo":{"name":"synthetic-agora","version":"1"}}))
        assert initialized.status_code == 200
        assert initialized.json()["result"]["protocolVersion"] == "2025-03-26"
        notification = await client.post("/api/v1/voice/mcp", headers=headers,
            json={"jsonrpc":"2.0","method":"notifications/initialized"})
        assert notification.status_code == 202
        listed = await client.post("/api/v1/voice/mcp", headers=headers, json=rpc("tools/list"))
        names = {item["name"] for item in listed.json()["result"]["tools"]}
        assert names == set(voice_env.service.allowed_tools("morgan"))
        assert {"get_dashboard_context", "get_action_status", "schedule_interview"} <= names
        assert "get_training_context" not in names and "confirm_action" not in names
        context = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name":"get_dashboard_context", "arguments":{}}))
        assert context.status_code == 200 and context.json()["result"]["isError"] is False
        content = context.json()["result"]["content"][0]["text"]
        data = json.loads(content)["data"]
        assert data["purpose"] == "recruiter_assistance"
        assert data["candidate"] == {"id": "candidate-a", "name": "Ada"}
        assert data["application"]["id"] == "application-a"
        assert data["job"]["title"] == "Engineer"
        assert data["cv_claims_not_verified_evidence"]["skills"] == ["Python"]
        assert "private-cross-job.pdf" not in content and '"private"' not in content
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_empty_dashboard_can_search_candidates_without_context_prerequisite(voice_env):
    result = await voice_env.service.start("morgan", {"sub": "recruiter-a"}, DashboardContext())
    session = await voice_env.service.store.get(result["session_id"])
    headers = {"Authorization": "Bearer " + issue_mcp_token(session)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name": "search_candidates", "arguments": {}}))
        assert response.status_code == 200
        assert response.json()["result"]["isError"] is False
        result = json.loads(response.json()["result"]["content"][0]["text"])
        assert result["status"] == "ok"
        matches = result["data"]["matches"]
        assert {item["candidate"]["id"] for item in matches} == {"candidate-a"}
        context = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name": "get_dashboard_context", "arguments": {}}))
        context_result = json.loads(context.json()["result"]["content"][0]["text"])
        assert context_result["data"] == {"purpose": "recruiter_assistance"}
        assert "empty selection is valid" in context_result["message"]
    assert voice_env.db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [None,"Bearer invalid.token","browser"])
async def test_mcp_rejects_missing_bad_or_ordinary_browser_token(voice_env, authorization):
    await new_session(voice_env)
    headers = (browser_headers("recruiter-a") if authorization == "browser" else {"Authorization":authorization} if authorization else {})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers, json=rpc("tools/list"))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_mcp_token_cannot_authenticate_browser_confirmation_route(voice_env):
    session, headers = await new_session(voice_env, "morgan")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post(f"/api/v1/voice/sessions/{session.session_id}/confirm", headers=headers,
            json={"confirmation_id":"not-approved", "approved":True})
    assert response.status_code == 401
    assert voice_env.db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change,expected", [({"sub":"recruiter-b"},403), ({"persona":"taylor"},403),
    ({"sid":"unknown-session"},404), ({"aud":"browser"},401), ({"iss":"wrong-issuer"},401),
    ({"exp":1},401), ({"persona":[]},401)])
async def test_mcp_claims_are_bound_to_owner_session_persona_and_lifetime(voice_env, change, expected):
    session, _ = await new_session(voice_env)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=forged_claims(session, **change), json=rpc("tools/list"))
    assert response.status_code == expected, response.text


@pytest.mark.asyncio
async def test_mcp_token_for_ended_session_is_revoked_even_before_jwt_expiry(voice_env):
    session, headers = await new_session(voice_env)
    await voice_env.service.end(session.session_id, {"sub": session.user_id})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers, json=rpc("tools/list"))
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_mcp_rechecks_persisted_user_activation(voice_env):
    session, headers = await new_session(voice_env)
    next(row for row in voice_env.db.rows["users"] if row["id"] == session.user_id)["is_active"] = False
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers, json=rpc("tools/list"))
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("tenant_id", "revoked-tenant"), ("role", "candidate")])
async def test_mcp_rechecks_persisted_tenant_and_role_after_session_start(voice_env, field, value):
    session, headers = await new_session(voice_env)
    next(row for row in voice_env.db.rows["users"] if row["id"] == session.user_id)[field] = value
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers, json=rpc("tools/list"))
    assert response.status_code == 403
    assert voice_env.db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [rpc("initialize", {"protocolVersion": "2025-03-26"}),
    rpc("tools/list"), rpc("tools/call", {"name": "get_training_context", "arguments": {}})])
async def test_taylor_rejects_even_correctly_signed_session_bound_mcp_token(voice_env, body):
    _, headers = await new_session(voice_env, "taylor")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers, json=body)
    assert response.status_code == 403, response.text
    assert "Python" not in response.text and "candidate-a" not in response.text
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_mcp_credential_in_query_is_never_accepted(voice_env):
    _, headers = await new_session(voice_env)
    token = headers["Authorization"].removeprefix("Bearer ")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", params={"token":token}, json=rpc("tools/list"))
    assert response.status_code == 401
    assert token not in response.text


@pytest.mark.asyncio
async def test_mcp_wrong_origin_is_denied(voice_env):
    _, headers = await new_session(voice_env)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers={**headers,"Origin":"https://other.example.test"}, json=rpc("tools/list"))
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args", [("schedule_interview", {"application_id":"application-a","slot_id":"slot-a"}),
    ("confirm_action", {"confirmation_id":"fake"}), ("get_dashboard_context",{}),
    ("get_training_context", {"candidate_id":"candidate-b"})])
async def test_taylor_rejects_hr_mutations_confirmation_and_context_identifiers(voice_env, tool, args):
    _, headers = await new_session(voice_env, "taylor")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name":tool,"arguments":args}))
    assert response.status_code == 403
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_morgan_mutation_is_proposal_only_and_cannot_confirm_over_mcp(voice_env):
    session, headers = await new_session(voice_env, "morgan")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app), base_url="http://test") as client:
        listed = await client.post("/api/v1/voice/mcp", headers=headers, json=rpc("tools/list"))
        names = {item["name"] for item in listed.json()["result"]["tools"]}
        assert "schedule_interview" in names and "get_dashboard_context" in names
        assert "confirm_action" not in names and "get_training_context" not in names
        proposed = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name":"schedule_interview", "arguments":{"application_id":"application-a","slot_id":"slot-a"}}))
        assert proposed.status_code == 200 and proposed.json()["result"]["isError"] is False
        pending = (await voice_env.service.store.get(session.session_id)).pending_action
        assert pending and pending["confirmation_id"]
        assert voice_env.db.writes == []
        rejected = await client.post("/api/v1/voice/mcp", headers=headers,
            json=rpc("tools/call", {"name":"confirm_action", "arguments":{"confirmation_id":pending["confirmation_id"],"approved":True}}))
        assert rejected.json()["result"]["isError"] is True
    assert voice_env.db.writes == []


@pytest.mark.asyncio
async def test_persisted_pending_action_survives_new_service_without_automatic_execution(voice_env):
    env = voice_env
    session, headers = await new_session(env, "morgan")
    pending = await env.service.call_tool(session.session_id, {"sub":"recruiter-a"}, "update_application_status",
                                        {"application_id":"application-a","status":"invited"})
    env.app.state.voice_assistants = VoiceAssistantService(env.db, env.redis, agora=env.agora)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://test") as client:
        status = await client.post("/api/v1/voice/mcp", headers=headers,
                                  json=rpc("tools/call", {"name":"get_action_status","arguments":{}}))
        assert pending["pending_action"]["confirmation_id"] in status.json()["result"]["content"][0]["text"]
        assert env.db.writes == []
        approved = await client.post(f"/api/v1/voice/sessions/{session.session_id}/confirm", headers=browser_headers("recruiter-a"),
            json={"confirmation_id":pending["pending_action"]["confirmation_id"], "approved":True})
        assert approved.status_code == 200 and approved.json()["status"] == "executing"
        await asyncio.gather(*list(env.app.state.voice_assistants._confirmation_tasks.values()))
        completed = await client.get(f"/api/v1/voice/sessions/{session.session_id}", headers=browser_headers("recruiter-a"))
        assert completed.status_code == 200
        assert completed.json()["last_tool_result"]["status"] == "succeeded"
    assert len(env.db.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [rpc("initialize", {"protocolVersion":[]}),
    {"jsonrpc":"2.0","id":{},"method":"tools/list"}, {"jsonrpc":"2.0","id":True,"method":"tools/list"},
    {"jsonrpc":"2.0","id":1,"method":"tools/call","params":["bad"]}])
async def test_malformed_mcp_requests_return_protocol_error_not_server_failure(voice_env, body):
    _, headers = await new_session(voice_env)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=voice_env.app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.post("/api/v1/voice/mcp", headers=headers, json=body)
    assert response.status_code == 200, response.text
    # Invalid protocol version may use the supported default or a JSON-RPC error.
    assert "error" in response.json() or response.json()["result"]["protocolVersion"] == "2025-03-26"
