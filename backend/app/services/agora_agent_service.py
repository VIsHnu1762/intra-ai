"""Agora Conversational AI Agent lifecycle service for starting and stopping interviewer agents."""

from __future__ import annotations

import base64
import time
from typing import Any, Optional
import httpx
import structlog

from app.agents.registry import AgentRegistry, agent_registry
from app.core.agora_token2 import RtcTokenBuilder2
from app.core.config import settings
from app.core.exceptions import AgoraConfigurationError

logger = structlog.stdlib.get_logger("intra_ai.services.agora_agent")


class AgoraAgentService:
    """Service to start, monitor, and stop Agora Conversational AI agents via official Agora REST APIs."""

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.registry = registry or agent_registry
        self.http_client = http_client

    async def start_interview_agent(
        self,
        interview_id: str,
        agent_id: str = "alex",
        agent_rtc_uid: Optional[int | str] = None,
        user_uid: int | str = 0,
        greeting_text: Optional[str] = None,
    ) -> dict[str, Any]:
        """Dispatch and start a configured Agora Conversational AI agent into the candidate's RTC channel.

        Steps:
        1. Resolve the agent profile and Agora mapping.
        2. Resolve the Agent RTC UID (from param or mapping default).
        3. Generate a valid AccessToken2 (Token007) for the agent.
        4. Build the official Agora Conversational AI start/join payload.
        5. Call Agora Conversational AI v2 API:
           POST https://api.agora.io/api/conversational-ai-agent/v2/projects/{app_id}/join
        6. Return a sanitized status result.
        """
        app_id = (settings.AGORA_APP_ID or "").strip()
        app_certificate = (settings.AGORA_APP_CERTIFICATE or "").strip()

        if not app_id or not app_certificate:
            raise AgoraConfigurationError("Agora App ID or App Certificate is not configured on the server.")

        channel_name = interview_id.strip()

        # 1. Resolve agent profile and mapping
        profile, mapping = self.registry.get_agent(agent_id)
        resolved_agent_uid = str(agent_rtc_uid) if agent_rtc_uid is not None and str(agent_rtc_uid) != "1001" else str(mapping.agent_rtc_uid)

        # 2. Generate dynamic AccessToken2 for the agent in this channel
        try:
            agent_token = RtcTokenBuilder2.build_agent_token(
                app_id=app_id,
                app_certificate=app_certificate,
                channel_name=channel_name,
                agent_rtc_uid=resolved_agent_uid,
                expire_seconds=86400,
            )
        except Exception as exc:
            logger.error("agora_token_build_failed", error=str(exc), interview_id=interview_id)
            raise AgoraConfigurationError(f"Failed to generate Agora Agent RTC token: {exc}") from exc

        # 3. Build official Agora Conversational AI v2 join payload
        props: dict[str, Any] = {
            "channel": channel_name,
            "agent_rtc_uid": resolved_agent_uid,
            "remote_rtc_uids": ["*"],
            # Keep the cloud agent alive while the browser finishes device checks
            # and joins. The default idle timeout is short enough to make a
            # silent opening look like a broken interview.
            "idle_timeout": 120,
            "token": agent_token,
            "advanced_features": {
                "enable_rtm": True,
            },
            "parameters": {
                "data_channel": "rtm",
                "enable_error_message": True,
                "enable_metrics": True,
            },
        }

        # Include Custom LLM configuration overrides so Agora Cloud directs ASR turns to our adapter.
        # Append session_id and agent_id as query parameters to the LLM URL so Agora preserves them
        # when it POSTs to /chat/completions. These are the only non-secret identifiers we embed —
        # no tokens, API keys, or credentials are included in the URL.
        if mapping.llm_url:
            from urllib.parse import urlparse, urlencode, urlunparse, parse_qs, urljoin
            parsed = urlparse(mapping.llm_url)
            # Build identity query params
            identity_params = urlencode({
                "session_id": channel_name,
                "agent_id": agent_id,
            })
            # Append to any existing query string
            existing_qs = parsed.query
            combined_qs = f"{existing_qs}&{identity_params}" if existing_qs else identity_params
            llm_url_with_identity = urlunparse(parsed._replace(query=combined_qs))

            # Agora's Custom LLM contract requires the custom vendor and the
            # OpenAI request style. The callback credential is distinct from
            # the Groq key used inside our adapter and is forwarded by Agora as
            # Authorization: Bearer <api_key>.
            custom_llm_api_key = (getattr(settings, "CUSTOM_LLM_API_KEY", "") or "").strip()
            props["llm"] = {
                "credential_mode": "byok",
                "vendor": "custom",
                "style": "openai",
                "url": llm_url_with_identity,
                "api_key": custom_llm_api_key,
                "params": {"model": mapping.llm_model or "intra-ai"},
                "input_modalities": ["text"],
                "output_modalities": ["text"],
            }
            # A handoff resumes the existing conversation. Its receiving
            # persona must not repeat a new-interview introduction.
            greeting = mapping.greeting if greeting_text is None else greeting_text
            if greeting:
                props["llm"]["greeting_message"] = greeting
            logger.info(
                "[CUSTOM_LLM_URL_CONFIGURED]",
                agent_id=agent_id,
                session_id=channel_name,
                # Log the base URL only — never the full URL with any potential secrets
                llm_base_url=f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            )


        # Raw REST requests must explicitly select managed credentials. Omitting
        # an API key alone defaults to BYOK; the SDK additionally injects a
        # managed preset, which this hand-built request does not use.
        props["tts"] = {
            "credential_mode": "managed",
            "vendor": mapping.tts_vendor or "openai",
            "params": {
                "model": mapping.tts_model or "tts-1",
                "voice": mapping.tts_voice or "echo",
                "speed": mapping.tts_speed,
            },
        }
        if props["tts"]["vendor"] == "openai":
            # base_url is the provider setting; url is also required by the
            # deployed Agora managed-mode validator. Both were verified live.
            props["tts"]["params"].update({
                "base_url": "https://api.openai.com/v1",
                "url": "https://api.openai.com/v1/audio/speech",
            })

        v2_join_payload = {
            "name": f"{agent_id}-{channel_name}",
            "pipeline_id": mapping.pipeline_id,
            "properties": props,
        }

        # 4. Configure Authorization header (prefer Basic auth if Customer ID/Secret present, otherwise 'agora token=')
        customer_id = (getattr(settings, "AGORA_CUSTOMER_ID", "") or "").strip()
        customer_secret = (getattr(settings, "AGORA_CUSTOMER_SECRET", "") or "").strip()

        if customer_id and customer_secret:
            auth_bytes = f"{customer_id}:{customer_secret}".encode("utf-8")
            auth_header = f"Basic {base64.b64encode(auth_bytes).decode('utf-8')}"
        else:
            auth_header = f"agora token={agent_token}"

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }

        logger.info(
            "[AGORA_AGENT_START]",
            agent_id=agent_id,
            pipeline_id=mapping.pipeline_id,
            interview_id=channel_name,
            channel=channel_name,
            agent_rtc_uid=resolved_agent_uid,
        )

        from app.interview_context.store import interview_session_store

        # Register aliases for an already-created context. Do not create a context
        # here because this service does not know the canonical candidate identity.
        interview_session_store.register_alias(channel_name, channel_name)

        api_url = f"https://api.agora.io/api/conversational-ai-agent/v2/projects/{app_id}/join"

        try:
            client = self.http_client or httpx.AsyncClient(timeout=15.0)
            async with client as http:
                response = await http.post(api_url, headers=headers, json=v2_join_payload)
                response_data = response.json() if response.content else {}

                if response.status_code in (200, 201, 204):
                    agora_agent_res_id = response_data.get("agent_id")
                    if agora_agent_res_id:
                        interview_session_store.register_alias(agora_agent_res_id, channel_name)

                    logger.info(
                        "[AGORA_AGENT_START_SUCCESS]",
                        agent_id=agent_id,
                        pipeline_id=mapping.pipeline_id,
                        channel=channel_name,
                        agora_agent_id=agora_agent_res_id,
                    )
                    return {
                        "status": "started",
                        "mode": "cloud_dispatched",
                        "agent_id": agent_id,
                        "agent_name": profile.display_name,
                        "channel_name": channel_name,
                        "agent_rtc_uid": resolved_agent_uid,
                        "agora_agent_id": agora_agent_res_id,
                        "agora_response": response_data,
                    }
                elif response.status_code == 409 and response_data.get("agent_id"):
                    agora_agent_res_id = response_data.get("agent_id")
                    if agora_agent_res_id:
                        interview_session_store.register_alias(agora_agent_res_id, channel_name)

                    logger.info(
                        "[AGORA_AGENT_START_SUCCESS]",
                        agent_id=agent_id,
                        pipeline_id=mapping.pipeline_id,
                        channel=channel_name,
                        agora_agent_id=agora_agent_res_id,
                        note="already_running",
                    )
                    return {
                        "status": "started",
                        "mode": "cloud_dispatched",
                        "agent_id": agent_id,
                        "agent_name": profile.display_name,
                        "channel_name": channel_name,
                        "agent_rtc_uid": resolved_agent_uid,
                        "agora_agent_id": agora_agent_res_id,
                        "agora_response": response_data,
                    }
                else:
                    error_msg = response_data.get("message") or response.text or f"HTTP {response.status_code}"
                    logger.error(
                        "[AGORA_AGENT_START_FAILURE]",
                        agent_id=agent_id,
                        pipeline_id=mapping.pipeline_id,
                        error=error_msg,
                        status_code=response.status_code,
                    )
                    return {
                        "status": "error",
                        "mode": "cloud_dispatch_failed",
                        "agent_id": agent_id,
                        "error": f"Agora API join failed: {error_msg}",
                        "status_code": response.status_code,
                    }
        except Exception as exc:
            logger.error("[AGORA_AGENT_START_FAILURE]", agent_id=agent_id, pipeline_id=mapping.pipeline_id, error=str(exc))
            return {
                "status": "error",
                "mode": "cloud_dispatch_failed",
                "agent_id": agent_id,
                "error": f"Failed to connect to Agora start API: {exc}",
            }

    async def stop_interview_agent(
        self,
        interview_id: str,
        agent_id: str = "alex",
        agora_agent_id: Optional[str] = None,
        agent_rtc_uid: Optional[int | str] = None,
    ) -> dict[str, Any]:
        """Stop an active Agora Conversational AI agent."""
        app_id = (settings.AGORA_APP_ID or "").strip()
        app_certificate = (settings.AGORA_APP_CERTIFICATE or "").strip()

        if not app_id:
            return {"status": "skipped", "message": "Agora App ID not configured."}

        # 1. Resolve agent profile and mapping
        profile, mapping = self.registry.get_agent(agent_id)
        resolved_agent_uid = str(agent_rtc_uid) if agent_rtc_uid is not None and str(agent_rtc_uid) != "1001" else str(mapping.agent_rtc_uid)

        # Generate auth token if needed
        agent_token = ""
        if app_certificate:
            try:
                agent_token = RtcTokenBuilder2.build_agent_token(
                    app_id=app_id,
                    app_certificate=app_certificate,
                    channel_name=interview_id.strip(),
                    agent_rtc_uid=resolved_agent_uid,
                    expire_seconds=3600,
                )
            except Exception:
                pass

        customer_id = (getattr(settings, "AGORA_CUSTOMER_ID", "") or "").strip()
        customer_secret = (getattr(settings, "AGORA_CUSTOMER_SECRET", "") or "").strip()

        if customer_id and customer_secret:
            auth_bytes = f"{customer_id}:{customer_secret}".encode("utf-8")
            auth_header = f"Basic {base64.b64encode(auth_bytes).decode('utf-8')}"
        elif agent_token:
            auth_header = f"agora token={agent_token}"
        else:
            return {"status": "skipped", "message": "No credentials available to stop agent."}

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }

        # If agora_agent_id is provided, call REST leave endpoint
        if agora_agent_id:
            api_url = f"https://api.agora.io/api/conversational-ai-agent/v2/projects/{app_id}/agents/{agora_agent_id}/leave"
            try:
                client = self.http_client or httpx.AsyncClient(timeout=10.0)
                async with client as http:
                    response = await http.post(api_url, headers=headers)
                    if 200 <= response.status_code < 300 or response.status_code == 404:
                        return {"status": "stopped", "code": response.status_code}
                    # A rejected leave does not permit another interviewer to
                    # join: the original voice may still be publishing.
                    return {
                        "status": "error",
                        "code": response.status_code,
                        "error": f"Agora API leave failed: HTTP {response.status_code}",
                    }
            except Exception as exc:
                return {"status": "error", "error": str(exc)}

        return {"status": "skipped", "note": "no_agora_agent_id"}

    async def get_agent_history(self, agora_agent_id: str) -> dict[str, Any]:
        """Read cloud speech timing without confusing streamed text with audio.

        Lifecycle transitions use completed assistant speech in this history;
        returning an empty history on failure would hide an observability gap.
        """
        app_id = (settings.AGORA_APP_ID or "").strip()
        customer_id = (settings.AGORA_CUSTOMER_ID or "").strip()
        customer_secret = (settings.AGORA_CUSTOMER_SECRET or "").strip()
        if not (app_id and customer_id and customer_secret):
            raise AgoraConfigurationError("Agora customer credentials are required to verify response playback")
        auth = base64.b64encode(f"{customer_id}:{customer_secret}".encode()).decode()
        url = (
            f"https://api.agora.io/api/conversational-ai-agent/v2/projects/{app_id}"
            f"/agents/{agora_agent_id}/history"
        )
        client = self.http_client or httpx.AsyncClient(timeout=10.0)
        async with client as http:
            response = await http.get(url, headers={"Authorization": f"Basic {auth}"})
            response.raise_for_status()
            return response.json()


agora_agent_service = AgoraAgentService()
