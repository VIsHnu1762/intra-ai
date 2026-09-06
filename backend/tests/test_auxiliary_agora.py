"""Offline contract tests for the separate Studio voice project."""

import asyncio
import base64
from dataclasses import FrozenInstanceError
import hashlib
import hmac
import json
import struct
from types import SimpleNamespace
import zlib

import httpx
import pytest

from app.voice.agora import (
    AgoraProjectConfig, AgoraStudioAgentConfig, AuxiliaryAgoraError,
    TrainingHRAgoraService,
)


def project(**changes):
    values = dict(app_id="1" * 32, app_certificate="2" * 32,
        taylor=AgoraStudioAgentConfig("taylor", "taylor-studio-pipeline", "201"),
        morgan=AgoraStudioAgentConfig("morgan", "morgan-studio-pipeline", "202"))
    return AgoraProjectConfig(**{**values, **changes})


def decode_token(token):
    assert token.startswith("007")
    raw = zlib.decompress(base64.b64decode(token[3:]))
    offset = 0

    def number(fmt):
        nonlocal offset
        result = struct.unpack_from(fmt, raw, offset)[0]
        offset += struct.calcsize(fmt)
        return result

    def string():
        nonlocal offset
        count = number("<H")
        value = raw[offset:offset + count]
        offset += count
        return value

    signature = string()
    signing_info = raw[offset:]
    app_id = string().decode()
    issued, expiry, salt = number("<I"), number("<I"), number("<I")
    services = {}
    for _ in range(number("<H")):
        kind = number("<H")
        privileges = {}
        for _ in range(number("<H")):
            key, value = number("<H"), number("<I")
            privileges[key] = value
        service = {"privileges": privileges}
        if kind == 1:
            service["channel"] = string().decode()
        service["uid"] = string().decode()
        services[kind] = service
    assert offset == len(raw)
    key = hmac.new(struct.pack("<I", issued), ("2" * 32).encode(), hashlib.sha256).digest()
    key = hmac.new(struct.pack("<I", salt), key, hashlib.sha256).digest()
    assert hmac.compare_digest(signature, hmac.new(key, signing_info, hashlib.sha256).digest())
    return {"app_id": app_id, "expiry": expiry, "services": services}


def test_project_is_immutable_and_repr_hides_server_secrets():
    config = project(api_token="Basic c2VydmVyOm9ubHk=")
    assert config.app_certificate not in repr(config)
    assert config.api_token not in repr(config)
    with pytest.raises(FrozenInstanceError):
        config.app_id = "3" * 32
    with pytest.raises(FrozenInstanceError):
        config.taylor.agent_rtc_uid = "999"


@pytest.mark.parametrize("changes", [{"app_id": None}, {"app_certificate": "invalid-secret"},
    {"api_token": "Bearer unsupported-secret"}, {"api_token": "Basic token\r\nX:injected"},
    {"morgan": AgoraStudioAgentConfig("morgan", "morgan-pipeline", "201")}])
def test_invalid_project_configuration_is_typed_and_sanitized(changes):
    with pytest.raises(AuxiliaryAgoraError) as error:
        project(**changes)
    assert error.value.code == "VOICE_CONFIGURATION_ERROR"
    assert "secret" not in str(error.value)


def test_settings_only_read_auxiliary_project_never_official_defaults():
    old = SimpleNamespace(AGORA_APP_ID="a" * 32, AGORA_APP_CERTIFICATE="b" * 32,
                          AGORA_CUSTOMER_ID="official", AGORA_CUSTOMER_SECRET="official-secret")
    with pytest.raises(AuxiliaryAgoraError) as error:
        AgoraProjectConfig.from_settings(old)
    assert error.value.code == "VOICE_CONFIGURATION_ERROR"
    old.AGORA_TRAINING_HR_APP_ID = "1" * 32
    old.AGORA_TRAINING_HR_APP_CERTIFICATE = "2" * 32
    old.AGORA_TAYLOR_AGENT_ID = "taylor-studio-pipeline"
    old.AGORA_TAYLOR_AGENT_RTC_UID = "201"
    old.AGORA_MORGAN_AGENT_ID = "morgan-studio-pipeline"
    old.AGORA_MORGAN_AGENT_RTC_UID = "202"
    assert AgoraProjectConfig.from_settings(old) == project()
    old.AGORA_MORGAN_LLM_MODE = "managed"
    old.AGORA_MORGAN_MANAGED_MODEL = "gpt-4.1-mini"
    assert AgoraProjectConfig.from_settings(old) == project(morgan_llm_mode="managed")


