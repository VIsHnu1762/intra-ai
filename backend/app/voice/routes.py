"""Authenticated assistant APIs and Agora's session-scoped Streamable HTTP MCP."""
from __future__ import annotations

import json
import re
import time
from copy import deepcopy
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.exceptions import AppError, ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import get_current_user
from app.voice.agora import AuxiliaryAgoraError
from app.voice.models import StartVoiceSession, ConfirmVoiceAction, CallVoiceTool
from app.voice.security import verify_mcp_token
from app.voice.service import VoiceAssistantService, VoiceServiceUnavailable
from app.voice.tools import tool_schemas

router = APIRouter(prefix="/voice", tags=["Voice assistants"])
logger = structlog.stdlib.get_logger("intra_ai.voice.routes")


def get_service(request: Request) -> VoiceAssistantService:
    service = getattr(request.app.state, "voice_assistants", None)
    if service is None:
        raise VoiceServiceUnavailable("The voice assistant is not configured or its session store is unavailable.")
    return service


async def safe_call(awaitable):
    try:
        return await awaitable
    except AuxiliaryAgoraError as exc:
        # Neither provider response prose nor stack traces reach the browser.
        raise HTTPException(exc.http_status, detail={"code": exc.code, "message": exc.message}) from None
    except (AppError, HTTPException):
        raise
    except Exception as exc:
        logger.warning("voice_request_failed", error_type=type(exc).__name__)
        raise VoiceServiceUnavailable() from None


@router.post("/{persona}/sessions", status_code=201)
async def start_voice(persona: Literal["taylor", "morgan"], body: StartVoiceSession,
                      request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).start(persona, user, body.context, body.practice, force=body.force))


@router.post("/{persona}/sessions/active/end")
async def end_active_voice(persona: Literal["taylor", "morgan"], request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).end_active(persona, user))


@router.get("/sessions/{sid}")
async def get_voice(sid: str, request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).get(sid, user))


@router.post("/sessions/{sid}/heartbeat")
async def heartbeat(sid: str, request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).get(sid, user, heartbeat=True))


@router.post("/sessions/{sid}/context")
async def update_context(sid: str, body: StartVoiceSession, request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).update_context(sid, user, body.context))


@router.post("/sessions/{sid}/end")
async def end_voice(sid: str, request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).end(sid, user))


@router.post("/sessions/{sid}/feedback")
async def finish_practice(sid: str, request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).finish_practice(sid, user))


@router.get("/sessions/{sid}/feedback")
async def get_practice_feedback(sid: str, request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).practice_feedback(sid, user))


@router.post("/sessions/{sid}/tools")
async def call_tool(sid: str, body: CallVoiceTool, request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).call_tool(sid, user, body.tool, body.args))


@router.post("/sessions/{sid}/confirm")
async def confirm(sid: str, body: ConfirmVoiceAction, request: Request, user=Depends(get_current_user)):
    return await safe_call(get_service(request).confirm(sid, user, body.confirmation_id, body.approved))


class TranscriptEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=160)
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)
    at: str = Field(min_length=1, max_length=64)


class TranscriptEvents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[TranscriptEvent] = Field(min_length=1, max_length=30)


@router.post("/sessions/{sid}/transcript-events")
async def transcript(sid: str, body: TranscriptEvents, request: Request, user=Depends(get_current_user)):
    # Browser transcripts are a practice/assistant conversation view only.
    # They never reach official evidence, scoring, interview state or reports.
    return await safe_call(get_service(request).transcript(sid, user, [e.model_dump() for e in body.events]))


_CONTEXT_TOOLS = {
    "get_dashboard_context": "Refresh the authorized page only after navigation or selection changes, at most once per user request. Startup context is already supplied. To list candidates use search_candidates directly; an empty page selection is valid.",
    "get_action_status": "Read the actual result or pending confirmation of the recruiter's latest action. Only succeeded results mean the action completed.",
}

# This is a transport representation only. The controlled tool service still
# validates canonical lists, limits, resource IDs, duplicates and ownership.
_MCP_ENCODED_ARRAY_TOOLS = {"bulk_shortlist_candidates": 50, "bulk_schedule_interviews": 25}
_MCP_APPLICATION_IDS_MAX_CHARS = 8192
_MCP_RESOURCE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_MCP_APPLICATION_IDS_ERROR = (
    "Provide application_ids as comma-separated application IDs with no empty entries, "
    'or a JSON array string such as ["application-id-1","application-id-2"].'
)


