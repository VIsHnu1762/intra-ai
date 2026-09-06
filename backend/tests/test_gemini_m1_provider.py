"""Unit tests for Gemini M1 Interview Intelligence provider in Intra AI."""

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
    get_m1_provider,
)
from app.models.enums import DifficultyLevel


class TestGeminiM1Provider(unittest.TestCase):
    """Test suite for GeminiAnalysisProvider and provider selection mechanics."""

    def setUp(self) -> None:
        self.context = InterviewAIContext(
            interview_id="int-test-gemini",
            candidate_id="cand-gemini",
            current_round_id="round-gemini",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )
        self.input_data = InterviewAnswerInput(
            answer_id="ans-gemini-test-01",
            question_text="How did you build your distributed ledger?",
            answer_text=(
                "I designed a distributed payment ledger using event sourcing and CQRS "
                "with PostgreSQL as the write model and Elasticsearch for queries. "
                "We handled around 5,000 writes per second."
            ),
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

    # ── TEST 1: Default / Safe provider is mock ──────────────────────────────
    def test_01_default_provider_is_mock(self) -> None:
        """Safe automated-test default remains DeterministicMockM1Provider."""
        with patch.object(settings, "M1_PROVIDER", "mock"):
            prov = get_m1_provider()
            self.assertIsInstance(prov, DeterministicMockM1Provider)

    # ── TEST 2: M1_PROVIDER=gemini resolves GeminiAnalysisProvider ──────────
    def test_02_gemini_provider_selection(self) -> None:
        """M1_PROVIDER=gemini explicitly resolves GeminiAnalysisProvider."""
        with patch.object(settings, "M1_PROVIDER", "gemini"), patch.object(
            settings, "GEMINI_API_KEY", "fake-test-key-for-unit-test"
        ), patch.object(settings, "GEMINI_MODEL", "gemini-2.5-flash"):
            prov = get_m1_provider()
            self.assertIsInstance(prov, GeminiAnalysisProvider)
            self.assertEqual(prov.model, "gemini-2.5-flash")


    # ── TEST 3: Unknown provider raises M1ProviderError ──────────────────────
    def test_03_unknown_provider_raises_error(self) -> None:
        """Unknown M1_PROVIDER value raises explicit M1ProviderError, not silent fallback."""
        with self.assertRaises(M1ProviderError):
            get_m1_provider("unknown_provider_xyz")

    # ── TEST 4: Gemini without API key raises M1ProviderError ────────────────
    def test_04_gemini_without_api_key_raises_error(self) -> None:
        """Gemini without configured key raises M1ProviderError with zero silent fallback."""
        with patch.object(settings, "M1_PROVIDER", "gemini"), patch.object(
            settings, "GEMINI_API_KEY", ""
        ):
            with self.assertRaises(M1ProviderError) as cm:
                get_m1_provider()
            self.assertIn("GEMINI_API_KEY is missing or empty", str(cm.exception))

    # ── TEST 5: Gemini retains original answer_id ───────────────────────────
    def test_05_gemini_retains_answer_id(self) -> None:
        """Gemini output preserves the input answer_id even if omitted by the model."""
        mock_response_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "overall_performance": 0.85,
                                        "confidence": 0.90,
                                        "vague": False,
                                        "contradiction_detected": False,
                                        "missing_information": ["Partition handling trade-offs"],
                                        "evidence": [
                                            {
                                                "id": "ev-1",
                                                "competency": "system_design",
                                                "signal": "Built event-sourced payment ledger.",
                                                "score": 8.5,
                                            }
                                        ],
                                        "competency_findings": [
                                            {
                                                "competency_id": "system_design",
                                                "assessment": "Strong architecture understanding.",
                                                "confidence": 0.90,
                                                "evidence_ids": ["ev-1"],
                                            }
                                        ],
                                        "recommended_follow_up": "How did you manage partition tolerance?",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }

        provider = GeminiAnalysisProvider(api_key="fake-test-key", model="gemini-2.5-flash")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_json

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            analysis = provider.analyze_answer(self.input_data)
            self.assertEqual(analysis.answer_id, "ans-gemini-test-01")
            self.assertEqual(analysis.overall_performance, 0.85)
            self.assertEqual(len(analysis.evidence), 1)

    # ── TEST 6: Gemini JSON maps into existing AnswerAnalysis ────────────────
    def test_06_gemini_json_maps_to_answer_analysis_schema(self) -> None:
        """Valid Gemini JSON parses strictly into the existing AnswerAnalysis Pydantic model."""
        provider = GeminiAnalysisProvider(api_key="fake-test-key")
        mock_response_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "answer_id": "ans-gemini-test-01",
                                        "overall_performance": 0.88,
                                        "confidence": 0.95,
                                        "vague": False,
                                        "contradiction_detected": False,
                                        "missing_information": [],
                                        "evidence": [],
                                        "competency_findings": [],
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_json

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            analysis = provider.analyze_answer(self.input_data)
            self.assertIsInstance(analysis, AnswerAnalysis)
            self.assertEqual(analysis.overall_performance, 0.88)
            self.assertFalse(analysis.vague)

    # ── TEST 7: Malformed Gemini JSON raises explicit M1ProviderError ────────
    def test_07_malformed_gemini_json_raises_provider_error(self) -> None:
        """Malformed or unparseable JSON from Gemini raises M1ProviderError."""
        provider = GeminiAnalysisProvider(api_key="fake-test-key")
        mock_response_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "NOT VALID JSON at all {missing_bracket"}
                        ]
                    }
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response_json

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)
            self.assertIn("INVALID_RESPONSE", str(cm.exception))

    # ── TEST 8: Gemini HTTP authentication/API failure raises M1ProviderError ─
    def test_08_gemini_auth_failure_raises_sanitized_error(self) -> None:
        """HTTP 401/403 errors raise sanitized PERMISSION_DENIED without leaking credentials."""
        provider = GeminiAnalysisProvider(api_key="secret-api-key-value-12345")

        req = httpx.Request("POST", "https://generativelanguage.googleapis.com/")
        resp = httpx.Response(403, request=req)

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.HTTPStatusError("Forbidden", request=req, response=resp)):
            with self.assertRaises(M1ProviderError) as cm:
                provider.analyze_answer(self.input_data)

            err_msg = str(cm.exception)
            self.assertIn("PERMISSION_DENIED", err_msg)
            # Guarantee API credentials never appear in error message
            self.assertNotIn("secret-api-key", err_msg)

    # ── TEST 9: No Gemini -> mock silent fallback ────────────────────────────
    def test_09_no_silent_fallback_to_mock(self) -> None:
        """When Gemini encounters a failure, M1ProviderError is raised, never silent mock fallback."""
        with patch.object(settings, "M1_PROVIDER", "gemini"), patch.object(
            settings, "GEMINI_API_KEY", "fake-key"
        ):
            prov = get_m1_provider()
            self.assertIsInstance(prov, GeminiAnalysisProvider)

            # Provider should raise M1ProviderError on timeout, never return mock AnswerAnalysis
            req = httpx.Request("POST", "https://generativelanguage.googleapis.com/")
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("Read timed out", request=req)):
                with self.assertRaises(M1ProviderError) as cm:
                    prov.analyze_answer(self.input_data)
                self.assertIn("NETWORK_TIMEOUT", str(cm.exception))

    # ── TEST 10: Existing mock-based tests continue passing ──────────────────
    def test_10_existing_mock_provider_operates_identically(self) -> None:
        """DeterministicMockM1Provider remains fully functional and unchanged."""
        mock_prov = DeterministicMockM1Provider()
        analysis = mock_prov.analyze_answer(self.input_data)
        self.assertEqual(analysis.answer_id, "ans-gemini-test-01")
        self.assertGreater(analysis.overall_performance, 0.5)


if __name__ == "__main__":
    unittest.main()
