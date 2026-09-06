"""Narrow server-only Composio MCP bridge for Morgan's controlled HR tools.

This is a provider adapter, not an authorization boundary. The caller must
authorize the recruiter/workspace and retain immutable, explicitly confirmed
inputs before invoking a write. No raw SQL, arbitrary URL, code execution,
connection management, or broad Composio tool catalogue reaches the model.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, ValidationError as PydanticError, model_validator

from app.core.exceptions import AppError, ValidationError


class MorganConnectorError(AppError):
    status_code = 503
    code = "MORGAN_CONNECTOR_UNAVAILABLE"
    message = "Morgan's connected service is unavailable. No completed external action has been verified."


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Empty(_Input):
    pass


class _Profile(_Input):
    user_id: Literal["me"] = "me"


class _Calendars(_Input):
    max_results: int = Field(default=10, ge=1, le=25, strict=True)
    page_token: str | None = Field(default=None, max_length=2048)


class _Channels(_Input):
    limit: int = Field(default=25, ge=1, le=100, strict=True)
    cursor: str | None = Field(default=None, max_length=2048)
    types: Literal["public_channel", "private_channel", "public_channel,private_channel"] = "public_channel"
    exclude_archived: Literal[True] = True


class _Email(_Profile):
    recipient_email: EmailStr
    subject: str = Field(min_length=1, max_length=200, pattern=r"^[^\r\n]+$")
    body: str = Field(min_length=1, max_length=5000)
    is_html: Literal[False] = False


class _CalendarEvent(_Input):
    calendar_id: str = Field(default="primary", min_length=1, max_length=256, pattern=r"^[^\s\x00-\x1f]+$")
    summary: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    start_datetime: AwareDatetime
    end_datetime: AwareDatetime
    attendees: list[EmailStr] = Field(min_length=1, max_length=50)
    send_updates: Literal["all", "none"]
    create_meeting_room: Literal[False] = False

    @model_validator(mode="after")
    def ordered(self):
        if self.end_datetime <= self.start_datetime:
            raise ValueError("End must follow start")
        return self


class _SlackMessage(_Input):
    channel: str = Field(pattern=r"^[CDG][A-Z0-9]{2,31}$")
    markdown_text: str = Field(min_length=1, max_length=4000)
    unfurl_links: Literal[False] = False
    unfurl_media: Literal[False] = False


_READ = {
    "GMAIL_GET_PROFILE": _Profile,
    "GOOGLECALENDAR_LIST_CALENDARS": _Calendars,
    "SLACK_TEST_AUTH": _Empty,
    "SLACK_LIST_CONVERSATIONS": _Channels,
}
_WRITE = {
    "GMAIL_CREATE_EMAIL_DRAFT": _Email,
    "GMAIL_SEND_EMAIL": _Email,
    "GOOGLECALENDAR_CREATE_EVENT": _CalendarEvent,
    "SLACK_SEND_MESSAGE": _SlackMessage,
}
_ALLOWED = {**_READ, **_WRITE}
_MAX_BYTES = 2 * 1024 * 1024


def _text(value: Any, limit: int = 256) -> str:
    return str(value or "")[:limit]


class MorganComposioClient:
    def __init__(self, url: str = "", api_key: str = "", *, http_client: httpx.AsyncClient | None = None):
        self._url, self._api_key = url.strip(), api_key.strip()
        self._http = http_client

    @classmethod
    def from_settings(cls, settings, **kwargs):
        return cls(settings.MORGAN_COMPOSIO_MCP_URL, settings.MORGAN_COMPOSIO_API_KEY, **kwargs)

    @property
    def configured(self) -> bool:
        try:
            url = urlsplit(self._url)
            return bool(self._api_key and "\n" not in self._api_key and "\r" not in self._api_key
                and url.scheme == "https" and url.hostname in {"app.composio.dev", "backend.composio.dev"}
                and url.port in {None, 443} and not (url.username or url.password or url.query or url.fragment)
                and re.fullmatch(r"/tool_router/(?:v3(?:\.1)?/)?[A-Za-z0-9_-]+/mcp", url.path))
        except ValueError:
            return False

    async def _rpc(self, client, headers, method: str, params: dict, rpc_id: int | None):
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if rpc_id is not None:
            payload["id"] = rpc_id
        try:
            async with client.stream("POST", self._url, headers=headers, json=payload, timeout=15, follow_redirects=False) as response:
                if response.status_code not in ({200, 202, 204} if rpc_id is None else {200}):
                    raise MorganConnectorError()
                data = bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data) > _MAX_BYTES:
                        raise MorganConnectorError()
                session = response.headers.get("mcp-session-id")
                if session:
                    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", session):
                        raise MorganConnectorError()
                    headers["Mcp-Session-Id"] = session
                if rpc_id is None:
                    return {}
                if "text/event-stream" in response.headers.get("content-type", ""):
                    events = []
                    # SSE data fields can span lines in one event.
                    for event in bytes(data).decode().replace("\r\n", "\n").split("\n\n"):
                        text = "\n".join(line[5:].lstrip() for line in event.splitlines() if line.startswith("data:"))
                        if text:
                            events.append(json.loads(text))
                    message = next((item for item in events if isinstance(item, dict) and item.get("id") == rpc_id), {})
                else:
                    message = json.loads(data)
                if not isinstance(message, dict) or message.get("id") != rpc_id or "error" in message or not isinstance(message.get("result"), dict):
                    raise MorganConnectorError()
                return message["result"]
        except (httpx.HTTPError, ValueError, UnicodeError):
            # Never include response prose, endpoint, auth headers or causes.
            raise MorganConnectorError() from None

    @asynccontextmanager
    async def _connection(self):
        if not self.configured:
            raise MorganConnectorError("Morgan's Composio connection is not configured.")
        headers = {"x-api-key": self._api_key, "Accept": "application/json, text/event-stream"}
        client = self._http or httpx.AsyncClient()
        try:
            await self._rpc(client, headers, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "intra-morgan-controlled-bridge", "version": "1"}}, 1)
            await self._rpc(client, headers, "notifications/initialized", {}, None)
            yield client, headers
        finally:
            if self._http is None:
                await client.aclose()

    async def discover(self) -> dict[str, Any]:
        """Return approved tool availability, never the broad remote catalogue."""
        if not self.configured:
            return {"configured": False, "available_tools": [], "connection_status": "not_configured"}
        async with self._connection() as (client, headers):
            result = await self._rpc(client, headers, "tools/list", {}, 2)
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise MorganConnectorError()
        names = {tool.get("name") for tool in tools if isinstance(tool, dict) and isinstance(tool.get("name"), str)}
        return {"configured": True, "available_tools": sorted(names & _ALLOWED.keys()),
                "connection_status": "mcp_reachable", "app_authorization_verified": False}

    @staticmethod
    def preview(name: str, arguments: dict) -> dict[str, Any]:
        """Validate an immutable prospective call without external side effects."""
        model = _ALLOWED.get(name)
        if model is None:
            raise ValidationError("This external operation is not approved for Morgan")
        try:
            value = model.model_validate(arguments)
        except PydanticError:
            raise ValidationError("Invalid connected-service arguments") from None
        args = value.model_dump(mode="json", exclude_none=True)
        return {"tool": name, "arguments": args, "requires_confirmation": name in _WRITE}

    async def call_tool(self, name: str, arguments: dict, *, confirmation_id: str | None = None) -> dict[str, Any]:
        """Execute only approved operations after caller-owned authorization.

        Writes require the identifier of the caller's claimed, persisted
        confirmation. This parameter is never a replacement for checking that
        confirmation's owner, immutable inputs and one-time execution state.
        """
        review = self.preview(name, arguments)
        if name in _WRITE:
            try:
                UUID(str(confirmation_id))
            except (ValueError, TypeError, AttributeError):
                raise ValidationError("A persisted recruiter confirmation is required") from None
        args = dict(review["arguments"])
        if name == "GOOGLECALENDAR_CREATE_EVENT":
            # Keep offsets in the immutable review. Only normalize the wire
            # payload because the discovered provider strips datetime offsets.
            for field in ("start_datetime", "end_datetime"):
                args[field] = datetime.fromisoformat(args[field]).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            args["timezone"] = "UTC"
        async with self._connection() as (client, headers):
            response = await self._rpc(client, headers, "tools/call", {"name": name, "arguments": args}, 2)
        if response.get("isError"):
            raise MorganConnectorError()
        content = response.get("content", [])
        try:
            values = [json.loads(item["text"]) for item in content if isinstance(item, dict) and item.get("type") == "text"]
        except (ValueError, TypeError, KeyError):
            raise MorganConnectorError() from None
        if len(values) != 1:
            raise MorganConnectorError()
        data = values[0]
        for _ in range(5):
            if not isinstance(data, dict):
                break
            if data.get("successful") is False or data.get("success") is False or data.get("ok") is False or data.get("error"):
                raise MorganConnectorError()
            if "data" not in data:
                break
            data = data["data"]
        if not isinstance(data, dict):
            raise MorganConnectorError()
        return self._safe_data(name, data)

    @staticmethod
    def _safe_data(name: str, data: dict) -> dict[str, Any]:
        if name == "GMAIL_GET_PROFILE":
            email = _text(data.get("emailAddress"))
            if "@" not in email:
                raise MorganConnectorError()
            return {"verified": True, "email": email}
        if name == "SLACK_TEST_AUTH":
            if data.get("ok") is not True or not data.get("team_id"):
                raise MorganConnectorError()
            return {"verified": True, **{key: _text(data.get(key)) for key in ("team_id", "user_id", "bot_id") if data.get(key)}}
        if name == "GOOGLECALENDAR_LIST_CALENDARS":
            # Composio's current direct tool normalizes Google's items and
            # nextPageToken; accept either documented response representation.
            rows = data.get("calendars", data.get("items"))
            if not isinstance(rows, list):
                raise MorganConnectorError()
            return {"verified": True, "calendars": [{key: row[key] if isinstance(row[key], bool) else _text(row[key])
                for key in ("id", "summary", "primary", "accessRole", "timeZone") if key in row}
                for row in rows[:25] if isinstance(row, dict)], "next_page_token": _text(data.get("next_page_token", data.get("nextPageToken")), 2048)}
        if name == "SLACK_LIST_CONVERSATIONS":
            rows = data.get("channels")
            if data.get("ok") is not True or not isinstance(rows, list):
                raise MorganConnectorError()
            return {"verified": True, "channels": [{key: row[key] if isinstance(row[key], bool) else _text(row[key])
                for key in ("id", "name", "is_private", "is_archived") if key in row}
                for row in rows[:100] if isinstance(row, dict)],
                "next_cursor": _text((data.get("response_metadata") or {}).get("next_cursor"), 2048)}
        identifier = data.get("ts") if name == "SLACK_SEND_MESSAGE" else data.get("id")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 256:
            raise MorganConnectorError()
        return {"provider": "composio", "provider_tool": name, "provider_id": identifier,
                "status": "accepted", "delivered": "not_verified"}
