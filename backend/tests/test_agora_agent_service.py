"""Test Agora dispatch with a Custom LLM and explicitly managed TTS credentials."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.core.config import settings
from app.core.exceptions import AgoraConfigurationError
from app.services.agora_agent_service import AgoraAgentService


class TestAgoraAgentService(unittest.IsolatedAsyncioTestCase):
    """Test suite for AgoraAgentService."""

    def setUp(self) -> None:
        # The adapter credential must not depend on a developer's .env file.
        self.callback_api_key = "test-custom-llm-callback-key"
        callback_key_patch = patch.object(settings, "CUSTOM_LLM_API_KEY", self.callback_api_key)
        callback_key_patch.start()
        self.addCleanup(callback_key_patch.stop)
        # Legacy pipeline tests are independent of a local shared-base setting.
        common_pipeline_patch = patch.object(settings, "AGORA_CUSTOM_LLM_PIPELINE_ID", "")
        common_pipeline_patch.start()
        self.addCleanup(common_pipeline_patch.stop)

    async def test_shared_custom_llm_pipeline_keeps_persona_dispatch_distinct(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.content = b'{"agent_id":"cloud-agent","status":"RUNNING"}'
        response.json.return_value = {"agent_id": "cloud-agent", "status": "RUNNING"}
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=response)
        service = AgoraAgentService(http_client=mock_http)

        with patch.object(settings, "AGORA_CUSTOM_LLM_PIPELINE_ID", "  shared-custom-base  "), patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012"):
            for agent_id in ("alex", "jordan"):
                result = await service.start_interview_agent(interview_id="same-channel", agent_id=agent_id)
                self.assertEqual(result["status"], "started")

        alex, jordan = [call.kwargs["json"] for call in mock_http.post.call_args_list]
        for payload, agent_id, voice in ((alex, "alex", "echo"), (jordan, "jordan", "nova")):
            self.assertEqual(payload["pipeline_id"], "shared-custom-base")
            props = payload["properties"]
            self.assertEqual(props["channel"], "same-channel")
            self.assertIn(f"agent_id={agent_id}", props["llm"]["url"])
            self.assert_voice_dispatch_contract(props, expected_voice=voice)
        self.assertNotEqual(alex["properties"]["agent_rtc_uid"], jordan["properties"]["agent_rtc_uid"])
        self.assertNotEqual(alex["properties"]["llm"]["greeting_message"], jordan["properties"]["llm"]["greeting_message"])

    def test_empty_common_base_retains_explicit_persona_pipelines(self) -> None:
        service = AgoraAgentService()
        with patch.object(settings, "AGORA_CUSTOM_LLM_PIPELINE_ID", "   "), patch.object(settings, "AGORA_ALEX_PIPELINE_ID", "configured-alex"), patch.object(settings, "AGORA_JORDAN_PIPELINE_ID", "configured-jordan"):
            self.assertEqual(service.registry.get_agora_mapping("alex").pipeline_id, "configured-alex")
            self.assertEqual(service.registry.get_agora_mapping("jordan").pipeline_id, "configured-jordan")

    def assert_voice_dispatch_contract(self, props: dict, expected_voice: str) -> None:
        """Guard the raw REST fields required by the verified Agora voice path."""
        llm = props["llm"]
        self.assertEqual(llm["credential_mode"], "byok")
        self.assertEqual(llm["api_key"], self.callback_api_key)
        self.assertEqual(llm["input_modalities"], ["text"])
        self.assertEqual(llm["output_modalities"], ["text"])

        tts = props["tts"]
        self.assertEqual(tts["credential_mode"], "managed")
        self.assertEqual(tts["vendor"], "openai")
        self.assertEqual(tts["params"]["base_url"], "https://api.openai.com/v1")
        self.assertEqual(tts["params"]["url"], "https://api.openai.com/v1/audio/speech")
        self.assertEqual(tts["params"]["model"], "tts-1")
        self.assertEqual(tts["params"]["voice"], expected_voice)
        self.assertNotIn("api_key", tts)
        self.assertNotIn("api_key", tts["params"])
        self.assertNotIn(self.callback_api_key, str(tts))

        self.assertIs(props["parameters"]["enable_error_message"], True)
        self.assertIs(props["parameters"]["enable_metrics"], True)

    async def test_01_start_agent_without_customer_credentials_uses_agora_token(self) -> None:
        """When customer credentials are not set, uses dynamic Token007 auth header."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = b'{"agent_id": "agora-agent-alex-1", "status": "RUNNING"}'
        mock_response.json.return_value = {"agent_id": "agora-agent-alex-1", "status": "RUNNING"}

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=mock_response)

        service = AgoraAgentService(http_client=mock_http)

        with patch.object(settings, "AGORA_CUSTOMER_ID", ""), patch.object(settings, "AGORA_CUSTOMER_SECRET", ""), patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012"):
            result = await service.start_interview_agent(
                interview_id="test-session-service-01",
                agent_id="alex",
            )
            self.assertEqual(result["status"], "started")
            self.assertEqual(result["mode"], "cloud_dispatched")
            self.assertEqual(result["agent_id"], "alex")
            self.assertEqual(result["channel_name"], "test-session-service-01")

            headers = mock_http.post.call_args[1]["headers"]
            self.assertTrue(headers["Authorization"].startswith("agora token=007"))

    async def test_02_start_alex_with_dynamic_channel(self) -> None:
        """Dispatch Alex to the requested channel with the configured echo voice."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = b'{"agent_id": "agora-agent-alex-1", "status": "RUNNING"}'
        mock_response.json.return_value = {"agent_id": "agora-agent-alex-1", "status": "RUNNING"}

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=mock_response)

        service = AgoraAgentService(http_client=mock_http)

        with patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012"):
            result = await service.start_interview_agent(
                interview_id="interview-dyn-channel-101",
                agent_id="alex",
            )
            self.assertEqual(result["status"], "started")
            self.assertEqual(result["mode"], "cloud_dispatched")
            self.assertEqual(result["agent_id"], "alex")
            self.assertEqual(result["channel_name"], "interview-dyn-channel-101")
            self.assertEqual(result["agora_agent_id"], "agora-agent-alex-1")

            # Verify API call payload
            call_kwargs = mock_http.post.call_args
            self.assertIn("conversational-ai-agent/v2/projects", call_kwargs[0][0])
            payload = call_kwargs[1]["json"]
            self.assertEqual(payload["pipeline_id"], "eb714d82ec524f14981e5b5f5108cbd1")
            self.assertEqual(payload["properties"]["channel"], "interview-dyn-channel-101")
            self.assertEqual(payload["properties"]["agent_rtc_uid"], "468707")
            self.assertNotIn("enable_rtm", payload["properties"])
            self.assertTrue(payload["properties"]["advanced_features"]["enable_rtm"])
            self.assertEqual(payload["properties"]["parameters"]["data_channel"], "rtm")
            self.assertIn("llm", payload["properties"])
            self.assertEqual(payload["properties"]["llm"]["vendor"], "custom")
            self.assertEqual(payload["properties"]["llm"]["style"], "openai")
            self.assertEqual(payload["properties"]["llm"]["params"]["model"], "intra-ai")
            self.assertEqual(payload["properties"]["llm"]["output_modalities"], ["text"])
            self.assert_voice_dispatch_contract(payload["properties"], expected_voice="echo")
            self.assertIn("/api/v1/chat/completions", payload["properties"]["llm"]["url"])
            self.assertEqual(payload["properties"]["tts"]["vendor"], "openai")
            self.assertEqual(payload["properties"]["tts"]["params"]["model"], "tts-1")
            self.assertTrue(payload["properties"]["token"].startswith("007"))

    async def test_03_start_jordan_with_dynamic_channel(self) -> None:
        """Dispatch Jordan with its own UID, pipeline, and distinct nova voice."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = b'{"agent_id": "agora-agent-jordan-2", "status": "RUNNING"}'
        mock_response.json.return_value = {"agent_id": "agora-agent-jordan-2", "status": "RUNNING"}

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=mock_response)

        service = AgoraAgentService(http_client=mock_http)

        with patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012"):
            result = await service.start_interview_agent(
                interview_id="interview-dyn-channel-202",
                agent_id="jordan",
            )
            self.assertEqual(result["status"], "started")
            self.assertEqual(result["mode"], "cloud_dispatched")
            self.assertEqual(result["agent_id"], "jordan")
            self.assertEqual(result["channel_name"], "interview-dyn-channel-202")

            payload = mock_http.post.call_args[1]["json"]
            self.assertEqual(payload["pipeline_id"], "642bb4345fa244099a78a50cede2d7d3")
            self.assertEqual(payload["properties"]["channel"], "interview-dyn-channel-202")
            self.assertEqual(payload["properties"]["agent_rtc_uid"], "654509")
            self.assertNotIn("enable_rtm", payload["properties"])
            self.assertTrue(payload["properties"]["advanced_features"]["enable_rtm"])
            self.assertEqual(payload["properties"]["parameters"]["data_channel"], "rtm")
            self.assertIn("llm", payload["properties"])
            self.assertEqual(payload["properties"]["llm"]["vendor"], "custom")
            self.assertEqual(payload["properties"]["llm"]["style"], "openai")
            self.assertEqual(payload["properties"]["llm"]["params"]["model"], "intra-ai")
            self.assertEqual(payload["properties"]["llm"]["output_modalities"], ["text"])
            self.assert_voice_dispatch_contract(payload["properties"], expected_voice="nova")
            self.assertNotEqual(
                payload["properties"]["tts"]["params"]["voice"],
                service.registry.get_agora_mapping("alex").tts_voice,
            )
            self.assertEqual(payload["properties"]["tts"]["vendor"], "openai")
            self.assertEqual(payload["properties"]["tts"]["params"]["model"], "tts-1")


    async def test_04_start_agent_api_failure_handled_gracefully(self) -> None:
        """When Agora API responds with error status, returns sanitized failure dict."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.content = b'{"message": "Invalid pipeline"}'
        mock_response.json.return_value = {"message": "Invalid pipeline"}

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=mock_response)

        service = AgoraAgentService(http_client=mock_http)

        with patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012"):
            result = await service.start_interview_agent(
                interview_id="test-session-service-04",
                agent_id="alex",
            )
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["mode"], "cloud_dispatch_failed")
            self.assertIn("Invalid pipeline", result["error"])

    async def test_05_stop_agent_calls_leave_endpoint(self) -> None:
        """Stopping an agent with agora_agent_id calls the official leave endpoint."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=mock_response)

        service = AgoraAgentService(http_client=mock_http)

        with patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012"):
            result = await service.stop_interview_agent(
                interview_id="test-session-service-05",
                agent_id="alex",
                agora_agent_id="agora-inst-999",
            )
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(result["code"], 200)

            call_kwargs = mock_http.post.call_args
            self.assertIn("/agents/agora-inst-999/leave", call_kwargs[0][0])

    async def test_stop_http_failure_is_not_reported_as_stopped(self) -> None:
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=httpx.Response(503))
        service = AgoraAgentService(http_client=mock_http)
        with patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_CUSTOMER_ID", "test"), patch.object(settings, "AGORA_CUSTOMER_SECRET", "test"):
            result = await service.stop_interview_agent("same-channel", agora_agent_id="cloud-old")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["code"], 503)

    async def test_handoff_greeting_override_preserves_managed_voice(self) -> None:
        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=httpx.Response(200, json={"agent_id": "cloud-jordan"}))
        service = AgoraAgentService(http_client=mock_http)
        with patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012"):
            await service.start_interview_agent("same-channel", "jordan", greeting_text="Earlier you described Kafka. How would you handle recovery?")
        props = mock_http.post.call_args.kwargs["json"]["properties"]
        self.assertEqual(props["channel"], "same-channel")
        self.assertEqual(props["llm"]["greeting_message"], "Earlier you described Kafka. How would you handle recovery?")
        self.assert_voice_dispatch_contract(props, "nova")

    async def test_06_missing_app_id_or_certificate_raises_error(self) -> None:
        """Missing app_id or app_certificate raises AgoraConfigurationError."""
        service = AgoraAgentService()
        with patch.object(settings, "AGORA_APP_ID", ""), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert"):
            with self.assertRaises(AgoraConfigurationError):
                await service.start_interview_agent(interview_id="room-1", agent_id="alex")

    async def test_07_invalid_agent_id_raises_error(self) -> None:
        """Invalid agent ID raises KeyError / ValueError."""
        service = AgoraAgentService()
        with patch.object(settings, "AGORA_APP_ID", "app_1"), patch.object(settings, "AGORA_APP_CERTIFICATE", "cert_1"):
            with self.assertRaises(Exception):
                await service.start_interview_agent(interview_id="room-1", agent_id="unknown_agent_xyz")

    async def test_08_verify_rtm_and_llm_payload_specifications(self) -> None:
        """Preserve dynamic dispatch and explicitly select adapter BYOK / managed TTS.

        Raw REST calls must supply the credential mode and endpoint fields;
        omitting a provider key does not invoke the SDK's managed preset logic.
        """
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = b'{"agent_id": "test-agent-dyn-01", "status": "RUNNING"}'
        mock_response.json.return_value = {"agent_id": "test-agent-dyn-01", "status": "RUNNING"}

        mock_http = MagicMock(spec=httpx.AsyncClient)
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post = AsyncMock(return_value=mock_response)

        service = AgoraAgentService(http_client=mock_http)
        dynamic_channel = "dynamic-eval-room-9988"

        with patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(settings, "AGORA_APP_CERTIFICATE", "test_cert_1234567890123456789012"):
            result = await service.start_interview_agent(
                interview_id=dynamic_channel,
                agent_id="alex",
            )
            self.assertEqual(result["status"], "started")

            payload = mock_http.post.call_args[1]["json"]
            props = payload["properties"]

            # 1. advanced_features.enable_rtm == True
            self.assertIn("advanced_features", props)
            self.assertIs(props["advanced_features"]["enable_rtm"], True)

            # 2. parameters.data_channel == "rtm"
            self.assertIn("parameters", props)
            self.assertEqual(props["parameters"]["data_channel"], "rtm")

            # 2b. A greeting and a bounded idle window prevent a silent
            # browser lobby from looking like a failed agent join.
            self.assertEqual(props["idle_timeout"], 120)
            self.assertTrue(props["llm"].get("greeting_message"))

            # 3. llm.url comes from configuration/mapping
            profile, mapping = service.registry.get_agent("alex")
            self.assertIn("llm", props)
            self.assertTrue(props["llm"]["url"].startswith(mapping.llm_url))

            # 4. The adapter model comes from configuration/mapping.
            self.assertEqual(props["llm"]["vendor"], "custom")
            self.assertEqual(props["llm"]["style"], "openai")
            self.assertEqual(props["llm"]["params"]["model"], mapping.llm_model)
            self.assertEqual(props["llm"]["output_modalities"], ["text"])
            self.assert_voice_dispatch_contract(props, expected_voice=mapping.tts_voice)

            # 5. no root-level properties.enable_rtm remains
            self.assertNotIn("enable_rtm", props)

            # 6. no hardcoded credentials in payload
            self.assertNotIn("test_cert", str(payload))
            self.assertNotIn("AGORA_CUSTOMER_SECRET", str(payload))

            # 7. no hardcoded Studio channel
            self.assertNotIn("session-test-voice", props["channel"])
            self.assertNotIn("Studio", props["channel"])

            # 8. no hardcoded token (dynamically starts with Token007)
            self.assertTrue(props["token"].startswith("007"))

            # 9. Agora supplies the TTS credential; the adapter key stays in LLM.
            self.assertEqual(props["tts"]["vendor"], "openai")
            self.assertEqual(props["tts"]["params"]["model"], "tts-1")
            self.assertNotIn("api_key", props["tts"]["params"])

            # 10. existing dynamic channel remains intact
            self.assertEqual(props["channel"], dynamic_channel)


if __name__ == "__main__":
    unittest.main()
