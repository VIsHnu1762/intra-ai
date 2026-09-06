"""Isolated Agora Studio adapter for the training and HR assistants.

This adapter never reads the official interview project's credentials or agent
registry. Studio retains ASR and TTS. The LLM is inherited unless Morgan's
explicit managed mode is enabled; Taylor always retains its Studio LLM.

Contracts: https://docs.agora.io/en/api-reference/api-ref/conversational-ai/join
and https://docs.agora.io/en/api-reference/api-ref/conversational-ai/authentication
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Literal, Sequence
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.core.agora_token2 import AccessToken2, pack_map_uint32, pack_string, pack_uint16

AgentType = Literal["taylor", "morgan"]
_API_ROOT = "https://api.agora.io/api/conversational-ai-agent/v2/projects"
_STATUSES = {"IDLE", "STARTING", "RUNNING", "STOPPING", "STOPPED", "FAILED"}
_MANAGED_MODELS = {"gpt-4o-mini", "gpt-4.1-mini", "gpt-5-nano", "gpt-5-mini"}
_logger = logging.getLogger(__name__)


class AuxiliaryAgoraError(Exception):
    """Public-safe error: no provider response, request, token or cause retained."""

    def __init__(self, code: str, message: str, *, http_status: int = 502,
                 provider_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.provider_status = provider_status


def _configuration_error() -> AuxiliaryAgoraError:
    return AuxiliaryAgoraError("VOICE_CONFIGURATION_ERROR",
        "The training and HR voice project is not configured correctly.", http_status=503)


def _identifier(value: str, *, max_length: int = 128) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or len(value) > max_length:
        raise AuxiliaryAgoraError("VOICE_INVALID_SESSION", "Invalid voice session identifier.", http_status=400)
    return value


def _uid(value: int | str) -> str:
    # Conversational AI remote_rtc_uids has a signed 31-bit upper bound,
    # narrower than the RTC SDK's general unsigned UID range.
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,10}", str(value)) or not 0 < int(value) <= 0x7FFFFFFF:
        raise AuxiliaryAgoraError("VOICE_INVALID_UID", "Invalid voice participant identifier.", http_status=400)
    return str(int(value))


def _ttl(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1800:
        raise AuxiliaryAgoraError("VOICE_INVALID_EXPIRY", "Voice tokens must expire within 30 minutes.", http_status=400)
    return value


@dataclass(frozen=True, slots=True)
class AgoraStudioAgentConfig:
    agent_type: AgentType
    pipeline_id: str
    agent_rtc_uid: str

    def __post_init__(self) -> None:
        if (self.agent_type not in {"taylor", "morgan"} or not isinstance(self.pipeline_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.pipeline_id)):
            raise _configuration_error()
        try:
            object.__setattr__(self, "agent_rtc_uid", _uid(self.agent_rtc_uid))
        except AuxiliaryAgoraError:
            raise _configuration_error() from None


@dataclass(frozen=True, slots=True)
class AgoraProjectConfig:
    app_id: str
    app_certificate: str = field(repr=False)
    taylor: AgoraStudioAgentConfig
    morgan: AgoraStudioAgentConfig
    api_token: str = field(default="", repr=False)
    morgan_llm_mode: Literal["studio", "managed"] = "studio"
    morgan_managed_model: str = "gpt-4.1-mini"

    def __post_init__(self) -> None:
        if (not isinstance(self.app_id, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", self.app_id)
                or not isinstance(self.app_certificate, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", self.app_certificate)
                or not isinstance(self.taylor, AgoraStudioAgentConfig) or not isinstance(self.morgan, AgoraStudioAgentConfig)
                or self.taylor.agent_type != "taylor" or self.morgan.agent_type != "morgan"
                or self.taylor.agent_rtc_uid == self.morgan.agent_rtc_uid):
            raise _configuration_error()
        # Studio embeds provide a full `agora token=007...` Authorization
        # value. A fresh session token replaces that expiring, channel-bound
        # token below. Basic credentials, if explicitly configured for this
        # separate project, are already a complete Authorization header.
        if not isinstance(self.api_token, str) or (self.api_token and not re.fullmatch(r"(?:agora token=007[A-Za-z0-9+/=]+|Basic [A-Za-z0-9+/=]+)", self.api_token)):
            raise _configuration_error()
        if (not isinstance(self.morgan_llm_mode, str) or self.morgan_llm_mode not in {"studio", "managed"}
                or not isinstance(self.morgan_managed_model, str) or self.morgan_managed_model not in _MANAGED_MODELS):
            raise _configuration_error()

    @classmethod
    def from_settings(cls, settings: Any) -> "AgoraProjectConfig":
        def read(name: str) -> str:
            return str(getattr(settings, name, "") or "").strip()
        return cls(
            app_id=read("AGORA_TRAINING_HR_APP_ID"),
            app_certificate=read("AGORA_TRAINING_HR_APP_CERTIFICATE"),
            api_token=read("AGORA_TRAINING_HR_API_TOKEN"),
            taylor=AgoraStudioAgentConfig("taylor", read("AGORA_TAYLOR_AGENT_ID"), read("AGORA_TAYLOR_AGENT_RTC_UID")),
            morgan=AgoraStudioAgentConfig("morgan", read("AGORA_MORGAN_AGENT_ID"), read("AGORA_MORGAN_AGENT_RTC_UID")),
            morgan_llm_mode=read("AGORA_MORGAN_LLM_MODE") or "studio",
            morgan_managed_model=read("AGORA_MORGAN_MANAGED_MODEL") or "gpt-4.1-mini",
        )

    def agent(self, agent_type: AgentType) -> AgoraStudioAgentConfig:
        if agent_type not in {"taylor", "morgan"}:
            raise AuxiliaryAgoraError("VOICE_INVALID_AGENT", "Unknown training or HR voice assistant.", http_status=400)
        return self.taylor if agent_type == "taylor" else self.morgan


class TrainingHRAgoraService:
    def __init__(self, project: AgoraProjectConfig, http_client: httpx.AsyncClient | None = None,
                 *, timeout_seconds: float = 15.0) -> None:
        self.project = project
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds

    def _token(self, channel: str, uid: str, expires_in: int, *, rtc: bool, rtm: bool) -> str:
        token = AccessToken2(self.project.app_id, self.project.app_certificate, expire=_ttl(expires_in))
        if rtc:
            # Official AccessToken2 publisher privileges: join, audio, video,
            # data. Bind the UID explicitly; never mint a wildcard candidate.
            service = (pack_uint16(1) + pack_map_uint32({i: expires_in for i in (1, 2, 3, 4)})
                       + pack_string(channel) + pack_string(uid))
            token.services.append((1, service))
        if rtm:
            token.add_rtm_service(uid, expire=expires_in)
        return token.build()

    def candidate_credentials(self, channel: str, candidate_uid: int | str, *, expires_in: int = 1800) -> dict[str, Any]:
        channel, uid = _identifier(channel, max_length=63), _uid(candidate_uid)
        if uid in {self.project.taylor.agent_rtc_uid, self.project.morgan.agent_rtc_uid}:
            raise AuxiliaryAgoraError("VOICE_UID_CONFLICT", "Voice participant identifiers must be distinct.", http_status=400)
        ttl = _ttl(expires_in)
        return {"app_id": self.project.app_id, "channel": channel, "uid": int(uid),
                "rtc_token": self._token(channel, uid, ttl, rtc=True, rtm=False),
                "rtm_token": self._token(channel, uid, ttl, rtc=False, rtm=True),
                "expires_at": int(time.time()) + ttl}

    def _authorization(self, agent_token: str) -> str:
        if self.project.api_token.startswith("Basic "):
            return self.project.api_token
        return f"agora token={agent_token}"

    async def _request(self, method: str, path: str, *, authorization: str,
                       payload: dict[str, Any] | None = None, empty_ok: bool = False) -> dict[str, Any]:
        url = f"{_API_ROOT}/{self.project.app_id}/{path}"
        headers = {"Authorization": authorization, "Content-Type": "application/json"}
        try:
            if self.http_client is not None:
                response = await self.http_client.request(method, url, json=payload, headers=headers,
                    timeout=self.timeout_seconds, follow_redirects=False)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.request(method, url, json=payload, headers=headers, follow_redirects=False)
        except httpx.TimeoutException:
            raise AuxiliaryAgoraError("VOICE_PROVIDER_TIMEOUT", "The voice provider timed out. Please retry.", http_status=504) from None
        except httpx.RequestError:
            raise AuxiliaryAgoraError("VOICE_PROVIDER_UNREACHABLE", "The voice provider could not be reached.") from None
        status = response.status_code
        if not 200 <= status < 300:
            code, message, mapped = {
                401: ("VOICE_PROVIDER_AUTHENTICATION", "The voice provider rejected the server credentials.", 503),
                403: ("VOICE_PROVIDER_FORBIDDEN", "This voice project is not authorized for that operation.", 503),
                404: ("VOICE_AGENT_NOT_FOUND", "This voice agent is no longer available.", 404),
                429: ("VOICE_PROVIDER_LIMIT", "The voice provider is busy. Please retry shortly.", 503),
            }.get(status, ("VOICE_PROVIDER_ERROR", "The voice provider could not complete the request.", 502))
            raise AuxiliaryAgoraError(code, message, http_status=mapped, provider_status=status)
        if empty_ok and not response.content:
            return {}
        try:
            result = response.json()
        except ValueError:
            raise AuxiliaryAgoraError("VOICE_INVALID_RESPONSE", "The voice provider returned an invalid response.") from None
        if not isinstance(result, dict):
            raise AuxiliaryAgoraError("VOICE_INVALID_RESPONSE", "The voice provider returned an invalid response.")
        return result

    @staticmethod
    def _safe_result(result: dict[str, Any], channel: str, *, expected_id: str | None = None) -> dict[str, str]:
        agent_id = result.get("agent_id", expected_id)
        if (not isinstance(agent_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", agent_id)
                or (expected_id is not None and agent_id != expected_id)
                or (result.get("channel") is not None and result["channel"] != channel)):
            raise AuxiliaryAgoraError("VOICE_SESSION_MISMATCH", "The voice provider returned inconsistent session details.")
        status = result.get("status")
        return {"agent_id": agent_id, "channel": channel,
                "status": status if isinstance(status, str) and status in _STATUSES else "UNKNOWN"}

    async def start_agent(self, agent_type: AgentType, channel: str, candidate_uid: int | str,
                          session_name: str, *, system_prompt: str | None = None,
                          greeting_message: str | None = None,
                          mcp_endpoint: str | None = None, mcp_authorization: str | None = None,
                          allowed_tools: Sequence[str] = (), expires_in: int = 1800) -> dict[str, str]:
        agent = self.project.agent(agent_type)
        channel, uid = _identifier(channel, max_length=63), _uid(candidate_uid)
        _identifier(session_name, max_length=128)
        if uid in {self.project.taylor.agent_rtc_uid, self.project.morgan.agent_rtc_uid}:
            raise AuxiliaryAgoraError("VOICE_UID_CONFLICT", "Voice participant identifiers must be distinct.", http_status=400)
        agent_token = self._token(channel, agent.agent_rtc_uid, expires_in, rtc=True, rtm=True)
        properties: dict[str, Any] = {
            "channel": channel, "token": agent_token, "agent_rtc_uid": agent.agent_rtc_uid,
            "remote_rtc_uids": [uid], "enable_string_uid": False, "idle_timeout": 60,
            "advanced_features": {"enable_rtm": True},
            "parameters": {"data_channel": "rtm", "enable_error_message": True,
                           "enable_metrics": True, "transcript": {"enable": True, "protocol_version": "v2"}},
        }
        llm: dict[str, Any] = {}
        if system_prompt is not None:
            if not isinstance(system_prompt, str) or not system_prompt.strip() or len(system_prompt) > 24000:
                raise AuxiliaryAgoraError("VOICE_INVALID_CONTEXT", "Invalid voice assistant context.", http_status=400)
            llm["system_messages"] = [{"role": "system", "content": system_prompt}]
        if greeting_message is not None:
            try:
                if (not isinstance(greeting_message, str) or not greeting_message.strip()
                        or len(greeting_message.encode("utf-8")) > 1024):
                    raise ValueError()
            except (ValueError, UnicodeError):
                raise AuxiliaryAgoraError("VOICE_INVALID_GREETING", "The voice greeting must be 1 to 1024 bytes.", http_status=400) from None
            # A short context-aware opening uses the saved Studio TTS voice.
            # single_first prevents replay when the same participant rejoins.
            llm["greeting_message"] = greeting_message.strip()
            llm["greeting_configs"] = {"mode": "single_first"}
        if agent_type == "taylor" and (mcp_endpoint is not None or mcp_authorization is not None or allowed_tools):
            raise AuxiliaryAgoraError("VOICE_INVALID_MCP", "Taylor uses preloaded practice context and has no MCP tools.", http_status=503)
        if mcp_endpoint is not None:
            try:
                parsed = urlsplit(mcp_endpoint)
                _ = parsed.port
            except ValueError:
                raise AuxiliaryAgoraError("VOICE_INVALID_MCP", "The voice assistant tools are not configured correctly.", http_status=503) from None
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or len(mcp_endpoint) > 2048
                    or not mcp_authorization or not re.fullmatch(r"Bearer [A-Za-z0-9_.-]+", mcp_authorization)
                    or not allowed_tools or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", tool) for tool in allowed_tools)):
                raise AuxiliaryAgoraError("VOICE_INVALID_MCP", "The voice assistant tools are not configured correctly.", http_status=503)
            llm["mcp_servers"] = [{"name": "IntraAssistantTools", "transport": "streamable_http",
                "endpoint": mcp_endpoint, "headers": {"Authorization": mcp_authorization},
                "allowed_tools": list(dict.fromkeys(allowed_tools)), "timeout_ms": 10000}]
            properties["advanced_features"]["enable_tools"] = True
        elif mcp_authorization or allowed_tools:
            raise AuxiliaryAgoraError("VOICE_INVALID_MCP", "The voice assistant tools are not configured correctly.", http_status=503)
        elif agent_type == "taylor":
            # Omission would inherit any tools saved in the Studio pipeline.
            # Normal practice uses its already-loaded CV context and native LLM.
            properties["advanced_features"]["enable_tools"] = False
            llm["mcp_servers"] = []
        managed_morgan = agent_type == "morgan" and self.project.morgan_llm_mode == "managed"
        if managed_morgan:
            # Agora supplies the model credential. Keep the saved ASR/TTS and
            # this session's prompt/MCP settings; never borrow an official key.
            # https://docs.agora.io/en/ai/models/llm/openai
            llm.update(credential_mode="managed", vendor="openai", style="openai",
                       url="https://api.openai.com/v1/chat/completions",
                       params={"model": self.project.morgan_managed_model}, max_history=32)
        if llm:
            properties["llm"] = llm
        result = await self._request("POST", "join", authorization=self._authorization(agent_token),
            payload={"name": session_name, "pipeline_id": agent.pipeline_id, "properties": properties})
        safe = self._safe_result(result, channel)
        if managed_morgan:
            try:
                # Join merges saved custom proxy params. Update replaces the
                # entire params object and removes those incompatible fields.
                # Finish this before the service issues browser credentials.
                # https://docs.agora.io/en/api-reference/api-ref/conversational-ai/update
                path, authorization = self._agent_request(agent_type, channel, safe["agent_id"])
                updated = await self._request("POST", f"{path}/update", authorization=authorization,
                    payload={"properties": {"llm": {"params": {"model": self.project.morgan_managed_model}}}})
                safe = self._safe_result(updated, channel, expected_id=safe["agent_id"])
            except BaseException:
                # This agent has not yet been handed to VoiceAssistantService,
                # so the adapter owns cleanup even on request cancellation.
                try:
                    await asyncio.shield(self.stop_agent(agent_type, channel, safe["agent_id"]))
                except Exception:
                    _logger.error("morgan_managed_start_cleanup_pending agent_id=%s", safe["agent_id"])
                raise
        return safe

    def _agent_request(self, agent_type: AgentType, channel: str, agent_id: str) -> tuple[str, str]:
        agent = self.project.agent(agent_type)
        _identifier(channel, max_length=63)
        _identifier(agent_id)
        token = self._token(channel, agent.agent_rtc_uid, 1800, rtc=True, rtm=True)
        return f"agents/{agent_id}", self._authorization(token)

    async def query_agent(self, agent_type: AgentType, channel: str, agent_id: str) -> dict[str, str]:
        path, authorization = self._agent_request(agent_type, channel, agent_id)
        result = await self._request("GET", path, authorization=authorization)
        return self._safe_result(result, channel, expected_id=agent_id)

    async def stop_agent(self, agent_type: AgentType, channel: str, agent_id: str) -> dict[str, str]:
        path, authorization = self._agent_request(agent_type, channel, agent_id)
        try:
            await self._request("POST", f"{path}/leave", authorization=authorization, empty_ok=True)
        except AuxiliaryAgoraError as exc:
            if exc.provider_status != 404:
                raise
        return {"agent_id": agent_id, "channel": channel, "status": "STOPPED"}

    async def announce_result(self, agent_type: AgentType, channel: str, agent_id: str,
                              text: str) -> dict[str, str]:
        """Speak a server-confirmed action result with the saved Studio voice.

        Caller must authorize/execute the action first. HTTP acceptance is not
        proof that the browser has played the audio.
        """
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 512:
            raise AuxiliaryAgoraError("VOICE_INVALID_ANNOUNCEMENT", "The voice announcement must be 1 to 512 bytes.", http_status=400)
        path, authorization = self._agent_request(agent_type, channel, agent_id)
        await self._request("POST", f"{path}/speak", authorization=authorization,
                            payload={"text": text, "priority": "APPEND", "interruptable": True}, empty_ok=True)
        return {"agent_id": agent_id, "channel": channel, "status": "ANNOUNCEMENT_ACCEPTED"}

    async def request_practice_feedback(self, agent_type: AgentType, channel: str, agent_id: str,
                                        *, text: str, request_id: str) -> dict[str, str]:
        """Trigger the same running Taylor Studio LLM, not another provider.

        `/think` returns request acceptance, not generated feedback. The caller
        must read and validate the subsequent assistant text before stopping the
        agent. The 8192-byte bound is local; Agora does not document a text cap.
        https://docs.agora.io/en/api-reference/api-ref/conversational-ai/think
        """
        if agent_type != "taylor":
            raise AuxiliaryAgoraError("VOICE_INVALID_AGENT", "Practice feedback is available only for Taylor.", http_status=400)
        try:
            if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 8192:
                raise ValueError()
            if not isinstance(request_id, str) or len(request_id) > 36:
                raise ValueError()
            UUID(request_id)
        except (ValueError, UnicodeError):
            raise AuxiliaryAgoraError("VOICE_INVALID_FEEDBACK_REQUEST", "Invalid practice feedback instruction or request identifier.", http_status=400) from None
        path, authorization = self._agent_request(agent_type, channel, agent_id)
        result = await self._request("POST", f"{path}/think", authorization=authorization,
            payload={"text": text, "on_listening_action": "interrupt",
                     "on_thinking_action": "interrupt", "on_speaking_action": "interrupt",
                     "interruptable": False, "metadata": {"request_id": request_id}})
        safe = self._safe_result(result, channel, expected_id=agent_id)
        return {"agent_id": safe["agent_id"], "channel": safe["channel"],
                "status": "FEEDBACK_REQUEST_ACCEPTED", "request_id": request_id}

    async def get_history(self, agent_type: AgentType, channel: str, agent_id: str) -> dict[str, Any]:
        """Read bounded user/assistant text from the current Taylor agent.

        This endpoint exposes short-term history while the agent is running,
        not a paginated durable archive. Other response fields are discarded.
        https://docs.agora.io/en/api-reference/api-ref/conversational-ai/history
        """
        if agent_type != "taylor":
            raise AuxiliaryAgoraError("VOICE_INVALID_AGENT", "Practice history is available only for Taylor.", http_status=400)
        path, authorization = self._agent_request(agent_type, channel, agent_id)
        result = await self._request("GET", f"{path}/history", authorization=authorization)
        safe = self._safe_result(result, channel, expected_id=agent_id)
        raw = result.get("contents", [])
        if not isinstance(raw, list):
            raise AuxiliaryAgoraError("VOICE_INVALID_HISTORY", "The voice provider returned invalid practice history.")
        contents = []
        truncated = len(raw) > 128
        budget = 131072
        # Retain the newest response and its request marker if an unexpectedly
        # large history exceeds local limits. Return chronological order.
        for item in reversed(raw[-128:]):
            if not isinstance(item, dict):
                raise AuxiliaryAgoraError("VOICE_INVALID_HISTORY", "The voice provider returned invalid practice history.")
            if item.get("role") not in {"user", "assistant"}:
                truncated = True
                continue
            content = item.get("content")
            if not isinstance(content, str):
                raise AuxiliaryAgoraError("VOICE_INVALID_HISTORY", "The voice provider returned invalid practice history.")
            if budget <= 0:
                truncated = True
                break
            limit = min(32768, budget)
            truncated = truncated or len(content) > limit
            value = content[:limit]
            budget -= len(value)
            contents.append({"role": item["role"], "content": value})
        return {**safe, "contents": list(reversed(contents)), "truncated": truncated}