def test_managed_morgan_replaces_inherited_params_before_start_returns_and_preserves_session_settings():
    async def run():
        calls = []
        update_started, allow_update = asyncio.Event(), asyncio.Event()
        effective_params = {"auth_jwt": "saved-proxy-secret", "agent_uuid": "saved-proxy-id"}

        async def handler(request):
            payload = json.loads(request.content)
            calls.append((request, payload))
            if request.url.path.endswith("/join"):
                # Reproduce the observed merge of incompatible saved proxy fields.
                effective_params.update(payload["properties"]["llm"]["params"])
            else:
                assert request.url.path.endswith("/agents/cloud-managed/update")
                update_started.set()
                await allow_update.wait()
                effective_params.clear()
                effective_params.update(payload["properties"]["llm"]["params"])
            return httpx.Response(200, json={"agent_id": "cloud-managed", "status": "RUNNING",
                                             "api_key": "must-not-return"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = TrainingHRAgoraService(project(morgan_llm_mode="managed"), client)
            task = asyncio.create_task(service.start_agent("morgan", "managed-session", 711, "managed-name",
                system_prompt="Only use authorized recruiter data.", greeting_message="Hi Ada, how can I help?",
                mcp_endpoint="https://example.test/api/v1/voice/mcp", mcp_authorization="Bearer scoped.session.token",
                allowed_tools=["search_candidates", "list_jobs"]))
            await asyncio.wait_for(update_started.wait(), timeout=1)
            assert not task.done(), "Start must await params replacement before returning a session"
            allow_update.set()
            result = await task
        assert len(calls) == 2
        join, update = calls[0][1], calls[1][1]
        assert [request.method for request, _ in calls] == ["POST", "POST"]
        assert join["pipeline_id"] == "morgan-studio-pipeline"
        properties = join["properties"]
        assert not {"asr", "tts", "mllm"} & set(properties)
        assert properties["channel"] == "managed-session" and properties["remote_rtc_uids"] == ["711"]
        assert properties["advanced_features"] == {"enable_rtm": True, "enable_tools": True}
        llm = properties["llm"]
        assert {key: llm[key] for key in ("credential_mode", "vendor", "style", "url", "params", "max_history")} == {
            "credential_mode": "managed", "vendor": "openai", "style": "openai",
            "url": "https://api.openai.com/v1/chat/completions", "params": {"model": "gpt-4.1-mini"}, "max_history": 32}
        assert llm["system_messages"] == [{"role": "system", "content": "Only use authorized recruiter data."}]
        assert llm["greeting_message"] == "Hi Ada, how can I help?"
        assert llm["greeting_configs"] == {"mode": "single_first"}
        assert llm["mcp_servers"][0]["allowed_tools"] == ["search_candidates", "list_jobs"]
        assert llm["mcp_servers"][0]["headers"] == {"Authorization": "Bearer scoped.session.token"}
        assert "api_key" not in llm
        assert update == {"properties": {"llm": {"params": {"model": "gpt-4.1-mini"}}}}
        assert effective_params == {"model": "gpt-4.1-mini"}
        assert result == {"agent_id": "cloud-managed", "channel": "managed-session", "status": "RUNNING"}
    asyncio.run(run())


@pytest.mark.parametrize("failure", ["http", "timeout", "wrong_agent", "wrong_channel", "invalid_json", "cancelled"])
def test_managed_morgan_update_failure_stops_only_new_agent_and_propagates(failure):
    async def run():
        calls = []
        def handler(request):
            calls.append(request.url.path.rsplit("/", 1)[-1])
            if calls[-1] == "join":
                return httpx.Response(200, json={"agent_id": "cloud-new", "status": "RUNNING"})
            if calls[-1] == "leave":
                assert request.url.path.endswith("/agents/cloud-new/leave")
                return httpx.Response(204)
            assert request.url.path.endswith("/agents/cloud-new/update")
            if failure == "http":
                return httpx.Response(400, json={"error": "private-provider-secret"})
            if failure == "timeout":
                raise httpx.ReadTimeout("private-provider-secret")
            if failure == "cancelled":
                raise asyncio.CancelledError()
            if failure == "invalid_json":
                return httpx.Response(200, text="private-provider-secret")
            return httpx.Response(200, json={"agent_id": "someone-else" if failure == "wrong_agent" else "cloud-new",
                "channel": "wrong-session" if failure == "wrong_channel" else "managed-session", "status": "RUNNING"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(asyncio.CancelledError if failure == "cancelled" else AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(morgan_llm_mode="managed"), client).start_agent(
                    "morgan", "managed-session", 711, "managed-name")
        assert calls == ["join", "update", "leave"]
        assert "private-provider-secret" not in str(error.value)
    asyncio.run(run())


def test_managed_morgan_cleanup_failure_does_not_hide_original_setup_error(caplog):
    async def run():
        calls = []
        def handler(request):
            calls.append(request.url.path.rsplit("/", 1)[-1])
            if calls[-1] == "join":
                return httpx.Response(200, json={"agent_id": "cloud-new", "status": "RUNNING"})
            return httpx.Response(429 if calls[-1] == "update" else 500, json={"secret": "private-upstream-content"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(morgan_llm_mode="managed"), client).start_agent(
                    "morgan", "managed-session", 711, "managed-name")
        assert calls == ["join", "update", "leave"]
        assert error.value.code == "VOICE_PROVIDER_LIMIT"
        assert "morgan_managed_start_cleanup_pending" in caplog.text
        assert "private-upstream-content" not in caplog.text
    asyncio.run(run())


def test_managed_morgan_setting_never_changes_taylor_llm_or_startup_calls():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"agent_id": "cloud-taylor", "status": "RUNNING"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await TrainingHRAgoraService(project(morgan_llm_mode="managed"), client).start_agent(
                "taylor", "practice-session", 711, "practice-name", system_prompt="Practice context.")
        assert len(calls) == 1 and calls[0].url.path.endswith("/join")
        payload = json.loads(calls[0].content)
        assert payload["pipeline_id"] == "taylor-studio-pipeline"
        assert payload["properties"]["llm"] == {
            "system_messages": [{"role": "system", "content": "Practice context."}], "mcp_servers": []}
        assert not {"asr", "tts", "mllm"} & set(payload["properties"])
    asyncio.run(run())


@pytest.mark.parametrize("changes", [{"morgan_llm_mode": "custom"}, {"morgan_llm_mode": []},
    {"morgan_managed_model": "unknown-model"}, {"morgan_managed_model": None}])
def test_managed_morgan_invalid_configuration_rejected_before_dispatch(changes):
    with pytest.raises(AuxiliaryAgoraError) as error:
        project(**changes)
    assert error.value.code == "VOICE_CONFIGURATION_ERROR"


def test_candidate_tokens_are_separate_uid_bound_and_signed_by_new_project():
    service = TrainingHRAgoraService(project())
    credentials = service.candidate_credentials("training-isolated-session", 711, expires_in=900)
    rtc, rtm = decode_token(credentials["rtc_token"]), decode_token(credentials["rtm_token"])
    assert rtc["app_id"] == rtm["app_id"] == "1" * 32
    assert rtc["expiry"] == rtm["expiry"] == 900
    assert rtc["services"] == {1: {"uid": "711", "channel": "training-isolated-session",
                                   "privileges": {1: 900, 2: 900, 3: 900, 4: 900}}}
    assert rtm["services"] == {2: {"uid": "711", "privileges": {1: 900}}}
    assert set(credentials) == {"app_id", "channel", "uid", "rtc_token", "rtm_token", "expires_at"}
    assert credentials["rtc_token"] != credentials["rtm_token"]
    assert "2" * 32 not in json.dumps(credentials)


@pytest.mark.parametrize("uid", [0, -1, True, 4294967296, "../11", "201", "202"])
def test_invalid_or_colliding_candidate_uid_rejected(uid):
    with pytest.raises(AuxiliaryAgoraError):
        TrainingHRAgoraService(project()).candidate_credentials("session", uid)


def test_conversational_ai_max_uid_is_accepted_in_tokens_and_join_payload():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"agent_id":"cloud-max-uid", "status":"RUNNING"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = TrainingHRAgoraService(project(), client)
            credentials = service.candidate_credentials("max-uid-session", 2147483647)
            assert decode_token(credentials["rtc_token"])["services"][1]["uid"] == "2147483647"
            assert decode_token(credentials["rtm_token"])["services"][2]["uid"] == "2147483647"
            await service.start_agent("taylor", "max-uid-session", 2147483647, "max-uid-name")
        assert json.loads(calls[0].content)["properties"]["remote_rtc_uids"] == ["2147483647"]
    asyncio.run(run())


def test_uid_above_conversational_ai_cap_rejected_before_tokens_or_dispatch():
    async def run():
        def handler(request):
            pytest.fail("A UID above the provider cap must never be dispatched")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = TrainingHRAgoraService(project(), client)
            with pytest.raises(AuxiliaryAgoraError) as credentials_error:
                service.candidate_credentials("overflow-uid-session", 2147483648)
            assert credentials_error.value.code == "VOICE_INVALID_UID"
            with pytest.raises(AuxiliaryAgoraError) as join_error:
                await service.start_agent("taylor", "overflow-uid-session", 2147483648, "overflow-uid-name")
            assert join_error.value.code == "VOICE_INVALID_UID"
    asyncio.run(run())


@pytest.mark.parametrize("expiry", [0, 1801, -1, True, 1.5])
def test_token_expiry_cannot_exceed_thirty_minutes(expiry):
    with pytest.raises(AuxiliaryAgoraError):
        TrainingHRAgoraService(project()).candidate_credentials("session", 711, expires_in=expiry)


def test_studio_join_preserves_providers_and_dynamic_agent_auth():
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"agent_id": "cloud-taylor", "status": "RUNNING",
                "token": "do-not-return", "properties": {"secret": "do-not-return"}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            # The stale Studio embed's token is never used for a new channel.
            service = TrainingHRAgoraService(project(api_token="agora token=007oldtoken"), client)
            result = await service.start_agent("taylor", "training-new-session", 711, "unique-session")
            assert not client.is_closed
        payload = json.loads(calls[0].content)
        assert str(calls[0].url) == "https://api.agora.io/api/conversational-ai-agent/v2/projects/" + "1" * 32 + "/join"
        assert payload["pipeline_id"] == "taylor-studio-pipeline"
        properties = payload["properties"]
        assert not {"asr", "tts", "mllm"} & set(properties)
        assert properties["llm"] == {"mcp_servers": []}
        assert properties["advanced_features"]["enable_tools"] is False
        assert properties["remote_rtc_uids"] == ["711"]
        assert properties["agent_rtc_uid"] == "201"
        decoded = decode_token(properties["token"])
        assert decoded["services"][1]["channel"] == "training-new-session"
        assert decoded["services"][1]["uid"] == decoded["services"][2]["uid"] == "201"
        assert calls[0].headers["authorization"] == "agora token=" + properties["token"]
        assert "oldtoken" not in calls[0].headers["authorization"]
        assert result == {"agent_id": "cloud-taylor", "channel": "training-new-session", "status": "RUNNING"}
    asyncio.run(run())


def test_explicit_project_basic_auth_is_preserved_without_legacy_fallback():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"agent_id": "cloud-morgan", "status": "RUNNING"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await TrainingHRAgoraService(project(api_token="Basic c2VydmVyOm9ubHk="), client).start_agent(
                "morgan", "hr-new-session", 711, "hr-name")
        assert calls[0].headers["authorization"] == "Basic c2VydmVyOm9ubHk="
        payload = json.loads(calls[0].content)
        assert "llm" not in payload["properties"]
        assert "enable_tools" not in payload["properties"]["advanced_features"]
        decoded = decode_token(payload["properties"]["token"])
        assert decoded["services"][1]["uid"] == decoded["services"][2]["uid"] == "202"
        assert "Basic" not in json.dumps(result)
    asyncio.run(run())


def test_taylor_greeting_uses_studio_voice_and_is_not_replayed_on_rejoin():
    async def run():
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"agent_id": "cloud-taylor", "status": "RUNNING"})
        greeting = "Hi Ada, I'm Taylor. Let's practise for Frontend Intern. What small project have you worked on?"
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await TrainingHRAgoraService(project(), client).start_agent("taylor", "practice-session", 711, "practice-name",
                system_prompt="Preloaded practice context: Ada's CV describes a Python project.", greeting_message=greeting)
        assert calls[0]["pipeline_id"] == "taylor-studio-pipeline"
        properties = calls[0]["properties"]
        assert not {"asr", "tts", "mllm"} & set(properties)
        assert properties["advanced_features"]["enable_tools"] is False
        assert properties["llm"] == {
            "system_messages": [{"role": "system", "content": "Preloaded practice context: Ada's CV describes a Python project."}],
            "greeting_message": greeting, "greeting_configs": {"mode": "single_first"}, "mcp_servers": []}
        assert "api_key" not in properties["llm"] and "params" not in properties["llm"]
    asyncio.run(run())


@pytest.mark.parametrize("greeting", ["", "  ", 123, "a" * 1025, "é" * 513, "\ud800"])
def test_invalid_greeting_is_rejected_before_provider_dispatch(greeting):
    async def run():
        def handler(request):
            pytest.fail("Invalid greeting must not make a provider call")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).start_agent("taylor", "session", 711, "name", greeting_message=greeting)
        assert error.value.code == "VOICE_INVALID_GREETING" and error.value.http_status == 400
    asyncio.run(run())


def test_context_and_mcp_override_only_session_fields_with_scoped_header():
    async def run():
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"agent_id": "cloud-morgan", "status": "RUNNING"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await TrainingHRAgoraService(project(), client).start_agent("morgan", "hr-session", 711, "hr-session-name",
                system_prompt="Only propose changes. UI confirmation is required.",
                mcp_endpoint="https://example.test/api/v1/voice/mcp", mcp_authorization="Bearer session.jwt.value",
                allowed_tools=["get_dashboard_context", "get_action_status", "propose_job"])
        properties = calls[0]["properties"]
        assert calls[0]["pipeline_id"] == "morgan-studio-pipeline"
        assert properties["advanced_features"] == {"enable_rtm": True, "enable_tools": True}
        assert set(properties["llm"]) == {"system_messages", "mcp_servers"}
        server = properties["llm"]["mcp_servers"][0]
        assert server["headers"] == {"Authorization": "Bearer session.jwt.value"}
        assert server["transport"] == "streamable_http"
        assert server["allowed_tools"] == ["get_dashboard_context", "get_action_status", "propose_job"]
        assert "session.jwt.value" not in server["endpoint"]
        assert not {"asr", "tts", "mllm"} & set(properties)
    asyncio.run(run())


@pytest.mark.parametrize("endpoint,authorization,tools", [
    ("http://example.test/mcp", "Bearer token", ["get_training_context"]),
    ("https://example.test/mcp?token=secret", "Bearer token", ["get_training_context"]),
    ("https://user:password@example.test/mcp", "Bearer token", ["get_training_context"]),
    ("https://example.test/mcp", "Bearer token\r\nX:secret", ["get_training_context"]),
    ("https://example.test/mcp", "Bearer token", ["*"]),
    ("https://example.test/mcp", "Bearer token", []),
    ("https://example.test:invalid/mcp", "Bearer token", ["get_training_context"]),
])
def test_invalid_mcp_never_dispatches(endpoint, authorization, tools):
    async def run():
        def handler(request):
            pytest.fail("Invalid MCP config must not make a provider call")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).start_agent("morgan", "session", 711, "name",
                    mcp_endpoint=endpoint, mcp_authorization=authorization, allowed_tools=tools)
            assert error.value.code == "VOICE_INVALID_MCP"
    asyncio.run(run())


@pytest.mark.parametrize("options", [
    {"mcp_endpoint": "https://example.test/mcp", "mcp_authorization": "Bearer session.jwt.value", "allowed_tools": ["get_training_context"]},
    {"mcp_endpoint": "https://example.test/mcp", "mcp_authorization": "Bearer session.jwt.value", "allowed_tools": ["schedule_interview"]},
    {"mcp_endpoint": "https://example.test/mcp"},
    {"mcp_authorization": "Bearer session.jwt.value"},
    {"allowed_tools": ["get_training_context"]},
])
def test_taylor_rejects_all_explicit_mcp_configuration_including_legacy_read_tool(options):
    async def run():
        def handler(request):
            pytest.fail("Taylor must never start with an MCP configuration")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).start_agent("taylor", "session", 711, "name", **options)
        assert error.value.code == "VOICE_INVALID_MCP"
        assert "session.jwt.value" not in str(error.value)
    asyncio.run(run())


