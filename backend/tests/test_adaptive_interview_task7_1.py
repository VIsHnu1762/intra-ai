"""Task 7.1 — Comprehensive Integration & Adaptive Verification Test Suite.

Tests verify:
1. Real M1 provider selection ('mock' vs 'openai', explicit error on missing key)
2. First-question persona correctness (Alex technical vs Jordan product)
3. Strong answer -> evidence-driven deeper question (probes failure scenarios & recovery)
4. Weak answer -> simpler question (probes fundamentals at lower difficulty)
5. Vague answer -> clarification (requests concrete components & metrics)
6. Contradiction -> clarification
7. Missing information -> targeted probe
8. Sufficient coverage -> next competency
9. Alex -> Jordan context preservation (same InterviewAIContext survives handoff)
10. Jordan product-domain question (evaluates customer problem, prioritization, metrics)
11. No technical-only Jordan question (strictly in product domain)
12. N-agent routing (registry-driven)
13. No hardcoded persona transition
14. Context isolation (isolated session contexts)
15. Multiple-turn state persistence
16. SSE compatibility
17. Provider failure handling
18. Orchestrator failure handling
19. Empty answer handling
20. Agora connectivity boundary verification
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from app.agents.alex import ALEX_PROFILE
from app.agents.jordan import JORDAN_PROFILE
from app.agents.models import ActionType, AgentProfile, DifficultyLevel, NextAction
from app.agents.registry import AgentRegistry
from app.agent_context.builder import AgentTurnContextBuilder
from app.core.config import settings
from app.custom_llm.adapter import (
    CustomLLMAdapter,
    SessionContextProvider,
    generate_opening_question,
    is_first_turn_or_greeting,
)
from app.custom_llm.models import ChatCompletionRequest, ChatMessage, InterviewTurn
from app.interview_context.models import EvidenceItem, InterviewAIContext
from app.interview_context.store import InterviewSessionStore
from app.interview_intelligence.analyzer import M1InterviewAnalyzer, apply_analysis_to_context
from app.interview_intelligence.models import (
    AnswerAnalysis,
    CompetencyFinding,
    InterviewAnswerInput,
)
from app.interview_intelligence.provider import (
    DeterministicMockM1Provider,
    M1ProviderError,
    OpenAIAnalysisProvider,
    extract_key_subject,
    get_m1_provider,
)
from app.orchestrator.service import MetaOrchestrator
from app.knowledge_graph.memory_service import CandidateMemoryService
from app.knowledge_graph.repository import InMemoryKnowledgeGraphRepository
from app.knowledge_graph.service import KnowledgeGraphPersistenceService


class TestAdaptiveInterviewTask71(unittest.TestCase):
    """Rigorous verification of real adaptive reasoning and persona behavior."""

    def setUp(self) -> None:
        # This suite asserts deterministic fixture wording. Real provider calls
        # are covered separately; a developer .env must not turn these cases
        # into live Groq requests or reuse candidate data in a shared graph.
        orchestrator_key = patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
        orchestrator_key.start()
        self.addCleanup(orchestrator_key.stop)
        graph_repository = InMemoryKnowledgeGraphRepository()
        self.session_store = InterviewSessionStore()
        self.registry = AgentRegistry(register_defaults=True)
        self.provider = DeterministicMockM1Provider()
        self.m1_analyzer = M1InterviewAnalyzer(provider=self.provider)
        self.orchestrator = MetaOrchestrator(registry=self.registry)
        self.context_provider = SessionContextProvider(
            store=self.session_store,
        )
        self.adapter = CustomLLMAdapter(
            session_store=self.session_store,
            registry=self.registry,
            m1_analyzer=self.m1_analyzer,
            orchestrator=self.orchestrator,
            context_provider=self.context_provider,
            kg_service=KnowledgeGraphPersistenceService(graph_repository),
            context_builder=AgentTurnContextBuilder(
                memory_service=CandidateMemoryService(graph_repository), registry=self.registry),
        )

    # ── TEST 1: Real M1 Provider Selection ──────────────────────────────────
    def test_01_real_provider_selection(self) -> None:
        """Explicitly selects mock or openai provider; raises on missing key without silent fallback."""
        # 1. Mock provider explicitly
        mock_prov = get_m1_provider("mock")
        self.assertIsInstance(mock_prov, DeterministicMockM1Provider)

        # 2. Unknown provider raises M1ProviderError
        with self.assertRaises((M1ProviderError, ValueError)):
            get_m1_provider("non_existent_provider")

        # 3. OpenAI provider with placeholder or empty key raises M1ProviderError
        with patch.object(settings, "OPENAI_API_KEY", "sk-placeholder-openai-api-key"):
            with self.assertRaises(M1ProviderError):
                get_m1_provider("openai")

        # 4. OpenAI provider with valid key returns OpenAIAnalysisProvider
        with patch.object(settings, "OPENAI_API_KEY", "sk-actual-valid-openai-key"):
            prov = get_m1_provider("openai")
            self.assertIsInstance(prov, OpenAIAnalysisProvider)

    # ── TEST 2: First-Question Persona Correctness ──────────────────────────
    def test_02_first_question_persona_correctness(self) -> None:
        """Alex opening is technical/system-design; Jordan opening is product/customer problem."""
        ctx_alex = InterviewAIContext(
            interview_id="sess-first-alex",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="alex",
        )
        alex_q = generate_opening_question(ALEX_PROFILE, ctx_alex)
        self.assertIn("Alex", alex_q)
        self.assertIn(ALEX_PROFILE.role, alex_q)
        self.assertIn("personally build", alex_q.lower())
        self.assertEqual(alex_q.count("?"), 1)

        ctx_jordan = InterviewAIContext(
            interview_id="sess-first-jordan",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="jordan",
        )
        jordan_q = generate_opening_question(JORDAN_PROFILE, ctx_jordan)
        self.assertIn("Jordan", jordan_q)
        self.assertIn(JORDAN_PROFILE.role, jordan_q)
        self.assertIn("main user", jordan_q.lower())
        self.assertEqual(jordan_q.count("?"), 1)

    # ── TEST 3: Strong Answer -> Evidence-Driven Deeper Question ─────────────
    def test_03_strong_answer_probes_deeper_failure_modes(self) -> None:
        """Strong architecture answer without trade-offs produces targeted probe on failure recovery."""
        turn = InterviewTurn(
            session_id="sess-strong-1",
            messages=[
                ChatMessage(role="assistant", content="Describe a complex backend system you designed."),
                ChatMessage(
                    role="user",
                    content=(
                        "I designed a distributed payment ledger using event sourcing and CQRS "
                        "with PostgreSQL as the write model and Elasticsearch for queries. "
                        "We handled 5,000 writes per second."
                    ),
                ),
            ],
            context=InterviewAIContext(
                interview_id="sess-strong-1",
                candidate_id="cand-1",
                current_round_id="round-1",
                current_agent_id="alex",
                missing_competencies=["system_design", "scalability"],
            ),
        )
        response, next_action = asyncio.run(self.adapter.process_turn_async(turn))
        self.assertIsNotNone(next_action)
        self.assertEqual(next_action.action, ActionType.ASK_QUESTION)
        self.assertEqual(next_action.target_agent_id, "alex")
        # Assert question references candidate's payment ledger and probes failure recovery
        self.assertTrue(
            "failure" in response.lower() or "trade-off" in response.lower() or "recovery" in response.lower()
            or ("servers cannot communicate" in response.lower() and "conflicting writes" in response.lower()),
            f"Expected failure/recovery probe in response, got: {response}",
        )
        self.assertIn("payment ledger", response.lower())

    # ── TEST 4: Weak Answer -> Simpler Question on Fundamentals ─────────────
    def test_04_weak_answer_probes_fundamentals(self) -> None:
        """Weak answer reduces difficulty from HARD to MEDIUM to test core fundamentals."""
        ctx = InterviewAIContext(
            interview_id="sess-weak-1",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="alex",
            difficulty=DifficultyLevel.HARD,
            missing_competencies=["system_design"],
        )
        turn = InterviewTurn(
            session_id="sess-weak-1",
            messages=[
                ChatMessage(role="assistant", content="How do you handle system failure modes?"),
                ChatMessage(
                    role="user",
                    content="I didn't consider failure modes because our servers never fail and we just reboot when there is an issue.",
                ),
            ],
            context=ctx,
        )
        response, next_action = asyncio.run(self.adapter.process_turn_async(turn))
        self.assertIsNotNone(next_action)
        self.assertEqual(next_action.action, ActionType.ASK_QUESTION)
        self.assertEqual(next_action.difficulty, DifficultyLevel.MEDIUM)
        self.assertEqual(next_action.competency, "system_design")
        self.assertIn("server failure", response.lower())
        self.assertIn("database write", response.lower())
        self.assertEqual(response.count("?"), 1)

    # ── TEST 5: Vague Answer -> Clarification ───────────────────────────────
    def test_05_vague_answer_probes_concrete_details(self) -> None:
        """Vague answers lower difficulty and request one concrete example."""
        ctx = InterviewAIContext(
            interview_id="sess-vague-1",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design"],
        )
        turn = InterviewTurn(
            session_id="sess-vague-1",
            messages=[
                ChatMessage(role="assistant", content="Tell me about your system design experience."),
                ChatMessage(role="user", content="We basically used some stuff and things worked pretty good."),
            ],
            context=ctx,
        )
        response, next_action = asyncio.run(self.adapter.process_turn_async(turn))
        self.assertIsNotNone(next_action)
        self.assertEqual(next_action.action, ActionType.ASK_QUESTION)
        self.assertEqual(next_action.difficulty, DifficultyLevel.EASY)
        self.assertEqual(next_action.competency, "system_design")
        self.assertEqual(response.count("?"), 1)
        self.assertIn("web app", response.lower())
        self.assertIn("store", response.lower())
        self.assertIn("user data", response.lower())
        self.assertLessEqual(len(response.split()), 32)

    # ── TEST 6: Contradiction -> Clarification ──────────────────────────────
    def test_06_contradiction_requests_clarification(self) -> None:
        """Detects contradiction against evaluated competencies and asks for clarification."""
        ctx = InterviewAIContext(
            interview_id="sess-contra-1",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="alex",
            difficulty=DifficultyLevel.HARD,
            evaluated_competencies=["system_design"],
            missing_competencies=["scalability"],
        )
        turn = InterviewTurn(
            session_id="sess-contra-1",
            messages=[
                ChatMessage(role="assistant", content="How do you handle database scaling in system design?"),
                ChatMessage(role="user", content="I have no experience with system_design or relational databases."),
            ],
            context=ctx,
        )
        response, next_action = asyncio.run(self.adapter.process_turn_async(turn))
        self.assertIsNotNone(next_action)
        self.assertEqual(next_action.action, ActionType.ASK_QUESTION)
        self.assertIn("clarify", response.lower())

    # ── TEST 7: Missing Information -> Targeted Probe ───────────────────────
    def test_07_missing_information_targeted_probe(self) -> None:
        """Missing information in AnswerAnalysis directly shapes the next question."""
        ctx = InterviewAIContext(
            interview_id="sess-miss-1",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["scalability"],
        )
        analysis = AnswerAnalysis(
            answer_id="ans-miss-1",
            overall_performance=0.82,
            confidence=0.90,
            vague=False,
            contradiction_detected=False,
            missing_information=["Cache invalidation and replication lag under partition scenarios"],
            evidence=[EvidenceItem(id="ev-1", competency="scalability", signal="Redis cache clustering.")],
            competency_findings=[CompetencyFinding(competency_id="scalability", assessment="Good progress.", confidence=0.90)],
        )
        action = self.orchestrator.decide(ctx, analysis)
        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertIn("cache invalidation", action.question_text.lower())

    # ── TEST 8: Sufficient Coverage -> Next Competency ──────────────────────
    def test_08_sufficient_coverage_advances_competency(self) -> None:
        """When current competency has verified depth, advances to remaining agent competency."""
        ctx = InterviewAIContext(
            interview_id="sess-adv-1",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "debugging"],
        )
        analysis = AnswerAnalysis(
            answer_id="ans-adv-1",
            overall_performance=0.92,
            confidence=0.95,
            vague=False,
            contradiction_detected=False,
            missing_information=[],  # Verified depth
            evidence=[EvidenceItem(id="ev-1", competency="system_design", signal="Complete failure recovery.")],
            competency_findings=[CompetencyFinding(competency_id="system_design", assessment="Deep mastery.", confidence=0.95)],
        )
        apply_analysis_to_context(analysis, ctx)
        action = self.orchestrator.decide(ctx, analysis)
        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.competency, "debugging")

    # ── TEST 9: Alex -> Jordan Context Preservation ─────────────────────────
    def test_09_alex_to_jordan_context_preservation(self) -> None:
        """Verify the exact same InterviewAIContext survives handoff with Alex's evidence intact."""
        ctx = self.session_store.get_or_create("sess-handoff-persist")
        ctx.current_agent_id = "alex"
        ctx.evaluated_competencies = ["system_design"]
        ctx.missing_competencies = ["product_sense"]

        # Alex turn produces deep evidence with failure recovery and trade-offs
        turn_alex = InterviewTurn(
            session_id="sess-handoff-persist",
            messages=[
                ChatMessage(
                    role="user",
                    content=(
                        "I designed a distributed payment ledger using event sourcing and CQRS. "
                        "For failure recovery and partition handling, we implemented automated quorum consensus "
                        "and reconciliation to prevent split-brain states."
                    ),
                ),
            ],
            context=ctx,
        )
        _, next_action = asyncio.run(self.adapter.process_turn_async(turn_alex))
        self.assertEqual(next_action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(next_action.target_agent_id, "jordan")

        # Verify session context updated to Jordan while preserving Alex's evidence
        saved_ctx = self.session_store.get("sess-handoff-persist")
        self.assertIsNotNone(saved_ctx)
        self.assertEqual(saved_ctx.current_agent_id, "jordan")
        self.assertTrue(len(saved_ctx.accumulated_evidence) > 0)
        self.assertEqual(saved_ctx.accumulated_evidence[0].source_agent_id, "alex")

    # ── TEST 10: Jordan Product-Domain Question ─────────────────────────────
    def test_10_jordan_product_domain_question(self) -> None:
        """Jordan's opening question references Alex's project and asks about customer problems."""
        ctx = self.session_store.get_or_create("sess-jordan-prod-1")
        ctx.current_agent_id = "jordan"
        ctx.add_evidence(
            EvidenceItem(
                id="ev-alex-1",
                competency="system_design",
                signal="Demonstrated technical reasoning: 'I designed a distributed payment ledger using CQRS.'",
                source_agent_id="alex",
                metadata={"subject": "payment ledger"},
            )
        )
        ctx.add_evaluated_competency("system_design")
        ctx.missing_competencies = ["product_sense"]

        # Candidate greets Jordan
        turn_jordan = InterviewTurn(
            session_id="sess-jordan-prod-1",
            messages=[
                ChatMessage(role="assistant", content="Handing over to Jordan to evaluate product sense."),
                ChatMessage(role="user", content="Hello Jordan, nice to meet you."),
            ],
            context=ctx,
        )
        response, _ = asyncio.run(self.adapter.process_turn_async(turn_jordan))
        self.assertIn("payment ledger", response.lower())
        self.assertIn("main user", response.lower())
        self.assertEqual(response.count("?"), 1)

    # ── TEST 11: No Technical-Only Jordan Question ──────────────────────────
    def test_11_no_technical_only_jordan_question(self) -> None:
        """Assert Jordan's question evaluates the product dimension, never pure architecture."""
        ctx = InterviewAIContext(
            interview_id="sess-jordan-no-tech",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="jordan",
            missing_competencies=["product_sense", "customer_impact", "metrics_and_roi"],
        )
        turn = InterviewTurn(
            session_id="sess-jordan-no-tech",
            messages=[
                ChatMessage(role="assistant", content="What customer problem were you solving?"),
                ChatMessage(
                    role="user",
                    content="We reduced merchant settlement churn by 15% through instant ledger payouts.",
                ),
            ],
            context=ctx,
        )
        response, next_action = asyncio.run(self.adapter.process_turn_async(turn))
        # Jordan should evaluate customer adoption, metrics, trade-offs
        self.assertTrue(
            any(kw in response.lower() for kw in ["customer", "impact", "product", "metrics", "trade-offs", "adoption"])
            or ("user" in response.lower() and "problem" in response.lower()),
            f"Expected product-domain probe, got: {response}",
        )
        self.assertEqual(next_action.target_agent_id, "jordan")
        self.assertIn(next_action.competency, ["product_sense", "customer_impact", "metrics_and_roi"])
        self.assertEqual(response.count("?"), 1)
        # Jordan should NOT ask candidate to write code or draw database schemas
        self.assertNotIn("database schema", response.lower())
        self.assertNotIn("write a function", response.lower())

    # ── TEST 12: N-Agent Routing via Registry ───────────────────────────────
    def test_12_generic_n_agent_routing(self) -> None:
        """Registry dynamically routes to Samantha when remaining competency is threat_modeling."""
        samantha = AgentProfile(
            agent_id="samantha",
            display_name="Samantha",
            role="Security Lead",
            description="Evaluates security architecture, threat modeling, and defensive system design.",
            focal_competencies=["threat_modeling", "cryptography"],
            questioning_style="security auditor",
            instructions="Evaluate security vulnerabilities.",
        )
        self.registry.register(samantha)

        ctx = InterviewAIContext(
            interview_id="sess-n-agent-1",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="alex",
            evaluated_competencies=["system_design"],
            missing_competencies=["threat_modeling"],
        )
        analysis = AnswerAnalysis(
            answer_id="ans-n-1",
            overall_performance=0.90,
            confidence=0.90,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[EvidenceItem(id="ev-1", competency="system_design", signal="Good architecture.")],
            competency_findings=[CompetencyFinding(competency_id="system_design", assessment="Complete.", confidence=0.90)],
        )
        action = self.orchestrator.decide(ctx, analysis)
        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "samantha")
        self.assertEqual(action.competency, "threat_modeling")

    # ── TEST 13: No Hardcoded Persona Transition ────────────────────────────
    def test_13_no_hardcoded_persona_transition(self) -> None:
        """Routing from Jordan to Samantha occurs based on competency ownership, not hardcoded chains."""
        samantha = AgentProfile(
            agent_id="samantha",
            display_name="Samantha",
            role="Security Lead",
            description="Evaluates security architecture, threat modeling, and defensive system design.",
            focal_competencies=["threat_modeling"],
            questioning_style="security auditor",
            instructions="Evaluate security.",
        )
        self.registry.register(samantha)

        ctx = InterviewAIContext(
            interview_id="sess-jordan-to-sam",
            candidate_id="cand-1",
            current_round_id="round-1",
            current_agent_id="jordan",
            evaluated_competencies=["product_sense"],
            missing_competencies=["threat_modeling"],
        )
        analysis = AnswerAnalysis(
            answer_id="ans-jordan-complete",
            overall_performance=0.90,
            confidence=0.90,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[EvidenceItem(id="ev-1", competency="product_sense", signal="Strong product metrics.")],
            competency_findings=[CompetencyFinding(competency_id="product_sense", assessment="Complete.", confidence=0.90)],
        )
        action = self.orchestrator.decide(ctx, analysis)
        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "samantha")

    # ── TEST 14: Context Isolation ──────────────────────────────────────────
    def test_14_context_isolation_between_interviews(self) -> None:
        """Sessions remain completely isolated with no cross-candidate evidence leakage."""
        ctx_a = self.session_store.get_or_create("candidate-alpha")
        ctx_b = self.session_store.get_or_create("candidate-beta")

        ctx_a.add_evidence(EvidenceItem(id="ev-a", competency="system_design", signal="Alpha system."))
        self.session_store.set("candidate-alpha", ctx_a)

        retrieved_b = self.session_store.get("candidate-beta")
        self.assertEqual(len(retrieved_b.accumulated_evidence), 0)

    # ── TEST 15: Multiple-Turn State Persistence ────────────────────────────
    def test_15_multiple_turn_state_persistence(self) -> None:
        """Session store accurately persists accumulated evidence across multiple consecutive turns."""
        session_id = "sess-multiturn-persist"

        # Turn 1: Opening
        turn_1 = InterviewTurn(
            session_id=session_id,
            messages=[ChatMessage(role="user", content="Hi Alex, ready.")],
        )
        _, _ = asyncio.run(self.adapter.process_turn_async(turn_1))

        # Turn 2: Technical Answer
        turn_2 = InterviewTurn(
            session_id=session_id,
            messages=[
                ChatMessage(role="assistant", content="Describe a backend system you built."),
                ChatMessage(
                    role="user",
                    content="I designed a distributed payment ledger using event sourcing and CQRS.",
                ),
            ],
        )
        _, _ = asyncio.run(self.adapter.process_turn_async(turn_2))

        ctx = self.session_store.get(session_id)
        self.assertIsNotNone(ctx)
        self.assertEqual(len(ctx.accumulated_evidence), 1)
        self.assertIn("system_design", ctx.evaluated_competencies)

    # ── TEST 16: SSE Compatibility ──────────────────────────────────────────
    def test_16_sse_streaming_format_compatibility(self) -> None:
        """SSE stream yields valid OpenAI-compatible chunks and concludes with [DONE]."""
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello Alex, ready.")],
            model="gpt-4.1-mini",
            stream=True,
            user="sess-sse-test",
        )
        turn = self.adapter.parse_turn(req)
        chunks: list[str] = []

        async def collect():
            async for chunk in self.adapter.generate_stream(turn):
                chunks.append(chunk)

        asyncio.run(collect())
        self.assertTrue(len(chunks) > 1)
        self.assertEqual(chunks[-1], "data: [DONE]\n\n")
        first_payload = json.loads(chunks[0].replace("data: ", "").strip())
        self.assertEqual(first_payload["object"], "chat.completion.chunk")
        self.assertEqual(first_payload["choices"][0]["delta"]["role"], "assistant")

    # ── TEST 17: Provider Failure Resilience ────────────────────────────────
    def test_17_provider_failure_graceful_fallback(self) -> None:
        """When M1 fails, disclose a pause instead of implying a weak answer."""
        failing_m1 = M1InterviewAnalyzer()
        failing_m1.analyze_async = AsyncMock(side_effect=RuntimeError("M1 network timeout"))  # type: ignore[method-assign]
        adapter = CustomLLMAdapter(
            session_store=self.session_store,
            registry=self.registry,
            m1_analyzer=failing_m1,
            orchestrator=self.orchestrator,
        )
        turn = InterviewTurn(
            session_id="sess-fail-1",
            messages=[
                ChatMessage(role="assistant", content="Explain your architecture."),
                ChatMessage(role="user", content="We used microservices with Kafka messaging."),
            ],
        )
        response, next_action = asyncio.run(adapter.process_turn_async(turn))
        self.assertIsNone(next_action)
        self.assertIn("service is temporarily unavailable", response.lower())
        self.assertNotIn("?", response)

    # ── TEST 18: Orchestrator Failure Resilience ────────────────────
    def test_18_orchestrator_failure_graceful_fallback(self) -> None:
        """When routing fails, pause explicitly without fabricating a new probe."""
        failing_orch = MetaOrchestrator(registry=self.registry)
        failing_orch.decide_async = AsyncMock(side_effect=RuntimeError("LangGraph recursion error"))  # type: ignore[method-assign]
        adapter = CustomLLMAdapter(
            session_store=self.session_store,
            registry=self.registry,
            m1_analyzer=self.m1_analyzer,
            orchestrator=failing_orch,
        )
        turn = InterviewTurn(
            session_id="sess-orch-fail-1",
            messages=[
                ChatMessage(role="assistant", content="Explain your architecture."),
                ChatMessage(role="user", content="We used microservices with Kafka messaging."),
            ],
        )
        response, next_action = asyncio.run(adapter.process_turn_async(turn))
        self.assertIsNone(next_action)
        self.assertIn("service is temporarily unavailable", response.lower())
        self.assertNotIn("?", response)

    # ── TEST 19: Empty Answer Handling ──────────────────────────────────────
    def test_19_empty_candidate_answer_handling(self) -> None:
        """An ongoing empty ASR turn is silent and cannot advance or persist evaluation."""
        turn = InterviewTurn(
            session_id="sess-empty-1",
            messages=[
                ChatMessage(role="assistant", content="Could you describe your system?"),
                ChatMessage(role="user", content="   "),
            ],
            context=InterviewAIContext(
                interview_id="sess-empty-1",
                candidate_id="cand-1",
                current_round_id="round-1",
                current_agent_id="alex",
                accumulated_evidence=[EvidenceItem(id="ev-1", competency="system_design", signal="Initial.")],
            ),
        )
        before = turn.context.to_dict()
        with patch.object(self.m1_analyzer, "analyze_async", new_callable=AsyncMock) as m1, patch.object(self.orchestrator, "decide_async", new_callable=AsyncMock) as orchestrator, patch.object(self.adapter, "_persist_to_knowledge_graph_safe", new_callable=AsyncMock) as persist:
            response, next_action = asyncio.run(self.adapter.process_turn_async(turn))
        m1.assert_not_awaited()
        orchestrator.assert_not_awaited()
        persist.assert_not_awaited()
        self.assertIsNone(next_action)
        self.assertEqual(response, "")
        self.assertEqual(turn.context.to_dict(), before)

    # ── TEST 20: Agora Connectivity & Boundary Verification ─────────────────
    def test_20_agora_connectivity_boundary(self) -> None:
        """Verifies that the Custom LLM Adapter strictly satisfies the Agora Agent Studio interface contract."""
        # 1. Custom LLM Adapter parses Agora-specific session and channel headers
        headers = {
            "x-agora-session-id": "agora-session-999",
            "x-agora-channel-name": "channel-voice-primary",
            "x-agent-id": "alex",
        }
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Hello Alex, ready.")],
            model="gpt-4.1-mini",
        )
        turn = self.adapter.parse_turn(req, headers)
        self.assertEqual(turn.session_id, "agora-session-999")
        self.assertEqual(turn.channel_name, "channel-voice-primary")

        # 2. Registered Agora mapping provides valid project and pipeline configurations
        alex_mapping = self.registry.get_agora_mapping("alex")
        self.assertIsNotNone(alex_mapping)
        self.assertEqual(alex_mapping.tts_voice, "echo")
        self.assertEqual(alex_mapping.asr_model, "nova-3")
        self.assertEqual(alex_mapping.project_id, settings.AGORA_ALEX_PROJECT_ID)


if __name__ == "__main__":
    unittest.main()