def mcp_tools(persona: str) -> list[dict[str, Any]]:
    if persona != "morgan":
        return []
    names = {"get_dashboard_context", "get_action_status"}
    result = [{"name": name, "description": description,
               "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}
              for name, description in _CONTEXT_TOOLS.items() if name in names]
    schemas = deepcopy(tool_schemas())
    for schema in schemas:
        maximum = _MCP_ENCODED_ARRAY_TOOLS.get(schema["name"])
        if maximum is not None:
            schema["inputSchema"]["properties"]["application_ids"] = {
                "title": "Application Ids", "type": "string", "minLength": 1,
                "maxLength": _MCP_APPLICATION_IDS_MAX_CHARS,
                "description": (
                    "Selected application IDs separated by commas, for example "
                    "application-id-1,application-id-2. A single ID is allowed. "
                    'A JSON array string such as ["application-id-1","application-id-2"] is also accepted. '
                    f"Include 1 to {maximum} distinct actual application IDs from authorized results, "
                    "not candidate IDs or names."
                ),
            }
    return result + schemas


def _decode_mcp_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in _MCP_ENCODED_ARRAY_TOOLS:
        return arguments
    encoded = arguments.get("application_ids")
    # Existing callers may continue using canonical lists. All other canonical
    # fields, including a missing application_ids value, retain normal validation.
    if not isinstance(encoded, str):
        return arguments
    if len(encoded) > _MCP_APPLICATION_IDS_MAX_CHARS:
        raise ValidationError(_MCP_APPLICATION_IDS_ERROR)
    try:
        decoded = json.loads(encoded)
    except ValueError:
        # Agora may emit a scalar comma-delimited selection. Accept only literal
        # resource IDs: no quote stripping, object coercion or Python evaluation.
        decoded = [item.strip() for item in encoded.split(",")]
        if not all(_MCP_RESOURCE_ID.fullmatch(item) for item in decoded):
            raise ValidationError(_MCP_APPLICATION_IDS_ERROR) from None
    except RecursionError:
        raise ValidationError(_MCP_APPLICATION_IDS_ERROR) from None
    if not isinstance(decoded, list):
        raise ValidationError(_MCP_APPLICATION_IDS_ERROR)
    return {**arguments, "application_ids": decoded}


async def _mcp_claims(request: Request) -> dict:
    # Streamable HTTP MCP permits a stateless JSON response. No credential is
    # accepted in a URL, tool argument, or browser's ordinary auth token.
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != settings.VOICE_ASSISTANT_PUBLIC_URL.rstrip("/"):
        raise ForbiddenError("Origin is not allowed")
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Assistant authorization is required")
    claims = verify_mcp_token(authorization[7:])
    session, _ = await get_service(request).owned(claims["sid"], claims, active=True)
    if session.persona != claims["persona"]:
        raise ForbiddenError("Assistant authorization does not match this session")
    if session.persona != "morgan":
        raise ForbiddenError("Taylor uses preloaded practice context and has no MCP tools")
    return claims


@router.post("/mcp")
async def mcp(request: Request):
    claims = await safe_call(_mcp_claims(request))
    body = await request.body()
    if len(body) > 65536:
        raise HTTPException(413, "Tool request is too large")
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            raise ValueError()
    except (ValueError, TypeError):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON-RPC request"}}
    rpc_id = payload.get("id")
    if not (rpc_id is None or type(rpc_id) is int or (isinstance(rpc_id, str) and len(rpc_id) <= 128)):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request identifier"}}
    method = payload.get("method")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": "Invalid parameters"}}
    known_method = method if isinstance(method, str) and method in {
        "initialize", "ping", "tools/list", "tools/call", "notifications/initialized", "notifications/cancelled"
    } else "unsupported"
    logger.info("voice_mcp_request", session_id=claims["sid"], persona=claims["persona"], method=known_method)
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return Response(status_code=202)
    result: dict[str, Any]
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) and requested in {"2024-11-05", "2025-03-26", "2025-06-18"} else "2025-03-26"
        result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "intra-assistant-tools", "version": "1.0.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": mcp_tools(claims["persona"])}
    elif method == "tools/call":
        name, arguments = params.get("name"), params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": "Invalid tool arguments"}}
        # Names and argument values can be supplied by a model. Log only an
        # allowlisted name, bounded error codes and duration, never raw inputs.
        safe_name = name if name in get_service(request).allowed_tools(claims["persona"]) else "unsupported"
        started = time.monotonic()
        logger.info("voice_mcp_tool_started", session_id=claims["sid"], persona=claims["persona"], tool=safe_name)
        try:
            arguments = _decode_mcp_arguments(name, arguments)
            value = await safe_call(get_service(request).call_tool(claims["sid"], claims, name, arguments))
            logger.info("voice_mcp_tool_completed", session_id=claims["sid"], persona=claims["persona"],
                        tool=safe_name, status=value.get("status", "ok"),
                        duration_ms=round((time.monotonic() - started) * 1000))
            result = {"content": [{"type": "text", "text": json.dumps(value, default=str)}],
                      "isError": value.get("status") == "failed"}
        except AppError as exc:
            logger.warning("voice_mcp_tool_failed", session_id=claims["sid"], persona=claims["persona"],
                           tool=safe_name, code=exc.code, error_type=type(exc).__name__,
                           duration_ms=round((time.monotonic() - started) * 1000))
            result = {"content": [{"type": "text", "text": json.dumps({"status": "failed", "code": exc.code,
                        "message": exc.message})}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}
