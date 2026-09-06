"""Integration and unit tests for Intra AI Custom LLM Adapter connected to M1 and Meta-Orchestrator."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings

from app.agents import (
    ALEX_PROFILE,
    JORDAN_PROFILE,
    ActionType,
    AgentProfile,
    AgentRegistry,
    agent_registry,
)
from app.custom_llm import (
    ChatCompletionRequest,
    ChatMessage,
    CustomLLMAdapter,
    InterviewTurn,
    custom_llm_adapter,
)
from app.interview_context import (
    EvidenceItem,
    InterviewAIContext,
    InterviewSessionStore,
    interview_session_store,
)
from app.interview_intelligence import (
    AnswerAnalysis,
    CompetencyFinding,
    InterviewAnswerInput,
    M1InterviewAnalyzer,
    m1_analyzer,
)
from app.main import app
from app.models.enums import DifficultyLevel
from app.orchestrator import MetaOrchestrator, meta_orchestrator


class TestCustomLLMAdapterIntegration(unittest.TestCase):
    """Test suite verifying Custom LLM Adapter integration with M1, Meta-Orchestrator, and Agora protocol."""

    @classmethod
    def setUpClass(cls) -> None:
        from app.custom_llm.adapter import custom_llm_adapter
        from app.interview_intelligence.provider import DeterministicMockM1Provider
        cls._m1_env_patch = patch.object(settings, "M1_PROVIDER", "mock")
        cls._m1_env_patch.start()
        cls._orig_m1_provider = custom_llm_adapter.m1_analyzer.provider
        custom_llm_adapter.m1_analyzer.provider = DeterministicMockM1Provider()
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        from app.custom_llm.adapter import custom_llm_adapter
        custom_llm_adapter.m1_analyzer.provider = cls._orig_m1_provider
        cls._m1_env_patch.stop()

    def setUp(self) -> None:
        interview_session_store.clear()
        agent_registry.reset()

    def _create_mock_analysis(
        self,
        overall_performance: float = 0.85,
        confidence: float = 0.90,
        vague: bool = False,
        vague_reason: str | None = None,
        contradiction_detected: bool = False,
        contradiction_details: str | None = None,
        missing_information: list[str] | None = None,
        competency_id: str = "scalability",
        recommended_follow_up: str | None = None,
        evidence: list[EvidenceItem] | None = None,
    ) -> AnswerAnalysis:
        ev_list = evidence if evidence is not None else [EvidenceItem(id="ev-mock", competency=competency_id, signal="Mock signal")]
        return AnswerAnalysis(
            answer_id=f"ans-mock-{id(self)}",
            overall_performance=overall_performance,
            confidence=confidence,
            vague=vague,
            vague_reason=vague_reason,
            contradiction_detected=contradiction_detected,
            contradiction_details=contradiction_details,
            missing_information=missing_information if missing_information is not None else [],
            evidence=ev_list,
            competency_findings=[
                CompetencyFinding(
                    competency_id=competency_id,
                    assessment="Evaluated competency",
                    confidence=confidence,
                    evidence_ids=[ev.id for ev in ev_list],
                )
            ],
            recommended_follow_up=recommended_follow_up,
        )

    # ── TEST 1 — First-turn Opening Question ───────────────────────────────
    def test_01_first_turn_opening_question(self) -> None:
        """First candidate interaction without prior context returns an opening question."""
        payload = {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "Hello, I am ready to begin the interview."}],
            "stream": False,
        }
        headers = {"x-interview-id": "int-first-turn-1", "x-agent-id": "alex"}

        response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)

        content = response.json()["choices"][0]["message"]["content"]
        self.assertIn("Alex", content)
        self.assertIn("personally build", content.lower())
        self.assertEqual(content.count("?"), 1)

    # ── TEST 2 — Full Chain: Answer -> M1 -> Analysis -> Orchestrator -> ASK_QUESTION ─
    def test_02_full_chain_technical_answer_to_next_action(self) -> None:
        """Candidate technical answer traverses M1, Meta-Orchestrator, and yields an adaptive question."""
        session_id = "int-fullchain-2"
        # Seed session with an active technical context
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )

        payload = {
            "model": "gpt-4.1-mini",
            "messages": [
                {"role": "assistant", "content": "How did you scale your caching layer?"},
                {"role": "user", "content": "We partitioned Redis into 16 shards with consistent hashing and write-through caching."},
            ],
            "stream": False,
        }
        headers = {"x-interview-id": session_id}

        response = self.client.post("/v1/chat/completions", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)

        content = response.json()["choices"][0]["message"]["content"]
        self.assertTrue(len(content.strip()) > 15)

        # Verify context was mutated with M1 evidence
        updated_ctx = interview_session_store.get(session_id)
        self.assertIsNotNone(updated_ctx)
        self.assertGreater(len(updated_ctx.accumulated_evidence), 0)

    # ── TEST 3 — Strong-but-Shallow Answer -> Depth Follow-up ──────────────
    def test_03_strong_but_shallow_depth_followup(self) -> None:
        """Strong score lacking architectural trade-offs probes deeper at the same difficulty."""
        session_id = "int-shallow-3"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["scalability", "debugging"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.85,
            confidence=0.85,
            vague=False,
            missing_information=["Cache invalidation failure handling under network partitions"],
            competency_id="scalability",
            evidence=[EvidenceItem(id="ev-1", competency="scalability", signal="Redis caching mentioned")],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [
                    {"role": "assistant", "content": "How did you scale your database?"},
                    {"role": "user", "content": "I added Redis caching in front of PostgreSQL."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)

            self.assertEqual(response.status_code, 200)
            content = response.json()["choices"][0]["message"]["content"]
            # Must ask about the missing depth
            self.assertIn("invalidation", content.lower())

            # Difficulty must NOT advance to HARD on shallow evidence
            self.assertEqual(ctx.difficulty, DifficultyLevel.MEDIUM)

    # ── TEST 4 — Weak Answer -> Fundamental Question ───────────────────────
    def test_04_weak_answer_probes_fundamentals(self) -> None:
        """Weak answer reduces difficulty from HARD to MEDIUM to test fundamentals."""
        session_id = "int-weak-4"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            difficulty=DifficultyLevel.HARD,
            missing_competencies=["system_design", "scalability"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.25,
            confidence=0.90,
            vague=False,
            missing_information=["Basic transactional guarantees"],
            competency_id="system_design",
            evidence=[EvidenceItem(id="ev-weak", competency="system_design", signal="Confused ACIDs")],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [
                    {"role": "assistant", "content": "How do you achieve ACID compliance?"},
                    {"role": "user", "content": "ACID means we just save data to MongoDB without transactions."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)

            self.assertEqual(response.status_code, 200)
            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("login request", content.lower())
            self.assertIn("database", content.lower())
            self.assertEqual(content.count("?"), 1)
            self.assertEqual(ctx.question_history[-1].competency, "system_design")

            # Difficulty should be reduced
            self.assertEqual(ctx.difficulty, DifficultyLevel.MEDIUM)

    # ── TEST 5 — Vague Answer -> Clarification ─────────────────────────────
    def test_05_vague_answer_demands_clarification(self) -> None:
        """A vague answer gets one simple capacity scenario, not a compound checklist."""
        session_id = "int-vague-5"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["software_architecture"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.35,
            confidence=0.80,
            vague=True,
            vague_reason="Lacked architectural components and throughput numbers.",
            recommended_follow_up="Could you provide specific architecture diagrams and throughput numbers?",
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [
                    {"role": "assistant", "content": "Tell me about your architecture."},
                    {"role": "user", "content": "We had some servers and databases and things worked fine."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)

            self.assertEqual(response.status_code, 200)
            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("web app", content.lower())
            self.assertIn("users", content.lower())
            self.assertIn("check first", content.lower())
            self.assertEqual(content.count("?"), 1)
            self.assertLessEqual(len(content.split()), 32)
            self.assertNotIn("architecture diagrams and throughput numbers", content.lower())
            updated = interview_session_store.get(session_id)
            self.assertEqual(updated.difficulty, DifficultyLevel.EASY)
            self.assertEqual(updated.question_history[-1].competency, "scalability")

    # ── TEST 6 — Contradiction -> Clarification ────────────────────────────
    def test_06_contradiction_probes_discrepancy(self) -> None:
        """Contradiction takes top priority to demand candidate resolution."""
        session_id = "int-contra-6"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["databases"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.40,
            confidence=0.85,
            contradiction_detected=True,
            contradiction_details="Previously claimed 8 years Postgres DBA, now claims no relational DB experience.",
            recommended_follow_up="Can you clarify your experience with PostgreSQL?",
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [
                    {"role": "assistant", "content": "What DB do you use?"},
                    {"role": "user", "content": "I've never touched relational databases like Postgres."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)

            self.assertEqual(response.status_code, 200)
            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("postgresql", content.lower())

    # ── TEST 7 — Sufficient Competency -> Next Competency ──────────────────
    def test_07_sufficient_competency_advances_topic(self) -> None:
        """When candidate demonstrates strong depth on current competency, advances to next topic."""
        session_id = "int-advance-7"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "debugging"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.92,
            confidence=0.95,
            missing_information=[],  # Full depth achieved
            competency_id="system_design",
            evidence=[EvidenceItem(id="ev-sd", competency="system_design", signal="Flawless distributed design")],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [
                    {"role": "assistant", "content": "Describe your system design."},
                    {"role": "user", "content": "Here is the exact sharding and replication design with consensus."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)

            self.assertEqual(response.status_code, 200)
            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("debugging", content.lower())
            self.assertEqual(ctx.difficulty, DifficultyLevel.HARD)

    # ── TEST 8 — Current Agent Exhausted -> SWITCH_AGENT ───────────────────
    def test_08_current_agent_exhausted_triggers_switch(self) -> None:
        """When Alex exhausts focal competencies, hands off to Jordan for product sense."""
        agent_registry.register(JORDAN_PROFILE)

        session_id = "int-switch-8"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["product_sense"],  # Jordan's domain
        )
        ctx.evaluated_competencies = list(ALEX_PROFILE.focal_competencies)

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.88,
            confidence=0.92,
            missing_information=[],
            competency_id="technical_depth",
            evidence=[EvidenceItem(id="ev-alex", competency="technical_depth", signal="Deep technical understanding")],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [
                    {"role": "assistant", "content": "Any technical final remarks?"},
                    {"role": "user", "content": "I thoroughly covered our architecture."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)

            self.assertEqual(response.status_code, 200)
            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("Jordan", content)

    # ── TEST 9 — SWITCH_AGENT Preserves Candidate Context ──────────────────
    def test_09_switch_agent_preserves_candidate_context(self) -> None:
        """Context, evidence, and session ID survive the agent handoff intact."""
        agent_registry.register(JORDAN_PROFILE)

        session_id = "int-persist-9"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["product_sense"],
        )
        ctx.add_evidence(EvidenceItem(id="ev-pres-1", competency="system_design", signal="Initial tech"))
        ctx.add_evaluated_competency("system_design")

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.90,
            confidence=0.90,
            missing_information=[],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [{"role": "user", "content": "Completed technical round."}],
                "stream": False,
            }
            self.client.post("/v1/chat/completions", json=payload, headers={"x-interview-id": session_id})

            # Check context updated to Jordan, while preserving past evaluations
            updated_ctx = interview_session_store.get(session_id)
            self.assertEqual(updated_ctx.current_agent_id, "jordan")
            self.assertIn("system_design", updated_ctx.evaluated_competencies)
            self.assertGreaterEqual(len(updated_ctx.accumulated_evidence), 1)

    # ── TEST 10 — N-Agent Switching is Registry-Driven ─────────────────────
    def test_10_registry_driven_n_agent_switching(self) -> None:
        """Registers a 3rd agent (Samantha - Security) and verifies dynamic handoff without hardcoding."""
        samantha = AgentProfile(
            agent_id="samantha",
            display_name="Samantha",
            role="Security Lead",
            description="Evaluates cryptography and threat modeling.",
            focal_competencies=["threat_modeling", "cryptography"],
            questioning_style="security auditor",
            instructions="You are Samantha...",
        )
        agent_registry.register(samantha)

        session_id = "int-samantha-10"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["threat_modeling"],
        )
        ctx.evaluated_competencies = list(ALEX_PROFILE.focal_competencies)

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.88,
            confidence=0.90,
            missing_information=[],
            competency_id="technical_depth",
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [{"role": "user", "content": "I have extensive experience in OAuth2 and threat modeling with STRIDE."}],
                "stream": False,
            }
            response = self.client.post("/v1/chat/completions", json=payload, headers={"x-interview-id": session_id})
            self.assertEqual(response.status_code, 200)
            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("Samantha", content)

    # ── TEST 11 — COMPLETE Only After Valid Completion Conditions ───────────
    def test_11_valid_completion_lifecycle(self) -> None:
        """Interview finishes with natural concluding message when all targets are satisfied."""
        session_id = "int-complete-11"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=[],
        )
        ctx.evaluated_competencies = ["system_design", "scalability"]
        ctx.add_evidence(EvidenceItem(id="ev-c1", competency="system_design", signal="Complete"))

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.95,
            confidence=0.95,
            missing_information=[],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload = {
                "messages": [{"role": "user", "content": "That covers all my experience."}],
                "stream": False,
            }
            response = self.client.post("/v1/chat/completions", json=payload, headers={"x-interview-id": session_id})
            self.assertEqual(response.status_code, 200)
            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("concludes our interview", content.lower())

    # ── TEST 12 — No Hiring Decision Generated ─────────────────────────────
    def test_12_no_hiring_decision_produced(self) -> None:
        """Response must never emit hire/reject/pass/fail recommendations."""
        session_id = "int-nohire-12"
        interview_session_store.get_or_create(session_id)

        payload = {
            "messages": [{"role": "user", "content": "Did I pass or get hired?"}],
            "stream": False,
        }
        response = self.client.post("/api/v1/chat/completions", json=payload, headers={"x-interview-id": session_id})
        self.assertEqual(response.status_code, 200)

        content = response.json()["choices"][0]["message"]["content"].lower()
        self.assertNotIn("hired", content)
        self.assertNotIn("rejected", content)
        self.assertNotIn("you passed", content)
        self.assertNotIn("you failed", content)

    # ── TEST 13 — No Context Leakage Between Sessions ──────────────────────
    def test_13_no_context_leakage_between_interview_ids(self) -> None:
        """Context for candidate A is strictly isolated from candidate B."""
        session_a = "int-sess-alpha"
        session_b = "int-sess-beta"

        ctx_a = interview_session_store.get_or_create(session_a, candidate_id="cand-alpha")
        ctx_b = interview_session_store.get_or_create(session_b, candidate_id="cand-beta")

        ctx_a.add_evidence(EvidenceItem(id="ev-alpha", competency="caching", signal="Alpha Secret"))

        self.assertNotIn("caching", [e.competency for e in ctx_b.accumulated_evidence])
        self.assertEqual(len(ctx_b.accumulated_evidence), 0)

    # ── TEST 14 — Multiple Turns Preserve Context ──────────────────────────
    def test_14_multiple_turns_preserve_accumulated_context(self) -> None:
        """Three consecutive candidate turns accumulate evidence into the same session context."""
        session_id = "int-multiturn-14"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design", "scalability"],
        )

        for turn_idx, answer in enumerate([
            "We used Kafka for queue buffering.",
            "For storage, we chose Cassandra with quorum consistency.",
        ]):
            payload = {
                "messages": [
                    {"role": "assistant", "content": f"Question {turn_idx}?"},
                    {"role": "user", "content": answer},
                ],
                "stream": False,
            }
            resp = self.client.post("/api/v1/chat/completions", json=payload, headers={"x-interview-id": session_id})
            self.assertEqual(resp.status_code, 200)

        updated_ctx = interview_session_store.get(session_id)
        self.assertGreaterEqual(len(updated_ctx.accumulated_evidence), 2)

    # ── TEST 15 — Async Execution ──────────────────────────────────────────
    def test_15_async_turn_processing(self) -> None:
        """CustomLLMAdapter.process_turn_async executes natively without blocking."""
        adapter = CustomLLMAdapter()
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="Async turn verification")],
            stream=False,
            user="async-user-1",
        )
        turn = adapter.parse_turn(req)

        response_text, action = asyncio.run(adapter.process_turn_async(turn))
        self.assertTrue(len(response_text) > 0)

    # ── TEST 16 — Agora SSE Protocol Compatibility ─────────────────────────
    def test_16_agora_sse_streaming_protocol(self) -> None:
        """Verify stream=true conforms to Agora's SSE expectations (role chunk, deltas, stop, [DONE])."""
        payload = {
            "model": "gpt-4.1-mini",
            "messages": [{"role": "user", "content": "How do you manage database connections?"}],
            "stream": True,
        }
        response = self.client.post("/v1/chat/completions", json=payload, headers={"x-interview-id": "int-sse-16"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])

        lines = [line.strip() for line in response.text.split("\n") if line.strip()]
        self.assertEqual(lines[-1], "data: [DONE]")

        chunks = [json.loads(line[6:]) for line in lines if line.startswith("data: ") and line != "data: [DONE]"]
        self.assertEqual(chunks[0]["choices"][0]["delta"]["role"], "assistant")
        self.assertEqual(chunks[-1]["choices"][0]["finish_reason"], "stop")

    # ── TEST 17 — Malformed Request Handling ───────────────────────────────
    def test_17_malformed_request_handling(self) -> None:
        """Invalid requests return 422 with clean validation failure, no stack trace."""
        # Empty messages list
        resp = self.client.post("/v1/chat/completions", json={"messages": []})
        self.assertEqual(resp.status_code, 422)

        # Invalid message role
        resp2 = self.client.post("/v1/chat/completions", json={"messages": [{"role": "invalid_role", "content": "hello"}]})
        self.assertEqual(resp2.status_code, 422)

    # ── TEST 18 — M1 Failure Fallback ──────────────────────────────────────
    def test_18_m1_failure_fallback_preserves_session(self) -> None:
        """M1 errors pause explicitly instead of inventing an assessment question."""
        session_id = "int-m1fail-18"
        interview_session_store.get_or_create(session_id)

        with patch.object(m1_analyzer, "analyze_async", side_effect=RuntimeError("M1 Timeout")):
            payload = {
                "messages": [{"role": "user", "content": "I built a cache system."}],
                "stream": False,
            }
            response = self.client.post("/api/v1/chat/completions", json=payload, headers={"x-interview-id": session_id})
            self.assertEqual(response.status_code, 200)

            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("service is temporarily unavailable", content.lower())
            self.assertNotIn("?", content)
            self.assertTrue(interview_session_store.get(session_id).metadata["service_pause"])

    # ── TEST 19 — Orchestrator Failure Fallback ────────────────────────────
    def test_19_orchestrator_failure_fallback_preserves_session(self) -> None:
        """Routing errors pause explicitly and retain the unscored answer."""
        session_id = "int-orchfail-19"
        interview_session_store.get_or_create(session_id)

        with patch.object(meta_orchestrator, "decide_async", side_effect=RuntimeError("Graph compilation error")):
            payload = {
                "messages": [{"role": "user", "content": "I built a cache system."}],
                "stream": False,
            }
            response = self.client.post("/api/v1/chat/completions", json=payload, headers={"x-interview-id": session_id})
            self.assertEqual(response.status_code, 200)

            content = response.json()["choices"][0]["message"]["content"]
            self.assertIn("service is temporarily unavailable", content.lower())
            self.assertNotIn("?", content)
            self.assertTrue(interview_session_store.get(session_id).metadata["service_pause"])

    # ── TEST 20 — No Credentials or Secrets Exposed ────────────────────────
    def test_20_no_secrets_exposed(self) -> None:
        """Readiness and completion endpoints never leak tokens, certificates, or keys."""
        resp = self.client.get("/v1/custom-llm/readiness")
        self.assertEqual(resp.status_code, 200)

        raw_str = resp.text.lower()
        for forbidden in ["bearer", "agora_app_id", "certificate", "sk-", "secret_key"]:
            self.assertNotIn(forbidden, raw_str)

    # ── TEST 21 — Agora Handshake Empty User Message Accepted (Regression) ─
    def test_21_agora_handshake_empty_user_message_accepted(self) -> None:
        """System + Assistant + empty User message (Agora initial handshake turn) returns 200 OK."""
        session_id = "int-agora-handshake-21"
        payload = {
            "model": "intra-ai",
            "messages": [
                {"role": "system", "content": "You are Alex, Technical Interviewer at Intra AI."},
                {"role": "assistant", "content": "Hello! I am Alex, Technical Manager at Intra AI. I'm ready for our interview."},
                {"role": "user", "content": ""},
            ],
            "stream": False,
        }
        headers = {"x-interview-id": session_id, "x-agent-id": "alex"}
        response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)

        content = response.json()["choices"][0]["message"]["content"]
        self.assertIn("Alex", content)
        self.assertTrue(len(content.strip()) > 10)

    # ── TEST 22 — Empty User Message Skips M1 Analysis ─────────────────────
    def test_22_empty_user_message_skips_m1_analysis(self) -> None:
        """An empty user message does not invoke M1 analysis on empty candidate text."""
        session_id = "int-nom1-22"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock()) as mock_m1:
            payload = {
                "model": "intra-ai",
                "messages": [
                    {"role": "system", "content": "You are Alex..."},
                    {"role": "assistant", "content": "Hello!"},
                    {"role": "user", "content": ""},
                ],
                "stream": False,
            }
            response = self.client.post("/api/v1/chat/completions", json=payload, headers={"x-interview-id": session_id})
            self.assertEqual(response.status_code, 200)
            mock_m1.assert_not_called()

    # ── TEST 24 — Long-Run 15 Turns with History Truncation ─────────────────
    def test_24_long_run_15_turns_with_history_truncation(self) -> None:
        """Simulate 15 consecutive turns with history truncation; context must accumulate and never reset."""
        session_id = "int-longrun-15turns"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design", "scalability", "databases", "caching", "debugging"],
        )
        interview_session_store.register_alias("agora-call-longrun-101", session_id)

        all_messages: list[dict[str, str]] = [
            {"role": "assistant", "content": "Hello! Could you describe your backend experience?"}
        ]

        # Simulate 15 turns
        for turn_num in range(1, 16):
            candidate_text = f"Turn {turn_num}: I worked on distributed PostgreSQL database sharding and Kafka queues for payment processing."
            all_messages.append({"role": "user", "content": candidate_text})

            # Truncate history to last 4 messages (simulating Agora message sliding window)
            truncated_messages = all_messages[-4:]

            payload = {
                "model": "intra-ai",
                "call_id": "agora-call-longrun-101",
                "messages": truncated_messages,
                "stream": False,
            }
            # Note: No x-interview-id header! Relies on call_id / store resolution
            response = self.client.post("/api/v1/chat/completions", json=payload)
            self.assertEqual(response.status_code, 200)

            assistant_reply = response.json()["choices"][0]["message"]["content"]
            # Assistant reply must not be the opening question
            self.assertNotIn("Let's start with system design. Could you describe a complex backend architecture or service you have recently designed in production?", assistant_reply)
            all_messages.append({"role": "assistant", "content": assistant_reply})

        # Verify context maintained full state
        updated_ctx = interview_session_store.get(session_id)
        self.assertIsNotNone(updated_ctx)
        self.assertGreaterEqual(len(updated_ctx.accumulated_evidence), 5)
        self.assertGreaterEqual(len(updated_ctx.evaluated_competencies), 1)

    # ── TEST 25 — Short Answers After Previous Turns Never Reset ────────────
    def test_25_short_answers_after_previous_turns_never_reset(self) -> None:
        """Short utterances like 'I don't know' or 'One second' after prior turns must NOT trigger opening question."""
        session_id = "int-short-answers-25"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design", "scalability"],
        )
        interview_session_store.register_alias("agora-call-short-25", session_id)

        short_utterances = [
            "I don't know.",
            "One second.",
            "I'm not sure.",
            "No.",
            "I haven't worked with that.",
            "So wait one second.",
        ]

        history: list[dict[str, str]] = [
            {"role": "assistant", "content": "How do you scale database connections?"},
            {"role": "user", "content": "We use PgBouncer for connection pooling."},
            {"role": "assistant", "content": "What pool mode did you configure in PgBouncer?"},
        ]

        for utterance in short_utterances:
            current_msgs = list(history) + [{"role": "user", "content": utterance}]
            payload = {
                "model": "intra-ai",
                "call_id": "agora-call-short-25",
                "messages": current_msgs,
                "stream": False,
            }
            response = self.client.post("/api/v1/chat/completions", json=payload)
            self.assertEqual(response.status_code, 200)

            assistant_reply = response.json()["choices"][0]["message"]["content"]
            # Must NOT be the opening question
            self.assertNotIn("Let's start with system design. Could you describe a complex backend architecture or service you have recently designed in production?", assistant_reply)

    # ── TEST 26 — Agora Call ID / Agent UUID Session Resolution ─────────────
    def test_26_agora_call_id_and_agent_uuid_session_resolution(self) -> None:
        """Requests with call_id or agent_uuid resolve to the same canonical session."""
        session_id = "int-agora-alias-26"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )
        interview_session_store.register_alias("agora-call-uuid-999", session_id)

        payload1 = {
            "model": "intra-ai",
            "call_id": "agora-call-uuid-999",
            "messages": [
                {"role": "assistant", "content": "Question 1?"},
                {"role": "user", "content": "Answer 1 about Kafka message broker."},
            ],
            "stream": False,
        }
        res1 = self.client.post("/api/v1/chat/completions", json=payload1)
        self.assertEqual(res1.status_code, 200)

        # Second request using same call_id
        payload2 = {
            "model": "intra-ai",
            "call_id": "agora-call-uuid-999",
            "messages": [
                {"role": "assistant", "content": "Question 2?"},
                {"role": "user", "content": "Answer 2 about Redis cache cluster."},
            ],
            "stream": False,
        }
        res2 = self.client.post("/api/v1/chat/completions", json=payload2)
        self.assertEqual(res2.status_code, 200)

        ctx = interview_session_store.get(session_id)
        self.assertIsNotNone(ctx)
        self.assertGreaterEqual(len(ctx.accumulated_evidence), 2)

    # ── TEST 27 — AUDIO_CHECK Fast-Path Bypasses M1 & Orchestrator ─────────
    def test_27_audio_check_bypasses_m1_and_orchestrator(self) -> None:
        """AUDIO_CHECK utterance ('Am I audible?') returns immediate response and bypasses M1/Orchestrator."""
        session_id = "int-fastpath-audio-27"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )
        initial_evidence_count = len(ctx.accumulated_evidence)
        initial_competencies = list(ctx.evaluated_competencies)

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock()) as mock_m1, \
             patch.object(meta_orchestrator, "decide_async", new=AsyncMock()) as mock_orch:

            payload = {
                "model": "intra-ai",
                "messages": [{"role": "user", "content": "Am I audible?"}],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)

            reply = response.json()["choices"][0]["message"]["content"]
            self.assertIn("hear you", reply.lower())

            # Assert M1 and Meta-Orchestrator were NOT called
            mock_m1.assert_not_called()
            mock_orch.assert_not_called()

            # Assert zero context mutation
            updated_ctx = interview_session_store.get(session_id)
            self.assertEqual(len(updated_ctx.accumulated_evidence), initial_evidence_count)
            self.assertEqual(updated_ctx.evaluated_competencies, initial_competencies)

    # ── TEST 28 — TIME_PAUSE Fast-Path Bypasses M1 & Orchestrator ──────────
    def test_28_time_pause_bypasses_m1_and_orchestrator(self) -> None:
        """TIME_PAUSE utterance ('Give me a second.') returns immediate response without calling M1/Orchestrator."""
        session_id = "int-fastpath-pause-28"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock()) as mock_m1, \
             patch.object(meta_orchestrator, "decide_async", new=AsyncMock()) as mock_orch:

            payload = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How do you scale database reads?"},
                    {"role": "user", "content": "Give me a second."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)

            reply = response.json()["choices"][0]["message"]["content"]
            self.assertIn("take your time", reply.lower())

            mock_m1.assert_not_called()
            mock_orch.assert_not_called()

    # ── TEST 29 — REPEAT_QUESTION Refers to Actual Previous Question ────────
    def test_29_repeat_question_uses_actual_previous_question(self) -> None:
        """REPEAT_QUESTION utterance quotes/refers to the actual previous assistant question."""
        session_id = "int-fastpath-repeat-29"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )

        previous_q = "What technical trade-offs did you consider when designing the messaging system?"
        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock()) as mock_m1, \
             patch.object(meta_orchestrator, "decide_async", new=AsyncMock()) as mock_orch:

            payload = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": previous_q},
                    {"role": "user", "content": "Sorry, can you repeat the question?"},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)

            reply = response.json()["choices"][0]["message"]["content"]
            # Must refer to the actual question asked
            self.assertIn("What technical trade-offs did you consider", reply)

            mock_m1.assert_not_called()
            mock_orch.assert_not_called()

    # ── TEST 30 — NORMAL ANSWER Traverses Full M1 + Orchestrator Pipeline ───
    def test_30_normal_answer_invokes_m1_and_orchestrator(self) -> None:
        """INTERVIEW_ANSWER ('We used Redis because we needed low latency caching.') invokes M1 and Orchestrator."""
        session_id = "int-normal-answer-30"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["scalability"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.88,
            confidence=0.90,
            competency_id="scalability",
            evidence=[EvidenceItem(id="ev-redis", competency="scalability", signal="Redis low latency caching")],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)) as mock_m1, \
             patch.object(meta_orchestrator, "decide_async", wraps=meta_orchestrator.decide_async) as mock_orch:

            payload = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How did you manage caching?"},
                    {"role": "user", "content": "We used Redis because we needed low latency caching."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)

            # Assert M1 was called exactly once
            mock_m1.assert_called_once()
            self.assertEqual(mock_m1.call_args[0][0].answer_text, "We used Redis because we needed low latency caching.")

            # Assert Meta-Orchestrator was called
            mock_orch.assert_called_once()

            # Assert context was updated
            updated_ctx = interview_session_store.get(session_id)
            self.assertGreater(len(updated_ctx.accumulated_evidence), 0)

    # ── TEST 31 — Ignorance Statement Routes to M1 ─────────────────────────
    def test_31_ignorance_statement_routes_to_m1(self) -> None:
        """Candidate saying 'I don't know.' is classified as INTERVIEW_ANSWER and evaluated by M1."""
        session_id = "int-ignorance-31"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.1,
            confidence=0.95,
            competency_id="system_design",
            evidence=[EvidenceItem(id="ev-idk", competency="system_design", signal="Candidate does not know")],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)) as mock_m1:
            payload = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How do distributed transactions work?"},
                    {"role": "user", "content": "I don't know."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)

            mock_m1.assert_called_once()
            self.assertEqual(mock_m1.call_args[0][0].answer_text, "I don't know.")

    # ── TEST 32 — Adversarial Technical Cases Route to M1 ───────────────────
    def test_32_adversarial_technical_cases_route_to_m1(self) -> None:
        """Technical utterances with control keywords must NOT be intercepted as control turns."""
        adversarial_cases = [
            "Can you hear me explain how we used Redis for caching?",
            "I need a second replica for PostgreSQL.",
            "Give me a second example of how you implemented caching.",
            "Did that latency number come through in the benchmark?",
            "Let me think about the database partitioning strategy.",
            "Sorry, my mic cut out, but the architecture used Redis for caching.",
            "Could you repeat the question so I can explain our Redis cluster?",
        ]

        for idx, utterance in enumerate(adversarial_cases):
            session_id = f"int-adversarial-{idx}"
            interview_session_store.get_or_create(
                interview_id=session_id,
                agent_id="alex",
                missing_competencies=["system_design"],
            )

            mock_analysis = self._create_mock_analysis(
                overall_performance=0.8,
                competency_id="system_design",
                evidence=[EvidenceItem(id=f"ev-{idx}", competency="system_design", signal=utterance)],
            )

            with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)) as mock_m1:
                payload = {
                    "model": "intra-ai",
                    "messages": [
                        {"role": "assistant", "content": "Describe your architecture."},
                        {"role": "user", "content": utterance},
                    ],
                    "stream": False,
                }
                headers = {"x-interview-id": session_id}
                response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
                self.assertEqual(response.status_code, 200)

                # M1 MUST be called for every adversarial technical case
                mock_m1.assert_called_once()
                self.assertEqual(mock_m1.call_args[0][0].answer_text, utterance)

    # ── TEST 33 — Compound Control + Answer Routes to M1 ────────────────────
    def test_33_compound_control_and_answer_routes_to_m1(self) -> None:
        """Compound utterance combining control phrase with technical content routes to M1."""
        session_id = "int-compound-33"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.85,
            competency_id="system_design",
            evidence=[EvidenceItem(id="ev-kafka", competency="system_design", signal="Kafka event processing")],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)) as mock_m1:
            payload = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How did you handle real-time events?"},
                    {"role": "user", "content": "Can you hear me? We used Kafka for event processing."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)

            mock_m1.assert_called_once()

    # ── TEST 34 — Context Isolation Across Concurrent Interviews ────────────
    def test_34_context_isolation_between_sessions(self) -> None:
        """A control turn in Session A must not mutate or affect active context in Session B."""
        session_a = "int-session-a-34"
        session_b = "int-session-b-34"

        ctx_a = interview_session_store.get_or_create(
            interview_id=session_a,
            agent_id="alex",
            missing_competencies=["system_design"],
        )
        ctx_b = interview_session_store.get_or_create(
            interview_id=session_b,
            agent_id="alex",
            missing_competencies=["scalability"],
        )
        ctx_b.accumulated_evidence.append(
            EvidenceItem(id="ev-b1", competency="scalability", signal="Pre-existing signal in B")
        )
        interview_session_store.set(session_b, ctx_b)

        # Control turn in Session A
        payload_a = {
            "model": "intra-ai",
            "messages": [{"role": "user", "content": "Can you hear me?"}],
            "stream": False,
        }
        res_a = self.client.post("/api/v1/chat/completions", json=payload_a, headers={"x-interview-id": session_a})
        self.assertEqual(res_a.status_code, 200)

        # Verify Session B is untouched
        updated_b = interview_session_store.get(session_b)
        self.assertEqual(len(updated_b.accumulated_evidence), 1)
        self.assertEqual(updated_b.accumulated_evidence[0].signal, "Pre-existing signal in B")

        # Verify Session A has 0 evidence
        updated_a = interview_session_store.get(session_a)
        self.assertEqual(len(updated_a.accumulated_evidence), 0)

    # ── TEST 35 — Multi-Turn Flow With Interleaved Control Turns ────────────
    def test_35_multi_turn_with_interleaved_control_turns(self) -> None:
        """Sequential flow with control turns interleaved between answers preserves state perfectly."""
        session_id = "int-multiturn-35"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design", "scalability"],
        )

        # Turn 1: Substantive answer
        mock_a1 = self._create_mock_analysis(
            overall_performance=0.85,
            competency_id="system_design",
            evidence=[EvidenceItem(id="ev-1", competency="system_design", signal="PostgreSQL sharding")],
        )
        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_a1)):
            p1 = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How did you design your database?"},
                    {"role": "user", "content": "We implemented PostgreSQL sharding across 4 nodes."},
                ],
                "stream": False,
            }
            r1 = self.client.post("/api/v1/chat/completions", json=p1, headers={"x-interview-id": session_id})
            self.assertEqual(r1.status_code, 200)

        ctx = interview_session_store.get(session_id)
        self.assertEqual(len(ctx.accumulated_evidence), 1)

        # Turn 2: Audio check (Control turn)
        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock()) as mock_m1:
            p2 = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How did you handle failover?"},
                    {"role": "user", "content": "Am I audible?"},
                ],
                "stream": False,
            }
            r2 = self.client.post("/api/v1/chat/completions", json=p2, headers={"x-interview-id": session_id})
            self.assertEqual(r2.status_code, 200)
            mock_m1.assert_not_called()

        # Context evidence must still be 1 (unmutated by audio check)
        ctx = interview_session_store.get(session_id)
        self.assertEqual(len(ctx.accumulated_evidence), 1)

        # Turn 3: Time pause (Control turn)
        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock()) as mock_m1:
            p3 = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How did you handle failover?"},
                    {"role": "user", "content": "Give me a second."},
                ],
                "stream": False,
            }
            r3 = self.client.post("/api/v1/chat/completions", json=p3, headers={"x-interview-id": session_id})
            self.assertEqual(r3.status_code, 200)
            mock_m1.assert_not_called()

        ctx = interview_session_store.get(session_id)
        self.assertEqual(len(ctx.accumulated_evidence), 1)

        # Turn 4: Substantive answer to failover question
        mock_a2 = self._create_mock_analysis(
            overall_performance=0.90,
            competency_id="scalability",
            evidence=[EvidenceItem(id="ev-2", competency="scalability", signal="Patroni automated failover")],
        )
        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_a2)):
            p4 = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How did you handle failover?"},
                    {"role": "user", "content": "We used Patroni with Raft consensus for automated failover."},
                ],
                "stream": False,
            }
            r4 = self.client.post("/api/v1/chat/completions", json=p4, headers={"x-interview-id": session_id})
            self.assertEqual(r4.status_code, 200)

        # Context should now have 2 evidence items
        ctx = interview_session_store.get(session_id)
        self.assertEqual(len(ctx.accumulated_evidence), 2)

    # ── TEST 36 — First Turn Audio Check Safety ────────────────────────────
    def test_36_first_turn_audio_check_does_not_advance_interview(self) -> None:
        """First candidate turn 'Hi, am I audible?' is recognized as AUDIO_CHECK without advancing state."""
        session_id = "int-firstturn-audio-36"
        ctx = interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design", "scalability"],
        )

        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock()) as mock_m1:
            payload = {
                "model": "intra-ai",
                "messages": [{"role": "user", "content": "Hi, am I audible?"}],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)

            reply = response.json()["choices"][0]["message"]["content"]
            self.assertIn("hear you", reply.lower())
            mock_m1.assert_not_called()

        # Context should have 0 evidence and 0 evaluated competencies
        updated_ctx = interview_session_store.get(session_id)
        self.assertEqual(len(updated_ctx.accumulated_evidence), 0)
        self.assertEqual(len(updated_ctx.evaluated_competencies), 0)
        self.assertFalse(updated_ctx.metadata.get("completed", False))

    # ── TEST 37 — SSE Streaming for Both Control and Substantive Turns ──────
    def test_37_sse_streaming_protocol_compatibility(self) -> None:
        """Both control and substantive responses produce valid OpenAI-compatible SSE streams."""
        session_id = "int-sse-37"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )

        # 1. Test Control SSE (AUDIO_CHECK)
        payload_control = {
            "model": "intra-ai",
            "messages": [{"role": "user", "content": "Can you hear me clearly?"}],
            "stream": True,
        }
        res_ctrl = self.client.post("/api/v1/chat/completions", json=payload_control, headers={"x-interview-id": session_id})
        self.assertEqual(res_ctrl.status_code, 200)
        self.assertIn("text/event-stream", res_ctrl.headers["content-type"])

        ctrl_text = res_ctrl.text
        self.assertIn("data: ", ctrl_text)
        self.assertIn("data: [DONE]", ctrl_text)
        self.assertIn("role", ctrl_text)
        self.assertIn("assistant", ctrl_text)

        # Parse chunks
        lines = [line.strip() for line in ctrl_text.split("\n") if line.strip()]
        data_lines = [line[6:] for line in lines if line.startswith("data: ") and line != "data: [DONE]"]
        self.assertGreater(len(data_lines), 0)
        for dl in data_lines:
            chunk = json.loads(dl)
            self.assertEqual(chunk["object"], "chat.completion.chunk")

        # 2. Test Substantive SSE (INTERVIEW_ANSWER)
        mock_analysis = self._create_mock_analysis(
            overall_performance=0.85,
            competency_id="system_design",
            evidence=[EvidenceItem(id="ev-sse", competency="system_design", signal="Valid SSE answer")],
        )
        with patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)):
            payload_sub = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "What is your database schema?"},
                    {"role": "user", "content": "We used PostgreSQL with relational tables and foreign keys."},
                ],
                "stream": True,
            }
            res_sub = self.client.post("/api/v1/chat/completions", json=payload_sub, headers={"x-interview-id": session_id})
            self.assertEqual(res_sub.status_code, 200)
            self.assertIn("text/event-stream", res_sub.headers["content-type"])
            self.assertIn("data: [DONE]", res_sub.text)

    # ── TEST 38 — Safe Classifier Exception Fallback to Substantive Path ────
    def test_38_classifier_exception_failsafe_to_substantive_path(self) -> None:
        """If classifier encounters an unexpected exception, it safely falls back to M1 rather than crashing."""
        session_id = "int-classifier-fail-38"
        interview_session_store.get_or_create(
            interview_id=session_id,
            agent_id="alex",
            missing_competencies=["system_design"],
        )

        mock_analysis = self._create_mock_analysis(
            overall_performance=0.8,
            competency_id="system_design",
            evidence=[EvidenceItem(id="ev-fallback", competency="system_design", signal="Failsafe signal")],
        )

        with patch.object(custom_llm_adapter.classifier, "classify", side_effect=RuntimeError("Classifier boom!")), \
             patch.object(m1_analyzer, "analyze_async", new=AsyncMock(return_value=mock_analysis)) as mock_m1:

            payload = {
                "model": "intra-ai",
                "messages": [
                    {"role": "assistant", "content": "How do you handle data persistence?"},
                    {"role": "user", "content": "We write to write-ahead logs in PostgreSQL."},
                ],
                "stream": False,
            }
            headers = {"x-interview-id": session_id}
            response = self.client.post("/api/v1/chat/completions", json=payload, headers=headers)
            self.assertEqual(response.status_code, 200)

            # M1 should be safely invoked on classifier failure
            mock_m1.assert_called_once()


if __name__ == "__main__":
    unittest.main()
