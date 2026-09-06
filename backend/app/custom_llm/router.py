"""FastAPI router exposing OpenAI-compatible endpoints for Agora Custom LLM integration."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.custom_llm.adapter import custom_llm_adapter
from app.custom_llm.models import ChatCompletionRequest, ChatCompletionResponse

router = APIRouter(tags=["Custom LLM"])
logger = structlog.stdlib.get_logger("intra_ai.custom_llm.router")


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    status_code=status.HTTP_200_OK,
    summary="OpenAI-compatible Chat Completions endpoint for Agora Agent Studio",
)
async def chat_completions(
    request: ChatCompletionRequest,
    raw_request: Request,
):
    """Serve OpenAI-compatible chat completions to Agora Agent Studio or direct clients.

    When `stream=true` (default for Agora voice pipeline), streams Server-Sent Events (SSE).
    When `stream=false`, returns a standard ChatCompletionResponse JSON payload.
    """
    raw_headers = {k.lower(): v for k, v in raw_request.headers.items()}
    query_params = dict(raw_request.query_params)

    # Merge query params into headers so adapter can read session_id and agent_id
    # from either source. Query params take precedence over headers.
    merged_headers = dict(raw_request.headers)
    if "session_id" in query_params:
        merged_headers["x-session-id"] = query_params["session_id"]
    if "agent_id" in query_params:
        merged_headers["x-agent-id"] = query_params["agent_id"]

    turn = custom_llm_adapter.parse_turn(request, headers=merged_headers)

    # Record identity and credential presence, never raw headers or the URL query:
    # Agora forwards the callback key in Authorization and callers may put secrets
    # in other headers/query parameters as well.
    authorization = raw_headers.get("authorization", "")
    logger.info(
        "[AGORA_INCOMING_REQUEST]",
        request_id=turn.turn_id,
        session_id=turn.session_id,
        channel=turn.channel_name,
        requesting_agent_id=turn.raw_headers.get("x-agent-id"),
        path=raw_request.url.path,
        stream=request.stream,
        message_count=len(request.messages),
        authorization_present=bool(authorization.strip()),
        bearer_credential_present=(
            authorization.lower().startswith("bearer ")
            and bool(authorization[7:].strip())
        ),
        api_key_present=bool(raw_headers.get("api-key") or raw_headers.get("x-api-key")),
    )

    if request.stream:
        return StreamingResponse(
            custom_llm_adapter.generate_stream(turn),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Request-ID": turn.turn_id,
            },
        )

    response = await custom_llm_adapter.generate_response_async(turn)
    return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump())


@router.get(
    "/custom-llm/readiness",
    status_code=status.HTTP_200_OK,
    summary="Adapter readiness probe",
)
async def adapter_readiness():
    """Readiness check verifying adapter availability without calling external LLMs."""
    ready = custom_llm_adapter.is_ready()
    return {
        "status": "ready" if ready else "unavailable",
        "service": "intra-ai-custom-llm-adapter",
    }
