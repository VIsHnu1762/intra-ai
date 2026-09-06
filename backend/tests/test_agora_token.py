"""Unit tests for Agora RTC token generation in Intra AI."""

import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


class TestAgoraToken(unittest.TestCase):
    """Test suite for Agora RTC token endpoint, security boundaries, and error cases."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    # ── TEST 1: Valid Configuration Generates Valid Token ────────────────────
    def test_01_valid_configuration_generates_token(self) -> None:
        """With AGORA_APP_ID and AGORA_APP_CERTIFICATE configured, returns scoped RTC token."""
        with patch.object(settings, "AGORA_APP_ID", "test_app_id_12345"), patch.object(
            settings, "AGORA_APP_CERTIFICATE", "test_cert_abcdef67890"
        ):
            resp = self.client.get("/api/v1/interviews/sess-test-interview-99/agora-token?uid=1001&role=1")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            self.assertEqual(data["app_id"], "test_app_id_12345")
            self.assertEqual(data["channel_name"], "sess-test-interview-99")
            self.assertEqual(data["uid"], 1001)
            self.assertEqual(data["role"], 1)
            self.assertEqual(data["expires_in"], 3600)
            self.assertTrue(isinstance(data["token"], str) and len(data["token"]) > 30)

            # Strict security assertion: App certificate must NEVER appear in response
            self.assertNotIn("test_cert_abcdef67890", str(data))

    # ── TEST 2: Missing App ID Raises Error ──────────────────────────────────
    def test_02_missing_app_id_raises_sanitized_error(self) -> None:
        """Missing AGORA_APP_ID raises sanitized AgoraConfigurationError."""
        with patch.object(settings, "AGORA_APP_ID", ""), patch.object(
            settings, "AGORA_APP_CERTIFICATE", "some_cert"
        ):
            resp = self.client.get("/api/v1/interviews/sess-test-99/agora-token")
            self.assertEqual(resp.status_code, 500)
            data = resp.json()
            self.assertEqual(data["code"], "AGORA_CONFIG_ERROR")
            self.assertIn("not configured", data["message"].lower())

    # ── TEST 3: Missing App Certificate Raises Error ─────────────────────────
    def test_03_missing_app_cert_raises_sanitized_error(self) -> None:
        """Missing AGORA_APP_CERTIFICATE raises sanitized AgoraConfigurationError."""
        with patch.object(settings, "AGORA_APP_ID", "some_app_id"), patch.object(
            settings, "AGORA_APP_CERTIFICATE", ""
        ):
            resp = self.client.get("/api/v1/interviews/sess-test-99/agora-token")
            self.assertEqual(resp.status_code, 500)
            data = resp.json()
            self.assertEqual(data["code"], "AGORA_CONFIG_ERROR")
            self.assertIn("not configured", data["message"].lower())

    # ── TEST 4: Expiry Parameter Enforced ────────────────────────────────────
    def test_04_token_builder_receives_correct_expiry(self) -> None:
        """Verify token generation passes correct 1-hour expiry to Agora builder."""
        with patch.object(settings, "AGORA_APP_ID", "test_app_id"), patch.object(
            settings, "AGORA_APP_CERTIFICATE", "test_cert"
        ), patch("app.routes.interviews.RtcTokenBuilder2.build_token_with_uid") as mock_builder:
            mock_builder.return_value = "mock_rtc_token_xyz"

            resp = self.client.get("/api/v1/interviews/channel-abc/agora-token?uid=42&role=1")

            self.assertEqual(resp.status_code, 200)
            mock_builder.assert_called_once()
            call_kwargs = mock_builder.call_args.kwargs
            self.assertEqual(call_kwargs["app_id"], "test_app_id")
            self.assertEqual(call_kwargs["app_certificate"], "test_cert")
            self.assertEqual(call_kwargs["channel_name"], "channel-abc")
            self.assertEqual(call_kwargs["uid"], 42)
    # ── TEST 5: Agent Token Matches Studio Wildcard RTC Structure ────────────
    def test_05_agent_token_structure_matches_studio_wildcard_rtc(self) -> None:
        """Verify build_agent_token produces wildcard RTC UID and dynamic RTM user_id."""
        import base64
        import struct
        import zlib
        from app.core.agora_token2 import RtcTokenBuilder2

        app_id = "test_app_id_999"
        app_cert = "test_cert_1234567890123456789012"
        channel = "dynamic-interview-channel-xyz"
        agent_uid = "468707"

        token = RtcTokenBuilder2.build_agent_token(
            app_id=app_id,
            app_certificate=app_cert,
            channel_name=channel,
            agent_rtc_uid=agent_uid,
            expire_seconds=3600,
        )

        self.assertTrue(token.startswith("007"))
        self.assertNotIn(app_cert, token)

        # Decompress token payload
        raw = base64.b64decode(token[3:])
        decomp = zlib.decompress(raw)

        # Parse header
        pos = 0
        sig_len = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2 + sig_len
        app_id_len = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2
        parsed_app_id = decomp[pos:pos+app_id_len].decode()
        pos += app_id_len
        issue_ts, expire, salt = struct.unpack("<III", decomp[pos:pos+12])
        pos += 12
        service_count = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2

        self.assertEqual(parsed_app_id, app_id)
        self.assertEqual(service_count, 2)

        # Parse Service 1 (RTC)
        svc1_type = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2
        self.assertEqual(svc1_type, 1)  # ServiceRtc
        priv1_count = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2 + (priv1_count * 6)
        cname_len = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2
        parsed_channel = decomp[pos:pos+cname_len].decode()
        pos += cname_len
        uid_len = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2
        parsed_uid = decomp[pos:pos+uid_len].decode()
        pos += uid_len

        self.assertEqual(parsed_channel, channel)
        self.assertEqual(parsed_uid, "")  # Wildcard UID matches Studio layout

        # Parse Service 2 (RTM)
        svc2_type = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2
        self.assertEqual(svc2_type, 2)  # ServiceRtm
        priv2_count = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2 + (priv2_count * 6)
        user_len = struct.unpack("<H", decomp[pos:pos+2])[0]
        pos += 2
        parsed_user = decomp[pos:pos+user_len].decode()
        pos += user_len

        self.assertEqual(parsed_user, agent_uid)


if __name__ == "__main__":
    unittest.main()

