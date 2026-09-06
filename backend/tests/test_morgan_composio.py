"""Controlled MCP connector boundary: all provider traffic is synthetic."""
import json
from uuid import uuid4

import httpx
import pytest

from app.core.exceptions import ValidationError
from app.voice.composio import MorganComposioClient, MorganConnectorError

URL = "https://app.composio.dev/tool_router/v3/trs_synthetic/mcp"
SECRET = "synthetic-private-connector-key"


@pytest.mark.parametrize("path", ["/tool_router/trs_synthetic/mcp", "/tool_router/v3/trs_synthetic/mcp", "/tool_router/v3.1/trs_synthetic/mcp"])
def test_supplied_session_endpoint_and_documented_versioned_forms_are_accepted(path):
    assert MorganComposioClient("https://app.composio.dev" + path, SECRET).configured


def client_with(tool_data=None, *, sse=True, rpc_error=False, is_error=False, schema_names=(), request_log=None):
    request_log = request_log if request_log is not None else []

    def handler(request):
        request_log.append(request)
        assert request.headers["x-api-key"] == SECRET
        body = json.loads(request.content)
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        result = {"protocolVersion": "2025-03-26"}
        if body["method"] == "tools/list":
            result = {"tools": [{"name": name, "inputSchema": {"type": "object"}, "description": "untrusted"} for name in schema_names]}
        elif body["method"] == "tools/call":
            result = {"content": [{"type": "text", "text": json.dumps({"data": tool_data, "successful": not is_error, "error": SECRET if is_error else None})}], "isError": is_error}
        response = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        if rpc_error:
            response = {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32603, "message": SECRET}}
        if sse:
            return httpx.Response(200, headers={"content-type": "text/event-stream", "mcp-session-id": "mcp_synthetic"}, content="event: message\ndata: " + json.dumps(response) + "\n\n")
        return httpx.Response(200, json=response)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return MorganComposioClient(URL, SECRET, http_client=http)


@pytest.mark.asyncio
async def test_discovery_filters_remote_catalog_and_does_not_claim_app_access():
    requests = []
    client = client_with(schema_names=["SLACK_TEST_AUTH", "GMAIL_SEND_EMAIL", "SUPABASE_BETA_RUN_SQL_QUERY", "RUN_ARBITRARY_CODE"], request_log=requests)
    result = await client.discover()
    assert result == {"configured": True, "available_tools": ["GMAIL_SEND_EMAIL", "SLACK_TEST_AUTH"], "connection_status": "mcp_reachable", "app_authorization_verified": False}
    assert len(requests) == 3
    assert requests[-1].headers["mcp-session-id"] == "mcp_synthetic"
    assert SECRET not in json.dumps(result) and URL not in json.dumps(result)


@pytest.mark.parametrize("url", ["http://app.composio.dev/tool_router/v3/test/mcp", "https://evil.test/tool_router/v3/test/mcp", URL + "?key=secret", URL + "#secret", "https://app.composio.dev/arbitrary", "https://user:password@app.composio.dev/tool_router/v3/test/mcp"])
@pytest.mark.asyncio
async def test_unapproved_or_credential_bearing_endpoints_do_not_make_requests(url):
    client = MorganComposioClient(url, SECRET)
    assert not client.configured
    with pytest.raises(MorganConnectorError):
        await client.call_tool("SLACK_TEST_AUTH", {})


@pytest.mark.asyncio
async def test_missing_configuration_is_explicit():
    assert await MorganComposioClient().discover() == {"configured": False, "available_tools": [], "connection_status": "not_configured"}


@pytest.mark.parametrize("sse", [False, True])
@pytest.mark.asyncio
async def test_gmail_profile_returns_only_minimal_identity(sse):
    result = await client_with({"emailAddress": "recruiter@example.com", "messagesTotal": 777, "private": SECRET}, sse=sse).call_tool("GMAIL_GET_PROFILE", {})
    assert result == {"verified": True, "email": "recruiter@example.com"}


@pytest.mark.asyncio
async def test_slack_channels_filter_conversation_content_and_preserve_cursor():
    result = await client_with({"ok": True, "channels": [{"id": "C123", "name": "hiring", "is_private": False, "topic": {"value": SECRET}}], "response_metadata": {"next_cursor": "cursor-next"}}).call_tool("SLACK_LIST_CONVERSATIONS", {})
    assert result == {"verified": True, "channels": [{"id": "C123", "name": "hiring", "is_private": False}], "next_cursor": "cursor-next"}


@pytest.mark.asyncio
async def test_calendar_read_does_not_claim_write_or_meeting_support():
    result = await client_with({"items": [{"id": "primary-id", "summary": "Work", "accessRole": "reader", "conferenceProperties": SECRET}], "nextPageToken": "more"}).call_tool("GOOGLECALENDAR_LIST_CALENDARS", {"max_results": 1})
    assert result == {"verified": True, "calendars": [{"id": "primary-id", "summary": "Work", "accessRole": "reader"}], "next_page_token": "more"}


@pytest.mark.asyncio
async def test_observed_composio_calendar_wrapper_is_supported():
    result = await client_with({"calendars": [{"id": "primary-id", "summary": "Work", "primary": True}], "next_page_token": "more", "next_sync_token": SECRET}).call_tool("GOOGLECALENDAR_LIST_CALENDARS", {"max_results": 1})
    assert result == {"verified": True, "calendars": [{"id": "primary-id", "summary": "Work", "primary": True}], "next_page_token": "more"}


