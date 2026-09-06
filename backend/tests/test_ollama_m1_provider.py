"""Unit tests for Ollama Cloud M1 Interview Intelligence provider in Intra AI."""

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
    M1ProviderError,
    OllamaAnalysisProvider,
    get_m1_provider,
)
from app.models.enums import DifficultyLevel


class TestOllamaM1Provider(unittest.TestCase):
    """Test suite for OllamaAnalysisProvider and provider selection mechanics."""

    def setUp(self) -> None:
        self.context = InterviewAIContext(
            interview_id="int-test-ollama",
            candidate_id="cand-ollama",
            current_round_id="round-ollama",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )
        self.input_data = InterviewAnswerInput(
            answer_id="ans-ollama-test-01",
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
                                "answer_id": "ans-ollama-test-01",
                                "overall_performance": 0.85,
                                "confidence": 0.90,
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
                                        "score": 8.5,
                                    }
                                ],
                                "competency_findings": [
                                    {
                                        "competency_id": "system_design",
                                        "assessment": "Solid understanding of caching patterns.",
                                        "confidence": 0.90,
                                        "evidence_ids": ["ev-1"],
                                    }
                                ],
                                "recommended_follow_up": "How did you manage cache stampede?",
                            }
                        ),
                    }
                }
            ]
        }

    # ── TEST 1: Successful Ollama response & AnswerAnalysis parsing ──────────
    def test_01_successful_ollama_response_parsing(self) -> None:
        """Ollama OpenAI-compatible response parses into valid AnswerAnalysis."""
        provider = OllamaAnalysisProvider(
            api_key="test-key",
            model="gpt-oss:20b",
            base_url="https://ollama.com/v1",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_valid_payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            analysis = provider.analyze_answer(self.input_data)
            self.assertIsInstance(analysis, AnswerAnalysis)
            self.assertEqual(analysis.answer_id, "ans-ollama-test-01")
            self.assertEqual(analysis.overall_performance, 0.85)
            self.assertEqual(analysis.confidence, 0.90)
            self.assertFalse(analysis.vague)
            self.assertEqual(len(analysis.evidence), 1)
            self.assertEqual(len(analysis.competency_findings), 1)
            # Evidence enrichment check
            self.assertEqual(analysis.evidence[0].source_agent_id, "alex")
            self.assertEqual(analysis.evidence[0].round_id, "round-ollama")

    # ── TEST 2: Answer ID preservation when missing from model output ────────
    def test_02_answer_id_preservation(self) -> None:
        """answer_id is preserved from input_data if omitted by model."""
        provider = OllamaAnalysisProvider(api_key="test-key")
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "overall_performance": 0.75,
                                "confidence": 0.80,
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
            self.assertEqual(analysis.answer_id, "ans-ollama-test-01")

    # ── TEST 3: Malformed JSON output raises M1ProviderError ─────────────────
    def test_03_malformed_json_raises_provider_error(self) -> None:
        """Malformed or unparseable JSON from Ollama raises M1ProviderError."""
        provider = OllamaAnalysisProvider(api_key="test-key")
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

    # ── TEST 4: Invalid schema / missing required fields raises error ────────
    def test_04_invalid_schema_missing_required_fields(self) -> None:
        """Missing required fields in AnswerAnalysis schema raises M1ProviderError."""
        provider = OllamaAnalysisProvider(api_key="test-key")
        # Missing overall_performance and confidence
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

    # ── TEST 5: Invalid evidence reference is rejected ───────────────────────
    def test_05_invalid_evidence_reference_rejected(self) -> None:
        """CompetencyFinding referencing nonexistent evidence_id is rejected."""
        provider = OllamaAnalysisProvider(api_key="test-key")
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
                                        "evidence_ids": ["ev-nonexistent"],  # Invalid reference
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

    # ── TEST 6: HTTP 401/403 raises sanitized PERMISSION_DENIED ──────────────
    def test_06_http_401_403_raises_permission_denied_sanitized(self) -> None:
        """HTTP 401/403 raises PERMISSION_DENIED without leaking the API key."""
        sensitive_key = "super-secret-key-do-not-leak"
        provider = OllamaAnalysisProvider(api_key=sensitive_key)
        req = httpx.Request("POST", "https://ollama.com/v1/chat/completions")
        resp = httpx.Response(401, request=req)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("Unauthorized", request=req, response=resp)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            err_msg = str(cm.exception)
            self.assertIn("PERMISSION_DENIED", err_msg)
            self.assertNotIn(sensitive_key, err_msg)

    # ── TEST 7: HTTP 429 raises RESOURCE_EXHAUSTED ───────────────────────────
    def test_07_http_429_raises_resource_exhausted(self) -> None:
        """HTTP 429 raises RESOURCE_EXHAUSTED without stalling voice runtime."""
        provider = OllamaAnalysisProvider(api_key="test-key")
        req = httpx.Request("POST", "https://ollama.com/v1/chat/completions")
        resp = httpx.Response(429, request=req)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("Too Many Requests", request=req, response=resp)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("RESOURCE_EXHAUSTED", str(cm.exception))

    # ── TEST 8: HTTP 5xx raises SERVICE_UNAVAILABLE ──────────────────────────
    def test_08_http_5xx_raises_service_unavailable(self) -> None:
        """HTTP 500/502/503/504 raises SERVICE_UNAVAILABLE."""
        provider = OllamaAnalysisProvider(api_key="test-key")
        req = httpx.Request("POST", "https://ollama.com/v1/chat/completions")
        resp = httpx.Response(502, request=req)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("Bad Gateway", request=req, response=resp)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("SERVICE_UNAVAILABLE", str(cm.exception))

    # ── TEST 9: Timeout raises NETWORK_TIMEOUT ───────────────────────────────
    def test_09_timeout_raises_network_timeout(self) -> None:
        """Request timeout raises NETWORK_TIMEOUT."""
        provider = OllamaAnalysisProvider(api_key="test-key")
        req = httpx.Request("POST", "https://ollama.com/v1/chat/completions")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Connection timed out", request=req)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("NETWORK_TIMEOUT", str(cm.exception))

    # ── TEST 10: Provider selection via M1_PROVIDER=ollama ───────────────────
    def test_10_provider_selection_m1_provider_ollama(self) -> None:
        """M1_PROVIDER=ollama resolves OllamaAnalysisProvider with configured model and URL."""
        with patch.object(settings, "M1_PROVIDER", "ollama"), patch.object(
            settings, "OLLAMA_API_KEY", "valid-test-key"
        ), patch.object(settings, "OLLAMA_MODEL", "gpt-oss:20b"), patch.object(
            settings, "OLLAMA_BASE_URL", "https://ollama.com/v1"
        ):
            prov = get_m1_provider()
            self.assertIsInstance(prov, OllamaAnalysisProvider)
            self.assertEqual(prov.model, "gpt-oss:20b")
            self.assertEqual(prov.base_url, "https://ollama.com/v1")

    # ── TEST 11: Missing OLLAMA_API_KEY raises M1ProviderError ───────────────
    def test_11_ollama_missing_key_raises_error(self) -> None:
        """Ollama without configured key raises M1ProviderError without silent fallback."""
        with patch.object(settings, "M1_PROVIDER", "ollama"), patch.object(
            settings, "OLLAMA_API_KEY", ""
        ):
            with self.assertRaises(M1ProviderError) as cm:
                get_m1_provider()
            self.assertIn("OLLAMA_API_KEY is missing or empty", str(cm.exception))

    # ── TEST 12: Gemini provider still selectable ────────────────────────────
    def test_12_gemini_provider_still_selectable(self) -> None:
        """Gemini remains selectable via M1_PROVIDER=gemini for full portability."""
        with patch.object(settings, "M1_PROVIDER", "gemini"), patch.object(
            settings, "GEMINI_API_KEY", "gemini-key-test"
        ), patch.object(settings, "GEMINI_MODEL", "gemini-2.5-flash"):
            prov = get_m1_provider()
            self.assertIsInstance(prov, GeminiAnalysisProvider)
            self.assertEqual(prov.model, "gemini-2.5-flash")

    # ── TEST 13: API key is never leaked in logs or error messages ───────────
    def test_13_api_key_never_leaked_in_logs_or_errors(self) -> None:
        """Sensitive credentials never appear in exceptions or error logs."""
        secret = "secret-token-abcdef123456"
        provider = OllamaAnalysisProvider(api_key=secret)
        req = httpx.Request("POST", "https://ollama.com/v1/chat/completions")

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection refused", request=req)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertNotIn(secret, str(cm.exception))

    # ── TEST 14: Exact model and base URL used in HTTP request ───────────────
    def test_14_exact_model_and_base_url_used(self) -> None:
        """Post request sends exact configured model, base_url, and Bearer token."""
        provider = OllamaAnalysisProvider(
            api_key="my-key",
            model="gpt-oss:20b",
            base_url="https://ollama.com/v1",
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_valid_payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
            provider.analyze_answer(self.input_data)
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            call_headers = mock_post.call_args[1]["headers"]
            call_json = mock_post.call_args[1]["json"]

            self.assertEqual(call_url, "https://ollama.com/v1/chat/completions")
            self.assertEqual(call_headers["Authorization"], "Bearer my-key")
            self.assertEqual(call_json["model"], "gpt-oss:20b")
            self.assertEqual(call_json["response_format"], {"type": "json_object"})

    # ── TEST 15: Markdown code fences in response are stripped safely ────────
    def test_15_markdown_code_fences_stripped(self) -> None:
        """Model responses wrapped in ```json ... ``` code fences parse cleanly."""
        provider = OllamaAnalysisProvider(api_key="test-key")
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "```json\n" + json.dumps(
                            {
                                "answer_id": "ans-fence-01",
                                "overall_performance": 0.8,
                                "confidence": 0.9,
                                "vague": False,
                                "contradiction_detected": False,
                                "missing_information": [],
                                "evidence": [],
                                "competency_findings": [],
                            }
                        ) + "\n```",
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            analysis = provider.analyze_answer(self.input_data)
            self.assertEqual(analysis.answer_id, "ans-fence-01")
            self.assertEqual(analysis.overall_performance, 0.8)


if __name__ == "__main__":
    unittest.main()
