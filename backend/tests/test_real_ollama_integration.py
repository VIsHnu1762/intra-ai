"""Real end-to-end integration test for Ollama Cloud M1 Intelligence in Intra AI.

This test is ONLY executed when:
    M1_PROVIDER=ollama
    and a genuine OLLAMA_API_KEY is configured in the environment.

When active, it executes live network calls to Ollama Cloud (gpt-oss:20b), verifying:
    Real Ollama Cloud API -> AnswerAnalysis -> InterviewAIContext -> MetaOrchestrator -> NextAction.
"""

import os
import unittest

from app.agents import ALEX_PROFILE, JORDAN_PROFILE, ActionType, AgentRegistry
from app.core.config import settings
from app.custom_llm.adapter import CustomLLMAdapter
from app.custom_llm.models import ChatCompletionRequest, ChatMessage
from app.interview_context.models import InterviewAIContext
from app.interview_context.store import interview_session_store
from app.interview_intelligence.analyzer import apply_analysis_to_context, m1_analyzer
from app.interview_intelligence.models import AnswerAnalysis, InterviewAnswerInput
from app.interview_intelligence.provider import (
    OllamaAnalysisProvider,
    get_m1_provider,
)
from app.models.enums import DifficultyLevel
from app.orchestrator.service import MetaOrchestrator


class TestRealOllamaIntegration(unittest.TestCase):
    """Real live network test suite for Ollama Cloud M1 integration. Skipped if unconfigured."""

    def setUp(self) -> None:
        provider_name = os.getenv("M1_PROVIDER", getattr(settings, "M1_PROVIDER", "mock")).strip().lower()
        api_key = os.getenv("OLLAMA_API_KEY") or getattr(settings, "OLLAMA_API_KEY", "")
        api_key = api_key.strip() if api_key else ""

        if provider_name != "ollama" or not api_key:
            self.skipTest(
                "Real Ollama integration test skipped because OLLAMA_API_KEY is unavailable "
                f"or M1_PROVIDER is '{provider_name}' (expected 'ollama')."
            )

        self.registry = AgentRegistry()
        self.orchestrator = MetaOrchestrator(registry=self.registry)
        self.provider = OllamaAnalysisProvider(api_key=api_key)

    # ── TEST 1: Real Ollama Live M1 Analysis Smoke Test ─────────────────────
    def test_01_real_ollama_m1_analysis(self) -> None:
        """Execute a live Ollama Cloud API call and verify structured AnswerAnalysis output."""
        context = InterviewAIContext(
            interview_id="sess-live-ollama-smoke",
            candidate_id="cand-live-ollama",
            current_round_id="round-technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )

        input_data = InterviewAnswerInput(
            answer_id="ans-live-ollama-01",
            question_text="Tell me about a backend project where you had to improve reliability or performance.",
            answer_text=(
                "I worked on an API service where response times increased as traffic grew. "
                "I added Redis caching for frequently accessed data and introduced database indexing. "
                "I also monitored latency and error rates after the change."
            ),
            context=context,
            agent_profile=ALEX_PROFILE,
        )

        # Execute live Ollama Cloud analysis
        analysis = self.provider.analyze_answer(input_data)

        # Verify AnswerAnalysis contract
        self.assertEqual(analysis.answer_id, "ans-live-ollama-01")
        self.assertIsInstance(analysis.overall_performance, float)
        self.assertGreaterEqual(analysis.overall_performance, 0.0)
        self.assertLessEqual(analysis.overall_performance, 1.0)
        self.assertIsInstance(analysis.confidence, float)
        self.assertGreaterEqual(analysis.confidence, 0.0)
        self.assertLessEqual(analysis.confidence, 1.0)
        self.assertIsInstance(analysis.vague, bool)
        self.assertIsInstance(analysis.contradiction_detected, bool)
        self.assertIsInstance(analysis.evidence, list)
        self.assertIsInstance(analysis.competency_findings, list)

        # Print safe diagnostics only (NO API KEYS)
        print(f"\n[LIVE_OLLAMA_SMOKE_RESULT] provider=ollama model={self.provider.model} status=success analysis_valid=true overall_performance={analysis.overall_performance} evidence_count={len(analysis.evidence)}")

    # ── TEST 2: Real Ollama to Meta-Orchestrator Decision ────────────────────
    def test_02_real_ollama_to_orchestrator(self) -> None:
        """Verify live Ollama M1 output mutates context and drives Meta-Orchestrator decision."""
        context = InterviewAIContext(
            interview_id="sess-live-ollama-orch",
            candidate_id="cand-live-ollama",
            current_round_id="round-technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )

        input_data = InterviewAnswerInput(
            answer_id="ans-live-ollama-orch-01",
            question_text="How did you scale your database when writes became the bottleneck?",
            answer_text=(
                "When database writes saturated the master instance, I introduced read replicas "
                "for read operations, implemented connection pooling with PgBouncer, and partitioned "
                "the high-volume audit logs table by range."
            ),
            context=context,
            agent_profile=ALEX_PROFILE,
        )

        # 1. Live M1 Analysis
        analysis = self.provider.analyze_answer(input_data)

        # 2. Context application
        apply_analysis_to_context(analysis, context)

        # 3. Meta-Orchestrator decision
        next_action = self.orchestrator.decide(context, analysis)
        self.assertIsNotNone(next_action)
        self.assertIn(
            next_action.action,
            [ActionType.ASK_QUESTION, ActionType.SWITCH_AGENT, ActionType.COMPLETE],
        )
        self.assertTrue(len(next_action.rationale or "") > 0)
        print(f"\n[LIVE_ORCHESTRATOR_RESULT] action={next_action.action.value} rationale={next_action.rationale[:60]}...")

    # ── TEST 3: Real Custom LLM Adapter Turn (Full Async Path) ──────────────
    def test_03_real_custom_llm_adapter_turn(self) -> None:
        """Verify full CustomLLMAdapter turn using real Ollama M1 provider over async pipeline."""
        import asyncio

        async def run_adapter_turn() -> None:
            adapter = CustomLLMAdapter(m1_analyzer=m1_analyzer)
            interview_id = "sess-live-adapter-turn"

            # Seed conversation
            req = ChatCompletionRequest(
                model="gpt-4o-mini",
                messages=[
                    ChatMessage(role="assistant", content="Could you explain how you designed your payment service?"),
                    ChatMessage(
                        role="user",
                        content=(
                            "I designed the payment service using idempotency keys in Redis to prevent "
                            "double charging, transactional outbox pattern in PostgreSQL for event publishing, "
                            "and exponential backoff retries when communicating with third-party payment gateways."
                        ),
                    ),
                ],
                stream=False,
            )

            headers = {
                "x-agora-session-id": interview_id,
                "x-agora-channel-name": interview_id,
                "x-agent-id": "alex",
            }

            turn = adapter.parse_turn(req, headers=headers)
            resp = await adapter.generate_response_async(turn)
            self.assertIsNotNone(resp)
            self.assertEqual(len(resp.choices), 1)
            content = resp.choices[0].message.content
            self.assertTrue(len(content) > 0)
            print(f"\n[LIVE_ADAPTER_TURN_RESULT] response_len={len(content)} sample={content[:80]}...")

        asyncio.run(run_adapter_turn())


if __name__ == "__main__":
    unittest.main()