@pytest.mark.parametrize("name,args", [("SUPABASE_BETA_RUN_SQL_QUERY", {"query": "SELECT 1"}), ("GMAIL_GET_PROFILE", {"user_id": "other@example.com"}), ("SLACK_LIST_CONVERSATIONS", {"limit": 101}), ("SLACK_SEND_MESSAGE", {"channel": "general", "markdown_text": "hello"}), ("GMAIL_SEND_EMAIL", {"recipient_email": "candidate@example.com", "subject": "Hello\nBcc:other", "body": "hello"}), ("GMAIL_SEND_EMAIL", {"recipient_email": "candidate@example.com", "subject": "Hello", "body": "hello", "bcc": ["other@example.com"]})])
@pytest.mark.asyncio
async def test_invalid_or_unapproved_arguments_fail_before_network(name, args):
    requests = []
    client = client_with(request_log=requests)
    with pytest.raises(ValidationError):
        await client.call_tool(name, args, confirmation_id=str(uuid4()))
    assert requests == []


@pytest.mark.parametrize("name,args", [("GMAIL_CREATE_EMAIL_DRAFT", {"recipient_email": "candidate@example.com", "subject": "Interview", "body": "Draft"}), ("GMAIL_SEND_EMAIL", {"recipient_email": "candidate@example.com", "subject": "Interview", "body": "Draft"}), ("SLACK_SEND_MESSAGE", {"channel": "C123", "markdown_text": "Confirmed hiring update"})])
@pytest.mark.asyncio
async def test_writes_require_persisted_confirmation_identifier_before_network(name, args):
    requests = []
    client = client_with(request_log=requests)
    with pytest.raises(ValidationError, match="persisted recruiter confirmation"):
        await client.call_tool(name, args)
    assert requests == []


@pytest.mark.asyncio
async def test_calendar_review_preserves_offsets_and_wire_preserves_reviewed_instant():
    value = MorganComposioClient.preview("GOOGLECALENDAR_CREATE_EVENT", {
        "summary": "Interview", "start_datetime": "2026-09-07T14:00:00+05:30", "end_datetime": "2026-09-07T14:30:00+05:30",
        "attendees": ["candidate@example.com"], "send_updates": "none"})
    assert value["arguments"]["start_datetime"] == "2026-09-07T14:00:00+05:30"
    assert value["arguments"]["end_datetime"] == "2026-09-07T14:30:00+05:30"
    assert value["arguments"]["create_meeting_room"] is False
    assert value["requires_confirmation"] is True
    requests = []
    client = client_with({"id": "synthetic-event"}, request_log=requests)
    await client.call_tool(value["tool"], value["arguments"], confirmation_id=str(uuid4()))
    args = json.loads(requests[-1].content)["params"]["arguments"]
    assert args["start_datetime"] == "2026-09-07T08:30:00"
    assert args["end_datetime"] == "2026-09-07T09:00:00"
    assert args["timezone"] == "UTC"


def test_calendar_rejects_unknown_offset_and_reversed_interval():
    args = {"summary": "Interview", "start_datetime": "2026-09-07T14:00:00", "end_datetime": "2026-09-07T13:00:00", "attendees": ["candidate@example.com"], "send_updates": "none"}
    with pytest.raises(ValidationError):
        MorganComposioClient.preview("GOOGLECALENDAR_CREATE_EVENT", args)
    args.update(start_datetime="2026-09-07T14:00:00Z", end_datetime="2026-09-07T13:00:00Z")
    with pytest.raises(ValidationError):
        MorganComposioClient.preview("GOOGLECALENDAR_CREATE_EVENT", args)


@pytest.mark.asyncio
async def test_confirmed_mock_send_uses_exact_reviewed_body_and_returns_receipt_only():
    requests = []
    client = client_with({"id": "provider-receipt", "private": SECRET}, request_log=requests)
    args = {"recipient_email": "candidate@example.com", "subject": "Interview", "body": "Exactly this reviewed text"}
    result = await client.call_tool("GMAIL_SEND_EMAIL", args, confirmation_id=str(uuid4()))
    submitted = json.loads(requests[-1].content)["params"]
    assert submitted["arguments"]["body"] == args["body"]
    assert submitted["arguments"]["recipient_email"] == args["recipient_email"]
    assert result == {"provider": "composio", "provider_tool": "GMAIL_SEND_EMAIL", "provider_id": "provider-receipt", "status": "accepted", "delivered": "not_verified"}


@pytest.mark.parametrize("kwargs", [{"rpc_error": True}, {"is_error": True}, {}])
@pytest.mark.asyncio
async def test_error_and_missing_receipt_are_never_reported_as_success(kwargs):
    client = client_with({}, **kwargs)
    with pytest.raises(MorganConnectorError) as exc:
        await client.call_tool("GMAIL_SEND_EMAIL", {"recipient_email": "candidate@example.com", "subject": "Hello", "body": "Reviewed"}, confirmation_id=str(uuid4()))
    assert SECRET not in str(exc.value) and URL not in str(exc.value)
