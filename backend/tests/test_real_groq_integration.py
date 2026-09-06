"""Real end-to-end integration and latency benchmark for Groq M1 Intelligence in Intra AI.

This test suite is ONLY executed when:
    M1_PROVIDER=groq
    and a genuine GROQ_API_KEY is configured in the environment.

When active, it executes live network calls to Groq (openai/gpt-oss-20b), verifying:
    Real Groq API -> AnswerAnalysis -> InterviewAIContext -> MetaOrchestrator -> NextAction
and benchmarks realtime latency across multiple identical turns.
"""

import os
import statistics
import time
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
    GroqAnalysisProvider,
    M1ProviderError,
    get_m1_provider,
)
from app.models.enums import DifficultyLevel
from app.orchestrator.service import MetaOrchestrator


class TestRealGroqIntegration(unittest.TestCase):
    """Real live network test suite and benchmark for Groq M1 integration. Skipped if unconfigured."""

    def setUp(self) -> None:
        provider_name = os.getenv("M1_PROVIDER", getattr(settings, "M1_PROVIDER", "mock")).strip().lower()
        api_key = os.getenv("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", "")
        api_key = api_key.strip() if api_key else ""

        if provider_name != "groq" or not api_key:
            self.skipTest(
                "Real Groq integration test skipped because GROQ_API_KEY is unavailable "
                f"or M1_PROVIDER is '{provider_name}' (expected 'groq')."
            )

        self.registry = AgentRegistry()
        self.orchestrator = MetaOrchestrator(registry=self.registry)
        self.provider = GroqAnalysisProvider(api_key=api_key)

    def tearDown(self) -> None:
        # Respect Groq 8,000 TPM limit between live tests
        time.sleep(8)

    # ── TEST 1: Real Groq Live M1 Analysis Smoke Test ───────────────────────
    def test_01_real_groq_m1_analysis(self) -> None:
        """Execute a live Groq API call and verify structured AnswerAnalysis output."""
        context = InterviewAIContext(
            interview_id="sess-live-groq-smoke",
            candidate_id="cand-live-groq",
            current_round_id="round-technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )

        input_data = InterviewAnswerInput(
            answer_id="ans-live-groq-01",
            question_text="Tell me about a backend project where you had to improve reliability or performance.",
            answer_text=(
                "I worked on an API service where response times increased as traffic grew. "
                "I added Redis caching for frequently accessed data and introduced database indexing. "
                "I also monitored latency and error rates after the change."
            ),
            context=context,
            agent_profile=ALEX_PROFILE,
        )

        t0 = time.perf_counter()
        analysis = self.provider.analyze_answer(input_data)
        t1 = time.perf_counter()
        total_latency_ms = (t1 - t0) * 1000

        # Verify AnswerAnalysis contract
        self.assertEqual(analysis.answer_id, "ans-live-groq-01")
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

        # Print safe diagnostics only (NO SECRETS)
        print(
            f"\n[GROQ_M1_SMOKE_RESULT] "
            f"provider=groq model={self.provider.model} "
            f"total_latency_ms={total_latency_ms:.1f} "
            f"analysis_valid=true "
            f"overall_performance={analysis.overall_performance} "
            f"evidence_count={len(analysis.evidence)}"
        )

    # ── TEST 2: Real Groq to Meta-Orchestrator Decision ─────────────────────
    def test_02_real_groq_to_orchestrator(self) -> None:
        """Verify live Groq M1 output mutates context and drives Meta-Orchestrator decision."""
        context = InterviewAIContext(
            interview_id="sess-live-groq-orch",
            candidate_id="cand-live-groq",
            current_round_id="round-technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )

        input_data = InterviewAnswerInput(
            answer_id="ans-live-groq-orch-01",
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
        t0 = time.perf_counter()
        analysis = self.provider.analyze_answer(input_data)
        t1 = time.perf_counter()

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
        print(
            f"\n[GROQ_ORCHESTRATOR_RESULT] "
            f"m1_latency_ms={(t1 - t0)*1000:.1f} "
            f"action={next_action.action.value} "
            f"rationale={next_action.rationale[:60]}..."
        )

    # ── TEST 3: Real Custom LLM Adapter Turn (Pure Async Path) ──────────────
    def test_03_real_custom_llm_adapter_turn(self) -> None:
        """Verify full CustomLLMAdapter turn using real Groq M1 provider over async pipeline."""
        import asyncio

        async def run_adapter_turn() -> None:
            adapter = CustomLLMAdapter(m1_analyzer=m1_analyzer)
            interview_id = "sess-live-groq-adapter-turn"

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
            t0 = time.perf_counter()
            resp = await adapter.generate_response_async(turn)
            t1 = time.perf_counter()
            self.assertIsNotNone(resp)
            self.assertEqual(len(resp.choices), 1)
            content = resp.choices[0].message.content
            self.assertTrue(len(content) > 0)
            print(
                f"\n[GROQ_ADAPTER_TURN_RESULT] "
                f"total_turn_ms={(t1 - t0)*1000:.1f} "
                f"response_len={len(content)} "
                f"sample={content[:80]}..."
            )

        asyncio.run(run_adapter_turn())

    # ── TEST 4: 5-Turn Latency Benchmark (Fair Comparison with Ollama) ───────
    def test_04_groq_latency_benchmark_5_turns(self) -> None:
        """Benchmark 5 identical live M1 inference requests on Groq gpt-oss-20b."""
        context = InterviewAIContext(
            interview_id="sess-groq-bench",
            candidate_id="cand-groq-bench",
            current_round_id="round-technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )

        input_data = InterviewAnswerInput(
            answer_id="ans-groq-bench-01",
            question_text="Tell me about a backend project where you had to improve reliability or performance.",
            answer_text=(
                "I worked on an API service where response times increased as traffic grew. "
                "I added Redis caching for frequently accessed data and introduced database indexing. "
                "I also monitored latency and error rates after the change."
            ),
            context=context,
            agent_profile=ALEX_PROFILE,
        )

        latencies_ms: list[float] = []
        num_runs = 5
        print(f"\n--- Starting Groq 5-Turn Latency Benchmark (Model: {self.provider.model}) ---")

        for i in range(1, num_runs + 1):
            for attempt in range(3):
                try:
                    t0 = time.perf_counter()
                    analysis = self.provider.analyze_answer(input_data)
                    t1 = time.perf_counter()
                    lat_ms = (t1 - t0) * 1000
                    latencies_ms.append(lat_ms)
                    self.assertIsInstance(analysis, AnswerAnalysis)
                    print(f"Run {i}/{num_runs}: {lat_ms:.1f} ms | performance={analysis.overall_performance} | evidence={len(analysis.evidence)}")
                    if i < num_runs:
                        time.sleep(13)  # Respect 8,000 TPM limit
                    break
                except M1ProviderError as e:
                    if "RESOURCE_EXHAUSTED" in str(e) and attempt < 2:
                        print(f"Rate limited (8,000 TPM ceiling reached). Waiting 15s before retry {attempt + 1}...")
                        time.sleep(15)
                    else:
                        raise

        avg_lat = statistics.mean(latencies_ms)
        min_lat = min(latencies_ms)
        max_lat = max(latencies_ms)
        # Median (P50)
        sorted_lats = sorted(latencies_ms)
        p50 = statistics.median(sorted_lats)
        # P95 (using 95th percentile index)
        p95_idx = int(round(0.95 * len(sorted_lats))) - 1
        p95 = sorted_lats[max(0, min(p95_idx, len(sorted_lats) - 1))]

        print(f"\n[GROQ_M1_BENCHMARK_SUMMARY]")
        print(f"Provider: Groq")
        print(f"Model: {self.provider.model}")
        print(f"Runs: {num_runs}")
        print(f"Avg: {avg_lat:.1f} ms ({avg_lat/1000:.2f} s)")
        print(f"P50: {p50:.1f} ms ({p50/1000:.2f} s)")
        print(f"P95: {p95:.1f} ms ({p95/1000:.2f} s)")
        print(f"Min: {min_lat:.1f} ms ({min_lat/1000:.2f} s)")
        print(f"Max: {max_lat:.1f} ms ({max_lat/1000:.2f} s)")
        print(f"--- Benchmark Complete ---\n")

        # Assertion: Groq should comfortably execute under 10 seconds (our timeout is 20s)
        self.assertLess(avg_lat, 10000, f"Expected average latency under 10s on Groq, got {avg_lat:.1f}ms")


if __name__ == "__main__":
    unittest.main()