@pytest.mark.parametrize("status,code,mapped", [(401,"VOICE_PROVIDER_AUTHENTICATION",503),
    (403,"VOICE_PROVIDER_FORBIDDEN",503),(404,"VOICE_AGENT_NOT_FOUND",404),
    (429,"VOICE_PROVIDER_LIMIT",503),(500,"VOICE_PROVIDER_ERROR",502),(302,"VOICE_PROVIDER_ERROR",502)])
def test_provider_errors_are_typed_and_never_leak_body_or_credentials(status, code, mapped):
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(status, json={"message": "provider-secret-value", "token": "private-token"},
                                  headers={"Location": "https://untrusted.example/collect"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).query_agent("morgan", "hr-room", "cloud-id")
            assert error.value.code == code
            assert error.value.http_status == mapped
            assert error.value.provider_status == status
            assert "secret" not in str(error.value) + repr(vars(error.value))
            assert "private-token" not in repr(vars(error.value))
            assert len(calls) == 1  # Never forward Authorization on redirects.
    asyncio.run(run())


def test_provider_timeout_is_safe_and_owned_client_remains_open():
    async def run():
        def handler(request):
            raise httpx.ReadTimeout("secret request details", request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).query_agent("taylor", "training-room", "cloud-id")
            assert error.value.code == "VOICE_PROVIDER_TIMEOUT"
            assert error.value.http_status == 504
            assert "secret" not in str(error.value)
            assert not client.is_closed
    asyncio.run(run())


def test_stop_missing_agent_is_idempotent_and_speak_uses_studio_tts():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(404 if request.url.path.endswith("/leave") else 200)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = TrainingHRAgoraService(project(), client)
            stopped = await service.stop_agent("morgan", "hr-room", "cloud-id")
            spoken = await service.announce_result("morgan", "hr-room", "cloud-id", "The draft job was saved.")
        assert stopped["status"] == "STOPPED"
        assert spoken["status"] == "ANNOUNCEMENT_ACCEPTED"
        assert calls[0].url.path.endswith("/agents/cloud-id/leave")
        assert calls[1].url.path.endswith("/agents/cloud-id/speak")
        assert json.loads(calls[1].content) == {"text": "The draft job was saved.", "priority": "APPEND", "interruptable": True}
    asyncio.run(run())


def test_announcement_limit_counts_utf8_bytes_before_dispatch():
    async def run():
        def handler(request):
            pytest.fail("Oversized text must not be sent")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).announce_result("morgan", "hr-room", "cloud-id", "好" * 171)
            assert error.value.code == "VOICE_INVALID_ANNOUNCEMENT"
    asyncio.run(run())


