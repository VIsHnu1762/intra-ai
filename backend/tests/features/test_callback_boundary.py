from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from app.core.custom_llm_boundary import CustomLLMCredentialBoundary
from app.core.middleware import RequestIDMiddleware


def application(key):
    app = FastAPI()
    app.add_middleware(CustomLLMCredentialBoundary, key=key)
    app.add_middleware(RequestIDMiddleware)

    @app.post("/api/v1/chat/completions")
    @app.post("/v1/chat/completions")
    async def completion():
        async def events():
            yield 'data: {"choices":[]}\n\n'
            yield 'data: [DONE]\n\n'
        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "healthy"}
    return app


def test_callbacks_fail_closed_for_both_aliases_without_or_with_wrong_key():
    client = TestClient(application("test-callback-key"))
    for path in ("/api/v1/chat/completions", "/v1/chat/completions"):
        for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic test-callback-key"}):
            response = client.post(path, headers=headers, json={"messages": []})
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == "Bearer"
        assert TestClient(application("")).post(path, json={}).status_code == 503


def test_valid_callback_keeps_streaming_contract_and_liveness_is_independent():
    client = TestClient(application("test-callback-key"))
    for path in ("/api/v1/chat/completions", "/v1/chat/completions"):
        response = client.post(path, headers={"Authorization": "Bearer test-callback-key"}, json={})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.text.endswith("data: [DONE]\n\n")
    assert TestClient(application("")).get("/api/v1/health").status_code == 200


def test_untrusted_request_id_is_replaced_with_bounded_uuid():
    client = TestClient(application("test-key"))
    response = client.get("/api/v1/health", headers={"X-Request-ID": "untrusted-data-" * 100})
    assert str(UUID(response.headers["X-Request-ID"])) == response.headers["X-Request-ID"]
