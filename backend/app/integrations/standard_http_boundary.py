"""HTTP-only protection for legacy Standard Interview entry points.

No interview engine, M1, context, routing, or Agora session behavior lives here.
Guards are attached at composition time so frozen Standard modules stay intact.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute

from app.core.config import settings
from app.core.deps import get_supabase
from app.services.workspace_access import current_actor
from app.voice.authorization import Actor, require_interview

MAX_NOTIFICATION_BYTES = 256 * 1024


async def require_persisted_interview(
    request: Request,
    actor: Actor = Depends(current_actor),
    sb: Any = Depends(get_supabase),
) -> None:
    key = request.path_params.get("interview_id")
    if not key:
        raise HTTPException(403, "Use a persisted scheduled interview")
    await require_interview(actor, str(key), sb)


async def retired_agent_endpoint() -> None:
    # The legacy config response can contain server-side adapter credentials.
    # Even an authenticated participant must never receive that configuration.
    raise HTTPException(410, "Use the authenticated scheduled-interview session API")


async def require_agora_notification(request: Request) -> None:
    secret = settings.AGORA_NOTIFICATION_SECRET
    if not secret:
        raise HTTPException(503, "Agora notification verification is not configured")
    signatures = request.headers.getlist("agora-signature-v2")
    if len(signatures) != 1 or not re.fullmatch(r"[0-9a-fA-F]{64}", signatures[0]):
        raise HTTPException(401, "Invalid Agora notification signature")
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) < 0 or int(length) > MAX_NOTIFICATION_BYTES:
                raise HTTPException(413, "Notification too large")
        except ValueError:
            raise HTTPException(400, "Invalid content length") from None
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_NOTIFICATION_BYTES:
            raise HTTPException(413, "Notification too large")
        chunks.append(chunk)
    raw = b"".join(chunks)
    # Preserve the exact bytes for the existing request.json() ingestion path.
    request._body = raw
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signatures[0].lower()):
        raise HTTPException(401, "Invalid Agora notification signature")


def install_standard_http_boundaries(app: FastAPI) -> None:
    """Install once after routers are included, before OpenAPI/startup."""
    retired = {"get_agora_rtc_token", "get_agora_agent_config", "start_agora_agent", "stop_agora_agent"}
    signed = {"agora_webhook_global", "agora_webhook_interview"}
    scoped = {"ingest_transcript_event", "get_interview_transcript"}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        module, name = route.endpoint.__module__, route.endpoint.__name__
        guard = None
        if module == "app.routes.sessions" and "{interview_id}" in route.path:
            guard = require_persisted_interview
        elif module == "app.routes.sessions" and "POST" in route.methods:
            # Session configurations are server-created by scheduling. The old
            # arbitrary-config test launcher is intentionally not a public API.
            guard = retired_agent_endpoint
        elif module == "app.routes.interviews":
            if name in retired:
                guard = retired_agent_endpoint
            elif name in signed:
                guard = require_agora_notification
            elif name in scoped:
                guard = require_persisted_interview
        if guard is None or any(item.call is guard for item in route.dependant.dependencies):
            continue
        dependency = Depends(guard)
        route.dependencies.insert(0, dependency)
        route.dependant.dependencies.insert(0, get_parameterless_sub_dependant(depends=dependency, path=route.path_format))