@pytest.mark.parametrize("result", [{"agent_id": "wrong-id", "status": "RUNNING"},
    {"agent_id": "cloud-id", "channel": "other-room", "status": "RUNNING"}])
def test_query_does_not_accept_mismatched_cloud_session(result):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=result))) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).query_agent("taylor", "training-room", "cloud-id")
            assert error.value.code == "VOICE_SESSION_MISMATCH"
    asyncio.run(run())


def test_taylor_without_mcp_clears_inherited_tools_but_preserves_studio_model():
    async def run():
        calls = []
        def handler(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"agent_id": "cloud-taylor", "status": "RUNNING"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await TrainingHRAgoraService(project(), client).start_agent("taylor", "practice-room", 711, "practice-name",
                system_prompt="Candidate CV context is loaded once. Practice only.")
        properties = calls[0]["properties"]
        assert properties["advanced_features"]["enable_tools"] is False
        assert properties["llm"] == {"system_messages": [{"role": "system", "content": "Candidate CV context is loaded once. Practice only."}], "mcp_servers": []}
        assert not {"asr", "tts", "mllm"}.intersection(properties)
        assert not {"url", "api_key", "params", "vendor", "model"}.intersection(properties["llm"])
    asyncio.run(run())


def test_native_feedback_uses_same_taylor_agent_and_returns_acceptance_only():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"agent_id": "cloud-taylor", "channel": "practice-room", "start_ts": 1,
                "token": "private-provider-value", "feedback": "not-a-generated-result"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await TrainingHRAgoraService(project(), client).request_practice_feedback("taylor", "practice-room", "cloud-taylor",
                text="Finish practice and return feedback for marker qa-feedback.", request_id="6e05296b-a5b5-43cb-a8d7-3556d5b27061")
        request = calls[0]
        assert request.method == "POST"
        assert request.url.path == "/api/conversational-ai-agent/v2/projects/" + "1" * 32 + "/agents/cloud-taylor/think"
        payload = json.loads(request.content)
        assert payload == {"text": "Finish practice and return feedback for marker qa-feedback.",
            "on_listening_action": "interrupt", "on_thinking_action": "interrupt", "on_speaking_action": "interrupt",
            "interruptable": False, "metadata": {"request_id": "6e05296b-a5b5-43cb-a8d7-3556d5b27061"}}
        token = decode_token(request.headers["authorization"].removeprefix("agora token="))
        assert token["services"][1]["channel"] == "practice-room"
        assert token["services"][1]["uid"] == "201"
        assert result == {"agent_id": "cloud-taylor", "channel": "practice-room", "status": "FEEDBACK_REQUEST_ACCEPTED", "request_id": "6e05296b-a5b5-43cb-a8d7-3556d5b27061"}
        assert "private-provider-value" not in str(result)
    asyncio.run(run())


@pytest.mark.parametrize("text,request_id", [("", "6e05296b-a5b5-43cb-a8d7-3556d5b27061"), ("好" * 2731, "6e05296b-a5b5-43cb-a8d7-3556d5b27061"), ("finish", "not-a-uuid"), ("finish", "../../other")])
def test_invalid_native_feedback_request_never_dispatches(text, request_id):
    async def run():
        def handler(request):
            pytest.fail("Invalid feedback must not reach a provider")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).request_practice_feedback("taylor", "practice-room", "cloud-taylor", text=text, request_id=request_id)
            assert error.value.code == "VOICE_INVALID_FEEDBACK_REQUEST"
    asyncio.run(run())


