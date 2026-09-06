"""Long-running confirmed work must not lock voice lifecycle requests."""
import asyncio
from datetime import timedelta

import pytest

from app.core.exceptions import ConflictError, ForbiddenError
from app.voice.models import DashboardContext, utc_now
from app.voice.service import VoiceAssistantService
from app.voice.store import VoiceSessionStore
from tests.test_voice_sessions import voice_env


async def propose(env):
    session = await env.service.start("morgan", {"sub": "recruiter-a"}, DashboardContext())
    proposal = await env.service.call_tool(session["session_id"], {"sub": "recruiter-a"},
        "update_application_status", {"application_id": "application-a", "status": "invited"})
    return session["session_id"], proposal["pending_action"]["confirmation_id"]


@pytest.mark.asyncio
async def test_second_write_keeps_first_review_visible_and_allows_read_tools(voice_env):
    env = voice_env
    sid, cid = await propose(env)
    original = (await env.service.store.get(sid)).pending_action
    with pytest.raises(ConflictError, match="Confirm or decline"):
        await env.service.call_tool(sid, {"sub": "recruiter-a"}, "update_application_status",
            {"application_id": "application-a", "status": "rejected"})
    assert (await env.service.get(sid, {"sub": "recruiter-a"}))["pending_action"] == original
    found = await env.service.call_tool(sid, {"sub": "recruiter-a"}, "search_candidates", {})
    assert found["status"] == "ok"
    assert (await env.service.store.get(sid)).pending_action["confirmation_id"] == cid
    assert len([key for key in env.redis.values if ":confirmation:" in key]) == 1
    assert env.db.writes == []


@pytest.mark.asyncio
async def test_concurrent_write_proposals_create_exactly_one_pending_review(voice_env):
    env = voice_env
    started = await env.service.start("morgan", {"sub": "recruiter-a"}, DashboardContext())
    sid = started["session_id"]
    results = await asyncio.gather(*[
        env.service.call_tool(sid, {"sub": "recruiter-a"}, "update_application_status",
            {"application_id": "application-a", "status": status})
        for status in ("invited", "rejected")], return_exceptions=True)
    accepted = [result for result in results if isinstance(result, dict)]
    assert len(accepted) == 1
    assert sum(isinstance(result, ConflictError) for result in results) == 1
    assert (await env.service.store.get(sid)).pending_action == accepted[0]["pending_action"]
    assert len([key for key in env.redis.values if ":confirmation:" in key]) == 1
    assert env.db.writes == []


@pytest.mark.asyncio
async def test_declining_current_review_allows_new_proposal(voice_env):
    env = voice_env
    sid, cid = await propose(env)
    declined = await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, False)
    assert declined["status"] == "declined"
    new = await env.service.call_tool(sid, {"sub": "recruiter-a"}, "update_application_status",
        {"application_id": "application-a", "status": "rejected"})
    assert new["pending_action"]["confirmation_id"] != cid
    assert (await env.service.store.get(sid)).pending_action == new["pending_action"]
    assert env.db.writes == []


@pytest.mark.asyncio
async def test_expired_durable_review_does_not_block_new_proposal(voice_env):
    env = voice_env
    sid, cid = await propose(env)
    record = await env.service.tools.pending_store.get(cid)
    record["expires_at"] = (utc_now() - timedelta(seconds=1)).isoformat()
    await env.service.tools.pending_store.put(cid, record, 60)
    new = await env.service.call_tool(sid, {"sub": "recruiter-a"}, "update_application_status",
        {"application_id": "application-a", "status": "rejected"})
    assert new["pending_action"]["confirmation_id"] != cid
    assert (await env.service.store.get(sid)).pending_action == new["pending_action"]
    with pytest.raises(ConflictError, match="not the current"):
        await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True)
    assert env.db.writes == []


@pytest.mark.asyncio
async def test_invalidated_review_receipt_replaces_stale_view_and_allows_new_proposal(voice_env):
    env = voice_env
    sid, cid = await propose(env)
    env.db.rows["candidates"][0]["name"] = "Updated review name"
    with pytest.raises(ConflictError, match="Details changed"):
        await env.service.tools.confirm(cid, user_claims={"sub": "recruiter-a"}, session_id=sid)
    new = await env.service.call_tool(sid, {"sub": "recruiter-a"}, "update_application_status",
        {"application_id": "application-a", "status": "invited"})
    view = await env.service.get(sid, {"sub": "recruiter-a"})
    assert view["pending_action"] == new["pending_action"]
    assert new["pending_action"]["confirmation_id"] != cid
    assert view["last_tool_result"]["code"] == "details_changed"
    assert view["last_tool_result"]["confirmation_id"] == cid
    assert env.db.writes == []


@pytest.mark.asyncio
async def test_slow_confirmation_keeps_get_heartbeat_and_replay_responsive(voice_env, monkeypatch):
    env = voice_env
    sid, cid = await propose(env)
    entered, release = asyncio.Event(), asyncio.Event()
    original = env.service.tools._execute
    calls = []
    async def slow(*args, **kwargs):
        calls.append(1)
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(env.service.tools, "_execute", slow)
    try:
        receipt = await asyncio.wait_for(env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True), .5)
        assert receipt["status"] == "executing"
        await asyncio.wait_for(entered.wait(), .5)
        visible = await asyncio.wait_for(env.service.get(sid, {"sub": "recruiter-a"}, heartbeat=True), .5)
        assert visible["status"] == "EXECUTING"
        assert visible["last_tool_result"]["confirmation_id"] == cid
        assert visible["pending_action"] is None
        replay = await asyncio.wait_for(env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True), .5)
        assert replay["status"] == "executing" and len(calls) == 1
        with pytest.raises(ConflictError):
            await env.service.call_tool(sid, {"sub": "recruiter-a"}, "update_application_status", {"application_id": "application-a", "status": "rejected"})
        release.set()
        await asyncio.gather(*list(env.service._confirmation_tasks.values()))
        final = await env.service.get(sid, {"sub": "recruiter-a"})
        assert final["status"] == "CONNECTED"
        assert final["last_tool_result"]["status"] == "succeeded"
        assert await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True) == final["last_tool_result"]
        assert len(calls) == 1
        assert await env.service.store.executing_ids() == []
    finally:
        await env.service.shutdown()


