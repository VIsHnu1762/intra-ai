import hashlib
import hmac
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.core.deps import get_supabase
from app.integrations import standard_http_boundary as boundary
from app.services.workspace_access import current_actor
from app.voice.authorization import Actor


def app_for(module, name, path, method="POST"):
    app = FastAPI()
    async def endpoint(request: Request):
        return {"ok": True, "body": (await request.body()).decode("utf-8")}
    endpoint.__module__, endpoint.__name__ = module, name
    app.add_api_route(path, endpoint, methods=[method])
    boundary.install_standard_http_boundaries(app)
    boundary.install_standard_http_boundaries(app)
    return app


def test_session_resource_guard_uses_persisted_identity_and_existing_authorization(monkeypatch):
    calls = []
    async def authorize(actor, key, sb):
        calls.append((actor.user_id, key))
        if key != "owned": raise HTTPException(403, "Not your interview")
        return {"id": key}
    monkeypatch.setattr(boundary, "require_interview", authorize)
    app = app_for("app.routes.sessions", "start_session", "/api/v1/sessions/{interview_id}/start")
    app.dependency_overrides[current_actor] = lambda: Actor("user", "candidate", "c@test", "Candidate")
    app.dependency_overrides[get_supabase] = lambda: object()
    with TestClient(app) as client:
        assert client.post("/api/v1/sessions/owned/start").status_code == 200
        assert client.post("/api/v1/sessions/other/start").status_code == 403
    assert calls == [("user", "owned"), ("user", "other")]


@pytest.mark.parametrize("name", ["get_agora_rtc_token", "get_agora_agent_config", "start_agora_agent", "stop_agora_agent"])
def test_legacy_agent_configuration_and_credentials_cannot_be_exposed(name):
    with TestClient(app_for("app.routes.interviews", name, "/legacy")) as client:
        response = client.post("/legacy")
        assert response.status_code == 410
        assert "authenticated" in response.json()["detail"]


def test_arbitrary_browser_session_creation_is_retired():
    with TestClient(app_for("app.routes.sessions", "create_session", "/api/v1/sessions")) as client:
        assert client.post("/api/v1/sessions", json={"candidate_id": "other"}).status_code == 410


@pytest.mark.parametrize("name", ["agora_webhook_global", "agora_webhook_interview"])
def test_notification_verifies_raw_bytes_and_preserves_them(monkeypatch, name):
    monkeypatch.setattr(boundary, "settings", SimpleNamespace(AGORA_NOTIFICATION_SECRET="notification-test-secret"))
    raw = b'{ "event": "transcript", "text": "hello" }'
    signature = hmac.new(b"notification-test-secret", raw, hashlib.sha256).hexdigest()
    with TestClient(app_for("app.routes.interviews", name, "/webhook")) as client:
        assert client.post("/webhook", content=raw).status_code == 401
        headers = {"Agora-Signature-V2": signature}
        response = client.post("/webhook", content=raw, headers=headers)
        assert response.status_code == 200
        assert response.json()["body"] == raw.decode()
        assert client.post("/webhook", content=raw + b" ", headers=headers).status_code == 401
        assert client.post("/webhook", content=b"x" * (boundary.MAX_NOTIFICATION_BYTES + 1), headers=headers).status_code == 413


def test_missing_notification_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(boundary, "settings", SimpleNamespace(AGORA_NOTIFICATION_SECRET=""))
    with TestClient(app_for("app.routes.interviews", "agora_webhook_global", "/webhook")) as client:
        assert client.post("/webhook", json={}).status_code == 503


def test_transcript_read_requires_identity():
    app = app_for("app.routes.interviews", "get_interview_transcript", "/api/v1/interviews/{interview_id}/transcript", "GET")
    app.dependency_overrides[get_supabase] = lambda: object()
    with TestClient(app) as client:
        assert client.get("/api/v1/interviews/other/transcript").status_code in {401, 403}