@pytest.mark.parametrize("method", ["request_practice_feedback", "get_history"])
@pytest.mark.parametrize("persona", ["morgan", "alex", "jordan"])
def test_practice_apis_never_operate_on_other_personas(method, persona):
    async def run():
        def handler(request):
            pytest.fail("Practice APIs must not target another persona")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = TrainingHRAgoraService(project(), client)
            kwargs = {"text": "finish", "request_id": "6e05296b-a5b5-43cb-a8d7-3556d5b27061"} if method == "request_practice_feedback" else {}
            with pytest.raises(AuxiliaryAgoraError) as error:
                await getattr(service, method)(persona, "practice-room", "cloud-taylor", **kwargs)
            assert error.value.code == "VOICE_INVALID_AGENT"
    asyncio.run(run())


def test_history_returns_only_correlated_bounded_user_and_assistant_text():
    async def run():
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"agent_id": "cloud-taylor", "status": "RUNNING", "secret": "discard-me",
                "contents": [{"role": "user", "content": "My answer.", "token": "discard-me"},
                    {"role": "assistant", "content": '{"practice_score":70}', "properties": {"secret": "discard-me"}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await TrainingHRAgoraService(project(), client).get_history("taylor", "practice-room", "cloud-taylor")
        assert calls[0].method == "GET" and calls[0].url.path.endswith("/agents/cloud-taylor/history")
        assert result == {"agent_id": "cloud-taylor", "channel": "practice-room", "status": "RUNNING",
            "contents": [{"role": "user", "content": "My answer."}, {"role": "assistant", "content": '{"practice_score":70}'}], "truncated": False}
        assert "discard-me" not in str(result)
    asyncio.run(run())


@pytest.mark.parametrize("response", [{"agent_id": "other-agent", "contents": []}, {"channel": "other-room", "contents": []}])
@pytest.mark.parametrize("method", ["request_practice_feedback", "get_history"])
def test_practice_apis_reject_provider_session_mismatch(response, method):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(200, json=response))) as client:
            kwargs = {"text": "finish", "request_id": "6e05296b-a5b5-43cb-a8d7-3556d5b27061"} if method == "request_practice_feedback" else {}
            with pytest.raises(AuxiliaryAgoraError) as error:
                await getattr(TrainingHRAgoraService(project(), client), method)("taylor", "practice-room", "cloud-taylor", **kwargs)
            assert error.value.code == "VOICE_SESSION_MISMATCH"
    asyncio.run(run())