@pytest.mark.asyncio
async def test_result_survives_voice_end_and_does_not_reconnect_session(voice_env, monkeypatch):
    env = voice_env
    sid, cid = await propose(env)
    entered, release = asyncio.Event(), asyncio.Event()
    original = env.service.tools._execute
    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(env.service.tools, "_execute", slow)
    try:
        await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True)
        await entered.wait()
        ended = await asyncio.wait_for(env.service.end(sid, {"sub": "recruiter-a"}), .5)
        assert ended["status"] == "DISCONNECTED" and ended["last_tool_result"] is None
        running = await env.service.get(sid, {"sub": "recruiter-a"})
        assert running["status"] == "DISCONNECTED" and running["last_tool_result"]["status"] == "executing"
        release.set()
        await asyncio.gather(*list(env.service._confirmation_tasks.values()))
        final = await env.service.get(sid, {"sub": "recruiter-a"})
        assert final["status"] == "DISCONNECTED"
        assert final["last_tool_result"]["status"] == "succeeded"
        assert (await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True))["status"] == "succeeded"
        env.agora.announce_result.assert_not_awaited()
    finally:
        await env.service.shutdown()


@pytest.mark.asyncio
async def test_lost_worker_lease_yields_unknown_outcome_without_replay(voice_env, monkeypatch):
    env = voice_env
    sid, cid = await propose(env)
    entered = asyncio.Event()
    executions = []
    async def interrupted(*args, **kwargs):
        executions.append(1)
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(env.service.tools, "_execute", interrupted)
    await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True)
    await entered.wait()
    await env.service.shutdown()
    # Simulate the90-second Redis lease expiring after process disappearance.
    env.redis.values.pop(VoiceSessionStore.PREFIX + "execution:" + cid)
    replacement = VoiceAssistantService(env.db, env.redis, agora=env.agora)
    view = await replacement.get(sid, {"sub": "recruiter-a"})
    assert view["last_tool_result"]["status"] == "failed"
    assert view["last_tool_result"]["outcome_unknown"] is True
    assert (await replacement.confirm(sid, {"sub": "recruiter-a"}, cid, True))["outcome_unknown"] is True
    assert len(executions) == 1 and env.db.writes == []


@pytest.mark.asyncio
async def test_background_result_reads_recheck_resource_authorization(voice_env, monkeypatch):
    env = voice_env
    sid, cid = await propose(env)
    entered = asyncio.Event()
    async def blocked(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(env.service.tools, "_execute", blocked)
    try:
        await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True)
        await entered.wait()
        env.db.rows["jobs"][0]["created_by"] = "recruiter-b"
        with pytest.raises(ForbiddenError):
            await env.service.get(sid, {"sub": "recruiter-a"})
        ended = await env.service.end(sid, {"sub": "recruiter-a"})
        assert ended["last_tool_result"] is None
    finally:
        await env.service.shutdown()


@pytest.mark.asyncio
async def test_execution_lease_cannot_be_renewed_by_another_worker(voice_env):
    store = voice_env.service.store
    assert await store.begin_execution("session", "confirmation", "owner-a")
    assert not await store.begin_execution("session", "confirmation", "owner-b")
    assert not await store.renew_execution("confirmation", "owner-b")
    assert await store.renew_execution("confirmation", "owner-a")
    async with store.lock("execution:confirmation"):
        await store.finish_execution("session", "confirmation")
    assert not await store.renew_execution("confirmation", "owner-a")
    assert await store.executing_ids() == []


@pytest.mark.asyncio
async def test_get_can_read_acknowledged_action_before_tool_claim(voice_env, monkeypatch):
    env = voice_env
    sid, cid = await propose(env)
    started, release = asyncio.Event(), asyncio.Event()
    original = env.service.tools.confirm
    async def before_claim(*args, **kwargs):
        started.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(env.service.tools, "confirm", before_claim)
    try:
        await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True)
        await started.wait()
        visible = await asyncio.wait_for(env.service.get(sid, {"sub": "recruiter-a"}), .5)
        assert visible["last_tool_result"]["status"] == "executing"
        assert env.db.writes == []
        release.set()
        await asyncio.gather(*list(env.service._confirmation_tasks.values()))
        assert (await env.service.get(sid, {"sub": "recruiter-a"}))["last_tool_result"]["status"] == "succeeded"
    finally:
        await env.service.shutdown()


@pytest.mark.asyncio
async def test_changed_review_returns_stable_failed_receipt_without_mutation(voice_env):
    env = voice_env
    sid, cid = await propose(env)
    env.db.rows["candidates"][0]["name"] = "Changed after review"
    await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True)
    await asyncio.gather(*list(env.service._confirmation_tasks.values()))
    result = (await env.service.get(sid, {"sub": "recruiter-a"}))["last_tool_result"]
    assert result["status"] == "failed" and result["outcome_unknown"] is False
    assert result["code"] == "details_changed"
    assert await env.service.confirm(sid, {"sub": "recruiter-a"}, cid, True) == result
    assert env.db.writes == []
