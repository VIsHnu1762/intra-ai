"""Unit tests for Groq Cloud M1 Interview Intelligence provider in Intra AI."""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.agents import ALEX_PROFILE, JORDAN_PROFILE
from app.core.config import settings
from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis, InterviewAnswerInput
from app.interview_intelligence.provider import (
    DeterministicMockM1Provider,
    GeminiAnalysisProvider,
    GroqAnalysisProvider,
    M1ProviderError,
    OllamaAnalysisProvider,
    get_m1_provider,
)
from app.models.enums import DifficultyLevel


class TestGroqM1Provider(unittest.TestCase):
    """Test suite for GroqAnalysisProvider and provider selection mechanics."""

    def setUp(self) -> None:
        self.context = InterviewAIContext(
            interview_id="int-test-groq",
            candidate_id="cand-groq",
            current_round_id="round-groq",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )
        self.input_data = InterviewAnswerInput(
            answer_id="ans-groq-test-01",
            question_text="How did you build your distributed cache?",
            answer_text=(
                "I implemented Redis caching in front of our PostgreSQL cluster with cache-aside "
                "pattern and write-through invalidation to handle high read traffic."
            ),
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )
        self.sample_valid_payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer_id": "ans-groq-test-01",
                                "overall_performance": 0.88,
                                "confidence": 0.92,
                                "vague": False,
                                "vague_reason": None,
                                "contradiction_detected": False,
                                "contradiction_details": None,
                                "missing_information": [],
                                "evidence": [
                                    {
                                        "id": "ev-1",
                                        "competency": "system_design",
                                        "signal": "Implemented Redis cache-aside with write-through invalidation.",
                                        "score": 8.8,
                                    }
                                ],
                                "competency_findings": [
                                    {
                                        "competency_id": "system_design",
                                        "assessment": "Solid understanding of caching patterns.",
                                        "confidence": 0.92,
                                        "evidence_ids": ["ev-1"],
                                    }
                                ],
                                "recommended_follow_up": "How did you manage cache stampede?",
                            }
                        ),
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 700,
                "completion_tokens": 200,
                "total_tokens": 900,
            },
        }

    # ── TEST 1: Successful Groq response parsing ─────────────────────────────
    def test_01_successful_response_parsing(self) -> None:
        """Groq OpenAI-compatible response parses cleanly into valid AnswerAnalysis."""
        provider = GroqAnalysisProvider(
            api_key="gsk-test-key",
            model="openai/gpt-oss-20b",
            base_url="https://api.groq.com/openai/v1",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_valid_payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            analysis = provider.analyze_answer(self.input_data)
            self.assertIsInstance(analysis, AnswerAnalysis)
            self.assertEqual(analysis.answer_id, "ans-groq-test-01")
            self.assertEqual(analysis.overall_performance, 0.88)
            self.assertEqual(analysis.confidence, 0.92)
            self.assertFalse(analysis.vague)
            self.assertEqual(len(analysis.evidence), 1)
            self.assertEqual(len(analysis.competency_findings), 1)

    # ── TEST 2: AnswerAnalysis schema validation ─────────────────────────────
    def test_02_answer_analysis_validation(self) -> None:
        """Verified fields match existing AnswerAnalysis schema and grounded evidence."""
        provider = GroqAnalysisProvider(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_valid_payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            analysis = provider.analyze_answer(self.input_data)
            self.assertEqual(analysis.evidence[0].source_agent_id, "alex")
            self.assertEqual(analysis.evidence[0].round_id, "round-groq")

    # ── TEST 3: Answer ID preservation ───────────────────────────────────────
    def test_03_answer_id_preservation(self) -> None:
        """answer_id is preserved from input_data if omitted by model output."""
        provider = GroqAnalysisProvider(api_key="test-key")
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "overall_performance": 0.80,
                                "confidence": 0.85,
                                "vague": False,
                                "contradiction_detected": False,
                                "missing_information": [],
                                "evidence": [],
                                "competency_findings": [],
                            }
                        ),
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            analysis = provider.analyze_answer(self.input_data)
            self.assertEqual(analysis.answer_id, "ans-groq-test-01")

    # ── TEST 4: Malformed JSON output raises M1ProviderError ─────────────────
    def test_04_malformed_json_raises_provider_error(self) -> None:
        """Malformed or unparseable JSON from Groq raises M1ProviderError."""
        provider = GroqAnalysisProvider(api_key="test-key")
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Not JSON at all {invalid[",
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("INVALID_RESPONSE", str(cm.exception))

    # ── TEST 5: Missing required fields raises M1ProviderError ───────────────
    def test_05_missing_required_fields(self) -> None:
        """Missing required fields in AnswerAnalysis schema raises M1ProviderError."""
        provider = GroqAnalysisProvider(api_key="test-key")
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"vague": True}),
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("SCHEMA_VALIDATION_ERROR", str(cm.exception))

    # ── TEST 6: Invalid evidence reference is rejected ───────────────────────
    def test_06_invalid_evidence_references(self) -> None:
        """CompetencyFinding referencing nonexistent evidence_id is rejected."""
        provider = GroqAnalysisProvider(api_key="test-key")
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "answer_id": "ans-01",
                                "overall_performance": 0.8,
                                "confidence": 0.9,
                                "vague": False,
                                "contradiction_detected": False,
                                "missing_information": [],
                                "evidence": [
                                    {"id": "ev-real", "competency": "system_design", "signal": "signal", "score": 8.0}
                                ],
                                "competency_findings": [
                                    {
                                        "competency_id": "system_design",
                                        "assessment": "good",
                                        "confidence": 0.9,
                                        "evidence_ids": ["ev-phantom"],  # Invalid reference
                                    }
                                ],
                            }
                        ),
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("SCHEMA_VALIDATION_ERROR", str(cm.exception))

    # ── TEST 7: HTTP 401 raises sanitized PERMISSION_DENIED ──────────────────
    def test_07_http_401_raises_permission_denied(self) -> None:
        """HTTP 401 raises PERMISSION_DENIED without leaking the API key."""
        secret_key = "gsk_super_secret_key_401"
        provider = GroqAnalysisProvider(api_key=secret_key)
        req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        resp = httpx.Response(401, request=req)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("Unauthorized", request=req, response=resp)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            err_msg = str(cm.exception)
            self.assertIn("PERMISSION_DENIED", err_msg)
            self.assertNotIn(secret_key, err_msg)

    # ── TEST 8: HTTP 403 raises sanitized PERMISSION_DENIED ──────────────────
    def test_08_http_403_raises_permission_denied(self) -> None:
        """HTTP 403 raises PERMISSION_DENIED."""
        provider = GroqAnalysisProvider(api_key="test-key")
        req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        resp = httpx.Response(403, request=req)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("Forbidden", request=req, response=resp)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("PERMISSION_DENIED", str(cm.exception))

    # ── TEST 9: HTTP 429 raises RESOURCE_EXHAUSTED ───────────────────────────
    def test_09_http_429_raises_resource_exhausted(self) -> None:
        """HTTP 429 raises RESOURCE_EXHAUSTED."""
        provider = GroqAnalysisProvider(api_key="test-key")
        req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        resp = httpx.Response(429, request=req)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("Too Many Requests", request=req, response=resp)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("RESOURCE_EXHAUSTED", str(cm.exception))

    # ── TEST 10: HTTP 5xx raises SERVICE_UNAVAILABLE ─────────────────────────
    def test_10_http_5xx_raises_service_unavailable(self) -> None:
        """HTTP 500/502/503/504 raises SERVICE_UNAVAILABLE."""
        provider = GroqAnalysisProvider(api_key="test-key")
        req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
        resp = httpx.Response(503, request=req)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("Service Unavailable", request=req, response=resp)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("SERVICE_UNAVAILABLE", str(cm.exception))

    # ── TEST 11: Timeout raises NETWORK_TIMEOUT ──────────────────────────────
    def test_11_timeout_raises_network_timeout(self) -> None:
        """Request timeout raises NETWORK_TIMEOUT."""
        provider = GroqAnalysisProvider(api_key="test-key")
        req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Connection timed out", request=req)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("NETWORK_TIMEOUT", str(cm.exception))

    # ── TEST 12: Missing API key raises M1ProviderError ──────────────────────
    def test_12_missing_api_key_raises_error(self) -> None:
        """Groq without configured key raises M1ProviderError."""
        with patch.object(settings, "M1_PROVIDER", "groq"), patch.object(
            settings, "GROQ_API_KEY", ""
        ):
            with self.assertRaises(M1ProviderError) as cm:
                get_m1_provider()
            self.assertIn("GROQ_API_KEY is missing or empty", str(cm.exception))

    # ── TEST 13: Provider factory selection via M1_PROVIDER=groq ─────────────
    def test_13_provider_factory_selection(self) -> None:
        """M1_PROVIDER=groq resolves GroqAnalysisProvider with configured model and URL."""
        with patch.object(settings, "M1_PROVIDER", "groq"), patch.object(
            settings, "GROQ_API_KEY", "valid-groq-key"
        ), patch.object(settings, "GROQ_MODEL", "openai/gpt-oss-20b"), patch.object(
            settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1"
        ):
            prov = get_m1_provider()
            self.assertIsInstance(prov, GroqAnalysisProvider)
            self.assertEqual(prov.model, "openai/gpt-oss-20b")
            self.assertEqual(prov.base_url, "https://api.groq.com/openai/v1")

    # ── TEST 14: Exact model assertion ───────────────────────────────────────
    def test_14_exact_model_assertion(self) -> None:
        """Post request sends exact configured model ('openai/gpt-oss-20b')."""
        provider = GroqAnalysisProvider(
            api_key="my-key",
            model="openai/gpt-oss-20b",
            base_url="https://api.groq.com/openai/v1",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_valid_payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
            provider.analyze_answer(self.input_data)
            call_json = mock_post.call_args[1]["json"]
            self.assertEqual(call_json["model"], "openai/gpt-oss-20b")

    # ── TEST 15: Exact base URL assertion ────────────────────────────────────
    def test_15_exact_base_url_assertion(self) -> None:
        """Post request targets exact Groq completions endpoint."""
        provider = GroqAnalysisProvider(
            api_key="my-key",
            model="openai/gpt-oss-20b",
            base_url="https://api.groq.com/openai/v1",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_valid_payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
            provider.analyze_answer(self.input_data)
            call_url = mock_post.call_args[0][0]
            self.assertEqual(call_url, "https://api.groq.com/openai/v1/chat/completions")

    # ── TEST 16: Credential leakage protection ───────────────────────────────
    def test_16_credential_leakage_protection(self) -> None:
        """Sensitive credentials never appear in exceptions or error logs."""
        secret = "gsk_confidential_secret_value_123"
        provider = GroqAnalysisProvider(api_key=secret)
        req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection refused", request=req)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertNotIn(secret, str(cm.exception))

    # ── TEST 17: Structured output request assertion ─────────────────────────
    def test_17_structured_output_request_assertion(self) -> None:
        """Request payload strictly requires response_format={'type': 'json_object'}."""
        provider = GroqAnalysisProvider(api_key="my-key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_valid_payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
            provider.analyze_answer(self.input_data)
            call_json = mock_post.call_args[1]["json"]
            self.assertEqual(call_json["response_format"], {"type": "json_object"})


if __name__ == "__main__":
    unittest.main()