@pytest.mark.parametrize("contents", [{}, ["invalid"], [{"role": "assistant", "content": [{"type": "text", "text": "unsupported schema"}]}]])
def test_invalid_history_contract_fails_safely(contents):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={"agent_id": "cloud-taylor", "contents": contents}))) as client:
            with pytest.raises(AuxiliaryAgoraError) as error:
                await TrainingHRAgoraService(project(), client).get_history("taylor", "practice-room", "cloud-taylor")
            assert error.value.code == "VOICE_INVALID_HISTORY"
    asyncio.run(run())


def test_history_keeps_latest_feedback_with_explicit_truncation():
    async def run():
        contents = [{"role": "user", "content": "x" * 40000} for _ in range(140)] + [
            {"role": "user", "content": "feedback-request-marker"},
            {"role": "assistant", "content": '{"practice_score":70}'}]
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={"agent_id": "cloud-taylor", "contents": contents}))) as client:
            result = await TrainingHRAgoraService(project(), client).get_history("taylor", "practice-room", "cloud-taylor")
        assert result["truncated"] is True
        assert result["contents"][-2:] == contents[-2:]
        assert sum(len(item["content"]) for item in result["contents"]) <= 131072
        assert all(set(item) == {"role", "content"} for item in result["contents"])
    asyncio.run(run())
