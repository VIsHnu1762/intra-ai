"""Unit and integration tests for Intra AI Meta-Orchestrator LangGraph adaptive decision engine.

Orchestrator calls are mocked to remain deterministic; transport and browser
integration checks are separate from these policy tests.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents import ALEX_PROFILE, ActionType, AgentProfile, AgentRegistry
from app.core.config import settings
from app.core.exceptions import AgentNotFoundError, ValidationError
from app.interview_context import ContradictionItem, EvidenceItem, InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence import (
    AnswerAnalysis,
    CompetencyFinding,
    InterviewAnswerInput,
    M1InterviewAnalyzer,
)
from app.models.enums import DifficultyLevel
from app.orchestrator import (
    MetaOrchestrator,
    NemotronRoutingDecision,
    calculate_difficulty_adjustment,
    clamp_difficulty,
    find_best_switch_agent,
    select_next_competency,
)


# ── Nemotron Mock Helpers ───────────────────────────────────────────────────────

def _make_nemotron_ask_mock(competency: str = "scalability", agent_id: str = "alex"):
    """Return a mock NemotronRoutingDecision for ASK_QUESTION."""
    return MagicMock(
        action="ASK_QUESTION",
        target_agent_id=agent_id,
        competency=competency,
        rationale=f"Candidate should explore {competency} further.",
        cross_agent_opportunity=False,
        trigger_signals=[],
        unresolved_target_competencies=[competency],
        question_text=None,
        metadata={},
        to_action_type=lambda: ActionType.ASK_QUESTION,
    )


def _make_nemotron_switch_mock(target_agent: str, competency: str, cross_agent: bool = True, signals=None):
    """Return a mock NemotronRoutingDecision for SWITCH_AGENT."""
    return MagicMock(
        action="SWITCH_AGENT",
        target_agent_id=target_agent,
        competency=competency,
        rationale=f"Cross-agent opportunity: {signals or []} signal detected.",
        cross_agent_opportunity=cross_agent,
        trigger_signals=signals or [],
        unresolved_target_competencies=[competency],
        question_text=None,
        metadata={},
        to_action_type=lambda: ActionType.SWITCH_AGENT,
    )


class TestMetaOrchestrator(unittest.TestCase):
    """Test suite verifying adaptive LangGraph state machine, depth separation, and NextAction routing.

    All tests mock Nemotron to be deterministic. The mock is applied at the
    `call_groq` transport layer and `query_nemotron`/`validate_nemotron` nodes
    so the graph's deterministic nodes (contradiction, vagueness, probe_fundamentals)
    still run naturally.
    """

    def setUp(self) -> None:
        self.registry = AgentRegistry(register_defaults=True)  # Built-in Alex registered
        self.orchestrator = MetaOrchestrator(registry=self.registry)
        self._orig_orch_key = getattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
        settings.GROQ_ORCHESTRATOR_API_KEY = "mock-orch-key"

        # Active interview context
        self.context = InterviewAIContext(
            interview_id="int-orch-1",
            candidate_id="cand-orch-1",
            current_round_id="technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            evaluated_competencies=["system_design"],
            accumulated_evidence=[
                EvidenceItem(id="ev-init", competency="system_design", signal="Initial evidence")
            ],
            missing_competencies=["scalability", "debugging"],
        )

    def tearDown(self) -> None:
        settings.GROQ_ORCHESTRATOR_API_KEY = self._orig_orch_key

    def _create_analysis(
        self,
        overall_performance: float = 0.80,
        confidence: float = 0.90,
        vague: bool = False,
        vague_reason: str | None = None,
        contradiction_detected: bool = False,
        contradiction_details: str | None = None,
        missing_information: list[str] | None = None,
        competency_id: str = "scalability",
        recommended_follow_up: str | None = "How would you handle Redis failure?",
    ) -> AnswerAnalysis:
        ev = EvidenceItem(id="ev-orch-1", competency=competency_id, signal="Candidate statement.")
        return AnswerAnalysis(
            answer_id="ans-orch-turn",
            overall_performance=overall_performance,
            confidence=confidence,
            vague=vague,
            vague_reason=vague_reason,
            contradiction_detected=contradiction_detected,
            contradiction_details=contradiction_details,
            missing_information=missing_information if missing_information is not None else [],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(
                    competency_id=competency_id,
                    assessment="Demonstrated capability.",
                    confidence=confidence,
                    evidence_ids=["ev-orch-1"],
                )
            ],
            recommended_follow_up=recommended_follow_up,
        )

    def _decide_no_nemotron(self, context, analysis, **kwargs):
        """Call orchestrator.decide() with Nemotron mocked out (returns None = use fallback)."""
        with patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline")):
            return self.orchestrator.decide(context, analysis, **kwargs)

    # ── SCENARIO A — Strong but Shallow ─────────────────────────────────────
    def test_01_strong_but_shallow_probes_depth(self) -> None:
        """Strong score (0.85) with missing trade-off depth probes deeper at SAME difficulty."""
        analysis = self._create_analysis(
            overall_performance=0.85,
            competency_id="scalability",
            missing_information=["Architectural trade-offs between Redis and Memcached"],
        )
        action = self._decide_no_nemotron(self.context, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.competency, "scalability")
        self.assertEqual(action.difficulty, DifficultyLevel.MEDIUM)  # Does NOT bump to HARD without depth
        self.assertIn("redis failure", action.question_text.lower())
        self.assertEqual(action.question_text.count("?"), 1)
        self.assertIn("omitted critical depth", action.rationale)

    # ── SCENARIO B — Strong + Detailed (Mastered) ───────────────────────────
    def test_02_strong_and_detailed_increases_difficulty(self) -> None:
        """Strong score (0.88) with full depth and zero missing info increases difficulty to HARD."""
        analysis = self._create_analysis(
            overall_performance=0.88,
            confidence=0.95,
            competency_id="scalability",
            missing_information=[],  # Zero missing info -> Sufficient depth reached
        )
        action = self._decide_no_nemotron(self.context, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.difficulty, DifficultyLevel.HARD)
        self.assertEqual(action.competency, "debugging")  # Advances to next missing competency
        self.assertIn("strong depth", action.rationale.lower())

    # ── SCENARIO C — Weak + Concrete ────────────────────────────────────────
    def test_03_weak_performance_reduces_difficulty_to_probe_fundamentals(self) -> None:
        """Weak answer (0.30) reduces difficulty from HARD to MEDIUM to test core fundamentals."""
        self.context.set_difficulty(DifficultyLevel.HARD)
        analysis = self._create_analysis(
            overall_performance=0.30,
            competency_id="scalability",
            missing_information=["Fundamental data consistency principles"],
        )
        action = self.orchestrator.decide(self.context, analysis)  # probe_fundamentals is forced, no Nemotron

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.difficulty, DifficultyLevel.MEDIUM)  # Reduced by 1 step
        self.assertEqual(action.competency, "scalability")
        self.assertIn("fundamentals", action.rationale.lower())

    # ── SCENARIO D — Vague Answer ───────────────────────────────────────────
    def test_04_vague_answer_requests_clarification(self) -> None:
        """Vague answers lower difficulty and ask one concrete, grounded clarification."""
        analysis = self._create_analysis(
            overall_performance=0.35,
            vague=True,
            vague_reason="Lacked concrete implementation details or numbers.",
            recommended_follow_up="Could you provide specific throughput metrics and architecture components?",
        )
        action = self.orchestrator.decide(self.context, analysis)  # vagueness is forced, no Nemotron

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.difficulty, DifficultyLevel.EASY)
        self.assertEqual(action.competency, "scalability")
        self.assertIn("vague", action.rationale.lower())
        self.assertIn("web app", action.question_text)
        self.assertIn("twice as many users", action.question_text)
        self.assertNotIn("architecture components", action.question_text)
        self.assertLessEqual(len(action.question_text.split()), 32)
        self.assertEqual(action.question_text.count("?"), 1)

    # ── SCENARIO E — Contradiction ──────────────────────────────────────────
    def test_05_contradiction_probes_resolution(self) -> None:
        """Contradiction takes highest priority to resolve the discrepancy before any progression."""
        analysis = self._create_analysis(
            overall_performance=0.40,
            contradiction_detected=True,
            contradiction_details="Previously claimed distributed Postgres architect, but later claimed never used Postgres.",
            recommended_follow_up="Can you clarify your exact role with distributed PostgreSQL?",
        )
        action = self.orchestrator.decide(self.context, analysis)  # contradiction is forced, no Nemotron

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.difficulty, DifficultyLevel.MEDIUM)
        self.assertIn("contradiction", action.rationale.lower())
        self.assertEqual(action.question_text, "Can you clarify your exact role with distributed PostgreSQL?")

    # ── SCENARIO F — Missing Information ────────────────────────────────────
    def test_06_missing_information_incorporated_into_question(self) -> None:
        """Probe explicitly incorporates specific missing information identified by M1."""
        analysis = self._create_analysis(
            overall_performance=0.72,
            competency_id="debugging",
            missing_information=["Thread dump analysis methodology under high load"],
            recommended_follow_up=None,
        )
        action = self._decide_no_nemotron(self.context, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.competency, "debugging")
        self.assertIn("thread dump", action.question_text)
        self.assertIn("server stops responding", action.question_text)
        self.assertEqual(action.question_text.count("?"), 1)

    # ── SCENARIO G — Partially Evaluated Competency ─────────────────────────
    def test_07_partially_evaluated_competency_continues_probing(self) -> None:
        """A competency with partial depth continues probing with current agent rather than switching."""
        analysis = self._create_analysis(
            overall_performance=0.65,
            competency_id="scalability",
            missing_information=["Failure handling under network partitions"],
        )
        action = self._decide_no_nemotron(self.context, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.competency, "scalability")

    # ── SCENARIO H — Competency Sufficiently Covered Advances Next ──────────
    def test_08_sufficiently_covered_competency_advances_to_next(self) -> None:
        """When current competency achieves full depth, advances to next missing competency."""
        analysis = self._create_analysis(
            overall_performance=0.90,
            confidence=0.92,
            competency_id="scalability",
            missing_information=[],  # Deep!
        )
        action = self._decide_no_nemotron(self.context, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.competency, "debugging")  # Moved from scalability to debugging

    # ── SCENARIO I — Other Agent Better Suited (Handoff) ───────────────────
    def test_09_other_agent_better_suited_triggers_switch(self) -> None:
        """When current agent completes focal competencies, switches to agent covering remaining gap."""
        jordan = AgentProfile(
            agent_id="jordan",
            display_name="Jordan",
            role="Product Lead",
            description="Evaluates product sense and metrics.",
            focal_competencies=["product_sense", "customer_impact"],
            questioning_style="probing product inquiry",
            instructions="You are Jordan...",
        )
        self.registry.register(jordan)

        # Context has missing competency owned only by Jordan
        self.context.missing_competencies = ["product_sense"]
        analysis = self._create_analysis(
            overall_performance=0.88,
            competency_id="scalability",
            missing_information=[],
        )

        action = self._decide_no_nemotron(self.context, analysis)

        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "jordan")
        self.assertIn("switching", action.rationale.lower())
        self.assertIn("jordan", action.rationale.lower())

    # ── SCENARIO J — First Question / Empty Missing Safety ──────────────────
    def test_10_first_question_safety_does_not_complete_immediately(self) -> None:
        """A freshly initialized context with empty missing_competencies does NOT complete on turn 1."""
        fresh_context = InterviewAIContext(
            interview_id="int-fresh-1",
            candidate_id="cand-fresh-1",
            current_round_id="technical",
            current_agent_id="alex",
            missing_competencies=[],  # Empty upon initialization!
            evaluated_competencies=[],
            accumulated_evidence=[],
        )
        analysis = self._create_analysis(overall_performance=0.75)

        action = self._decide_no_nemotron(fresh_context, analysis)

        # Must ask a question, NOT complete!
        self.assertNotEqual(action.action, ActionType.COMPLETE)
        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")

    # ── SCENARIO K — Generic N-Agent Support (No Alex->Jordan Hardcoding) ──
    def test_11_generic_n_agent_support(self) -> None:
        """Orchestrator routes dynamically to whoever covers the missing competency."""
        samantha = AgentProfile(
            agent_id="samantha",
            display_name="Samantha",
            role="Security Lead",
            description="Evaluates cryptography and threat modeling.",
            focal_competencies=["cryptography", "threat_modeling"],
            questioning_style="security auditor",
            instructions="You are Samantha...",
        )
        self.registry.register(samantha)

        self.context.missing_competencies = ["threat_modeling"]
        analysis = self._create_analysis(overall_performance=0.88, missing_information=[])

        action = self._decide_no_nemotron(self.context, analysis)
        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "samantha")
        self.assertEqual(action.competency, "threat_modeling")

    # ── SCENARIO L — No Hiring Decision ─────────────────────────────────────
    def test_12_no_hiring_decision_produced(self) -> None:
        """Verify orchestrator output never produces hire/reject/pass/fail decisions."""
        analysis = self._create_analysis(overall_performance=0.99)
        action = self._decide_no_nemotron(self.context, analysis)

        self.assertFalse(hasattr(action, "hiring_decision"))
        self.assertFalse(hasattr(action, "recommendation"))
        self.assertNotIn("hire", action.rationale.lower())
        self.assertNotIn("reject", action.rationale.lower())

    # ── SCENARIO M — Context Immutability ────────────────────────────────────
    def test_13_context_immutability(self) -> None:
        """Verify orchestrator.decide() strictly leaves input context unchanged."""
        orig_agent = self.context.current_agent_id
        orig_diff = self.context.difficulty
        orig_missing = list(self.context.missing_competencies)
        orig_eval = list(self.context.evaluated_competencies)

        analysis = self._create_analysis(overall_performance=0.85)
        self._decide_no_nemotron(self.context, analysis)

        self.assertEqual(self.context.current_agent_id, orig_agent)
        self.assertEqual(self.context.difficulty, orig_diff)
        self.assertEqual(self.context.missing_competencies, orig_missing)
        self.assertEqual(self.context.evaluated_competencies, orig_eval)

    # ── TEST 14 — Safe Completion when All Targets Satisfied ───────────────
    def test_14_completion_when_all_targets_satisfied(self) -> None:
        """Completes cleanly when all targets evaluated and progress recorded."""
        self.context.missing_competencies = []
        self.context.evaluated_competencies = ["system_design", "scalability", "debugging"]
        analysis = self._create_analysis(overall_performance=0.85, missing_information=[])

        action = self._decide_no_nemotron(self.context, analysis)
        self.assertEqual(action.action, ActionType.COMPLETE)
        self.assertIn("all required interview competencies evaluated", action.rationale.lower())

    # ── TEST 15 — Difficulty Clamping to Agent Bounds ───────────────────────
    def test_15_difficulty_clamping_to_agent_bounds(self) -> None:
        """Difficulty respects agent profile minimum and maximum constraints."""
        capped_agent = AgentProfile(
            agent_id="junior_mentor",
            display_name="Junior Mentor",
            role="Onboarding Mentor",
            description="Mentors junior hires.",
            focal_competencies=["git_basics"],
            questioning_style="gentle",
            instructions="Mentor...",
            min_difficulty=DifficultyLevel.EASY,
            max_difficulty=DifficultyLevel.MEDIUM,  # Capped at MEDIUM
        )
        self.registry.register(capped_agent)

        self.context.current_agent_id = "junior_mentor"
        self.context.difficulty = DifficultyLevel.MEDIUM
        self.context.missing_competencies = ["git_basics"]

        analysis = self._create_analysis(
            overall_performance=0.95,
            competency_id="git_basics",
            missing_information=[],
        )
        action = self._decide_no_nemotron(self.context, analysis)

        # Bump attempted to HARD, but capped at MEDIUM
        self.assertEqual(action.difficulty, DifficultyLevel.MEDIUM)

    # ── TEST 16 — Async API decide_async() ─────────────────────────────────
    def test_16_decide_async_execution(self) -> None:
        """Verify decide_async() operates asynchronously with identical decision logic."""
        analysis = self._create_analysis(overall_performance=0.88, missing_information=[])

        async def run_test():
            with patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline")):
                return await self.orchestrator.decide_async(self.context, analysis)

        action = asyncio.run(run_test())
        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.difficulty, DifficultyLevel.HARD)

    # ── TEST 17 — Full Chain Integration: M1 -> Analysis -> Orchestrator ──
    def test_17_full_chain_m1_to_orchestrator(self) -> None:
        """Integration test tracing Candidate Answer -> M1 -> AnswerAnalysis -> MetaOrchestrator -> NextAction."""
        from app.interview_intelligence.provider import DeterministicMockM1Provider
        analyzer = M1InterviewAnalyzer(provider=DeterministicMockM1Provider())

        # Turn 1: Candidate gives a vague answer
        input_turn = InterviewAnswerInput(
            answer_id="ans-turn-1",
            question_text="How did you scale your caching layer?",
            answer_text="We basically just used some tools and things worked pretty good etc.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = analyzer.analyze(input_turn)
        self.assertTrue(analysis.vague)

        # Vagueness is a forcing condition — Nemotron is bypassed
        action = self.orchestrator.decide(self.context, analysis)

        # Latest policy lowers vague answers by one level for a simpler probe.
        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.difficulty, DifficultyLevel.EASY)
        self.assertIn("vague", action.rationale.lower())

    # ── TEST 18 — Only Canonical Actions Emitted ───────────────────────────
    def test_18_only_canonical_actions_emitted(self) -> None:
        """Verify NextAction strictly emits only canonical ActionType enum members."""
        analysis = self._create_analysis()
        action = self._decide_no_nemotron(self.context, analysis)
        self.assertIn(action.action, [ActionType.ASK_QUESTION, ActionType.SWITCH_AGENT, ActionType.COMPLETE])

    # ── TEST 19 — Different Initial Agent Execution ────────────────────────
    def test_19_different_initial_agent_execution(self) -> None:
        """Verify an interview started by a non-Alex agent runs through orchestrator identically."""
        taylor = AgentProfile(
            agent_id="taylor",
            display_name="Taylor",
            role="Frontend Lead",
            description="Evaluates web systems.",
            focal_competencies=["css_architecture", "state_management"],
            questioning_style="interactive",
            instructions="Taylor...",
        )
        self.registry.register(taylor)

        taylor_context = InterviewAIContext(
            interview_id="int-taylor-1",
            candidate_id="cand-1",
            current_round_id="frontend_round",
            current_agent_id="taylor",
            difficulty=DifficultyLevel.EASY,
            accumulated_evidence=[EvidenceItem(id="ev-t1", competency="css_architecture", signal="CSS")],
            missing_competencies=["css_architecture"],
        )

        analysis = self._create_analysis(
            overall_performance=0.88,
            competency_id="css_architecture",
            missing_information=[],
        )
        action = self._decide_no_nemotron(taylor_context, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "taylor")
        self.assertEqual(action.difficulty, DifficultyLevel.MEDIUM)

    # ── TEST 20 — Rationale Always Present and Meaningful ──────────────────
    def test_20_rationale_present_and_meaningful(self) -> None:
        """Verify NextAction always includes a non-empty, explainable rationale."""
        analysis = self._create_analysis()
        action = self._decide_no_nemotron(self.context, analysis)

        self.assertIsNotNone(action.rationale)
        self.assertGreater(len(action.rationale.strip()), 15)


class TestDynamicCrossAgentRouting(unittest.TestCase):
    """Test suite for dynamic, evidence-driven cross-agent routing (new Nemotron-driven capability).

    All Nemotron calls are mocked. These tests verify the routing CONTRACT,
    not the LLM's reasoning quality.
    """

    def setUp(self) -> None:
        # Enter the mocked provider branch independently of developer secrets.
        # Tests override this offline default with their particular responses.
        key_patch = patch.object(settings, "GROQ_ORCHESTRATOR_API_KEY", "test-orchestrator-key")
        key_patch.start()
        self.addCleanup(key_patch.stop)
        provider_patch = patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline"))
        provider_patch.start()
        self.addCleanup(provider_patch.stop)
        self.registry = AgentRegistry(register_defaults=True)
        # Register Jordan as a second agent
        from app.agents import JORDAN_PROFILE
        try:
            self.registry.register(JORDAN_PROFILE)
        except Exception:
            pass  # Already registered
        self.orchestrator = MetaOrchestrator(registry=self.registry)

    def _alex_context(self, missing_comps=None, evaluated=None):
        return InterviewAIContext(
            interview_id="int-dynamic-1",
            candidate_id="cand-dyn-1",
            current_round_id="r1",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            evaluated_competencies=evaluated or ["system_design"],
            accumulated_evidence=[EvidenceItem(id="ev-d1", competency="system_design", signal="evidence")],
            missing_competencies=missing_comps or ["scalability", "prioritization"],
        )

    def _jordan_context(self, missing_comps=None, evaluated=None):
        return InterviewAIContext(
            interview_id="int-dynamic-2",
            candidate_id="cand-dyn-1",
            current_round_id="r1",
            current_agent_id="jordan",
            difficulty=DifficultyLevel.MEDIUM,
            evaluated_competencies=evaluated or ["customer_understanding"],
            accumulated_evidence=[EvidenceItem(id="ev-d2", competency="customer_understanding", signal="evidence")],
            missing_competencies=missing_comps or ["prioritization", "technical_depth"],
        )

    def _analysis_with_product_signal(self):
        ev = EvidenceItem(
            id="ev-prod",
            competency="system_design",
            signal="checkout latency was causing customer abandonment",
            metadata={"subject": "checkout latency"},
        )
        return AnswerAnalysis(
            answer_id="ans-prod-sig",
            overall_performance=0.85,
            confidence=0.88,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(
                    competency_id="system_design",
                    assessment="Candidate introduced customer-impact signal.",
                    confidence=0.88,
                    evidence_ids=["ev-prod"],
                )
            ],
            recommended_follow_up=None,
        )

    def _analysis_with_technical_signal(self):
        ev = EvidenceItem(
            id="ev-tech",
            competency="prioritization",
            signal="chose caching instead of redesigning the service — trade-off",
            metadata={"subject": "caching vs redesign"},
        )
        return AnswerAnalysis(
            answer_id="ans-tech-sig",
            overall_performance=0.82,
            confidence=0.85,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(
                    competency_id="prioritization",
                    assessment="Candidate introduced technical trade-off signal.",
                    confidence=0.85,
                    evidence_ids=["ev-tech"],
                )
            ],
            recommended_follow_up=None,
        )

    # ── TEST 1 — Alex technical answer, no cross-agent opportunity ──────────
    def test_01_alex_technical_no_cross_agent_continues_alex(self) -> None:
        """Technical answer with no cross-agent signal continues with Alex deterministically."""
        ctx = self._alex_context(missing_comps=["scalability", "debugging"])
        ev = EvidenceItem(id="ev-a1", competency="scalability", signal="distributed caching")
        analysis = AnswerAnalysis(
            answer_id="ans-a1",
            overall_performance=0.85,
            confidence=0.88,
            vague=False,
            contradiction_detected=False,
            missing_information=["Failure modes"],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Good.", confidence=0.88, evidence_ids=["ev-a1"])
            ],
            recommended_follow_up="What failure scenarios did you design for?",
        )

        with patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline")):
            action = self.orchestrator.decide(ctx, analysis)

        # No switch should occur — probe missing info stays with Alex
        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")

    # ── TEST 2 — Nemotron cross-agent: Alex → Jordan ─────────────────────────
    def test_02_nemotron_switches_alex_to_jordan_on_product_signal(self) -> None:
        """Mocked Nemotron returns SWITCH_AGENT Jordan when product signal detected."""
        ctx = self._alex_context(missing_comps=["scalability", "prioritization"])
        analysis = self._analysis_with_product_signal()

        nemotron_response = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "jordan",
            "competency": "prioritization",
            "rationale": "Candidate introduced customer-impact signal relevant to Jordan's prioritization competency.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["customer abandonment", "checkout latency"],
            "unresolved_target_competencies": ["prioritization"],
            "question_text": None,
            "metadata": {"source_agent": "alex", "priority_applied": "cross_agent_opportunity"},
        }

        async def fake_call_groq(**kwargs):
            return nemotron_response

        with patch("app.orchestrator.graph.call_groq", new=fake_call_groq):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "jordan")
        self.assertEqual(action.competency, "prioritization")
        self.assertIn("customer-impact", action.rationale)
        self.assertTrue(action.metadata.get("cross_agent_opportunity"))
        self.assertTrue(action.metadata.get("nemotron_used"))

    # ── TEST 3 — Nemotron cross-agent: Jordan → Alex ─────────────────────────
    def test_03_nemotron_switches_jordan_to_alex_on_technical_signal(self) -> None:
        """Mocked Nemotron returns SWITCH_AGENT Alex when technical trade-off signal detected from Jordan."""
        ctx = self._jordan_context(missing_comps=["technical_depth", "prioritization"])
        analysis = self._analysis_with_technical_signal()

        nemotron_response = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "alex",
            "competency": "technical_depth",
            "rationale": "Candidate introduced technical trade-off signal relevant to Alex's unresolved competency.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["caching vs redesign", "trade-off"],
            "unresolved_target_competencies": ["technical_depth"],
            "question_text": None,
            "metadata": {"source_agent": "jordan", "priority_applied": "cross_agent_opportunity"},
        }

        async def fake_call_groq(**kwargs):
            return nemotron_response

        with patch("app.orchestrator.graph.call_groq", new=fake_call_groq):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.competency, "technical_depth")
        self.assertTrue(action.metadata.get("cross_agent_opportunity"))

    # ── TEST 4 — Alex → Jordan → Alex works ─────────────────────────────────
    def test_04_alex_jordan_alex_roundtrip(self) -> None:
        """Simulate Alex→Jordan→Alex routing with mocked Nemotron decisions."""
        # Turn 1: Alex → switch to Jordan
        ctx_alex = self._alex_context(missing_comps=["scalability", "prioritization"])
        analysis_1 = self._analysis_with_product_signal()

        nemotron_switch_to_jordan = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "jordan",
            "competency": "prioritization",
            "rationale": "Product signal from Alex.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["customer"],
            "unresolved_target_competencies": ["prioritization"],
            "question_text": None,
            "metadata": {},
        }

        async def fake_to_jordan(**kwargs):
            return nemotron_switch_to_jordan

        with patch("app.orchestrator.graph.call_groq", new=fake_to_jordan):
            action_1 = self.orchestrator.decide(ctx_alex, analysis_1)

        self.assertEqual(action_1.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action_1.target_agent_id, "jordan")

        # Turn 2: Jordan → switch back to Alex
        ctx_jordan = self._jordan_context(missing_comps=["technical_depth"])
        analysis_2 = self._analysis_with_technical_signal()

        nemotron_switch_to_alex = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "alex",
            "competency": "technical_depth",
            "rationale": "Technical trade-off signal from Jordan.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["trade-off"],
            "unresolved_target_competencies": ["technical_depth"],
            "question_text": None,
            "metadata": {},
        }

        async def fake_to_alex(**kwargs):
            return nemotron_switch_to_alex

        with patch("app.orchestrator.graph.call_groq", new=fake_to_alex):
            action_2 = self.orchestrator.decide(ctx_jordan, analysis_2)

        self.assertEqual(action_2.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action_2.target_agent_id, "alex")

    # ── TEST 5 — Three-agent registry works ─────────────────────────────────
    def test_05_three_agent_registry_dynamic_routing(self) -> None:
        """Three-agent registry routes dynamically based on competency signals."""
        behavioral = AgentProfile(
            agent_id="behavioral",
            display_name="Morgan",
            role="People Lead",
            description="Evaluates behavioral competencies.",
            focal_competencies=["leadership", "collaboration"],
            questioning_style="narrative",
            instructions="Morgan...",
        )
        self.registry.register(behavioral)

        ctx = self._alex_context(missing_comps=["scalability", "leadership"])
        ev = EvidenceItem(id="ev-b1", competency="scalability", signal="evidence")
        analysis = AnswerAnalysis(
            answer_id="ans-b1",
            overall_performance=0.88,
            confidence=0.90,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Good.", confidence=0.90, evidence_ids=["ev-b1"])
            ],
        )

        with patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline")):
            action = self.orchestrator.decide(ctx, analysis)

        # Should route to behavioral agent (only agent covering "leadership")
        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "behavioral")
        self.assertEqual(action.competency, "leadership")

    # ── TEST 6 — Routing does not depend on array order ──────────────────────
    def test_06_routing_not_dependent_on_agent_array_order(self) -> None:
        """Routing selects best-overlap agent, not first-in-array."""
        agentA = AgentProfile(
            agent_id="aaa",
            display_name="First",
            role="First",
            description="Has no relevant competency",
            focal_competencies=["irrelevant_comp"],
            questioning_style="neutral",
            instructions="First...",
        )
        agentB = AgentProfile(
            agent_id="bbb",
            display_name="Second",
            role="Second",
            description="Has the relevant competency",
            focal_competencies=["target_comp", "target_comp_2"],
            questioning_style="probing",
            instructions="Second...",
        )
        registry_ordered = AgentRegistry(register_defaults=False)
        registry_ordered.register(agentA)
        registry_ordered.register(agentB)

        # Build alex-like agent as current
        current = AgentProfile(
            agent_id="current_agent",
            display_name="Current",
            role="Lead",
            description="Current agent.",
            focal_competencies=["current_comp"],
            questioning_style="neutral",
            instructions="Current...",
        )
        registry_ordered.register(current)
        orch = MetaOrchestrator(registry=registry_ordered)

        ctx = InterviewAIContext(
            interview_id="int-order-1",
            candidate_id="cand-1",
            current_round_id="r1",
            current_agent_id="current_agent",
            difficulty=DifficultyLevel.MEDIUM,
            evaluated_competencies=["current_comp"],
            accumulated_evidence=[EvidenceItem(id="ev-o1", competency="current_comp", signal="ev")],
            missing_competencies=["target_comp", "target_comp_2"],
        )
        ev = EvidenceItem(id="ev-o2", competency="current_comp", signal="good")
        analysis = AnswerAnalysis(
            answer_id="ans-o1",
            overall_performance=0.90,
            confidence=0.90,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="current_comp", assessment="Deep.", confidence=0.90, evidence_ids=["ev-o2"])
            ],
        )

        with patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline")):
            action = orch.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "bbb")  # Best overlap (2 competencies vs 1)

    # ── TEST 7 — No hardcoded Alex→Jordan routing ────────────────────────────
    def test_07_no_hardcoded_alex_jordan_routing(self) -> None:
        """Verify orchestrator code contains no hardcoded Alex→Jordan transitions."""
        import inspect
        import app.orchestrator.graph as graph_module
        import app.orchestrator.policies as policies_module
        source_graph = inspect.getsource(graph_module)
        source_policies = inspect.getsource(policies_module)
        
        # These are the forbidden hardcoded patterns
        forbidden = [
            "if current_agent == \"alex\"",
            "if current_agent == 'alex'",
            "target = \"jordan\"",
            "target = 'jordan'",
            "== \"alex\":\n            target = \"jordan\"",
        ]
        for pattern in forbidden:
            self.assertNotIn(pattern, source_graph, f"Hardcoded routing found in graph.py: {pattern!r}")
            self.assertNotIn(pattern, source_policies, f"Hardcoded routing found in policies.py: {pattern!r}")

    # ── TEST 8 — Strong detailed answer advances competency ──────────────────
    def test_08_strong_detailed_advances_new_competency(self) -> None:
        """Strong + detailed (no missing info) → advance to next competency, not repeat."""
        ctx = self._alex_context(missing_comps=["scalability", "debugging"])
        ev = EvidenceItem(id="ev-s1", competency="scalability", signal="deep answer")
        analysis = AnswerAnalysis(
            answer_id="ans-s1",
            overall_performance=0.92,
            confidence=0.93,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Very deep.", confidence=0.93, evidence_ids=["ev-s1"])
            ],
        )

        with patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline")):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertNotEqual(action.competency, "scalability")  # Advanced to next!
        self.assertEqual(action.difficulty, DifficultyLevel.HARD)  # Bumped

    # ── TEST 9 — Strong shallow probes deeper, does not switch ───────────────
    def test_09_strong_shallow_probes_deeper_not_switch(self) -> None:
        """Strong (0.83) but shallow (has missing info) → probe deeper, not switch."""
        ctx = self._alex_context(missing_comps=["scalability"])
        ev = EvidenceItem(id="ev-ss1", competency="scalability", signal="shallow answer")
        analysis = AnswerAnalysis(
            answer_id="ans-ss1",
            overall_performance=0.83,
            confidence=0.85,
            vague=False,
            contradiction_detected=False,
            missing_information=["Partition handling strategy"],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Shallow.", confidence=0.85, evidence_ids=["ev-ss1"])
            ],
        )

        with patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline")):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertIn("servers cannot communicate", action.question_text)
        self.assertIn("conflicting writes", action.question_text)
        self.assertEqual(action.question_text.count("?"), 1)

    # ── TEST 10 — Vague answer → clarification ───────────────────────────────
    def test_10_vague_answer_forced_clarification(self) -> None:
        """Vague answer always forces clarification regardless of Nemotron routing."""
        ctx = self._alex_context()
        ev = EvidenceItem(id="ev-v1", competency="scalability", signal="vague stuff")
        analysis = AnswerAnalysis(
            answer_id="ans-v1",
            overall_performance=0.35,
            confidence=0.60,
            vague=True,
            vague_reason="Used generic terms like 'stuff' and 'things'.",
            contradiction_detected=False,
            missing_information=["concrete details"],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Vague.", confidence=0.60, evidence_ids=["ev-v1"])
            ],
            recommended_follow_up="Can you give a specific example?",
        )

        # Even if Nemotron returns SWITCH_AGENT, vague must force ASK_QUESTION clarification
        async def always_switch(**kwargs):
            return {
                "action": "SWITCH_AGENT",
                "target_agent_id": "jordan",
                "competency": "prioritization",
                "rationale": "Nemotron wants to switch.",
                "cross_agent_opportunity": True,
                "trigger_signals": [],
                "unresolved_target_competencies": [],
                "metadata": {},
            }

        with patch("app.orchestrator.graph.call_groq", new=always_switch):
            action = self.orchestrator.decide(ctx, analysis)

        # Even with a mocked Nemotron that wants to SWITCH, vague must force ASK_QUESTION
        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertIn("vague", action.rationale.lower())
        # Must NOT have switched agent
        self.assertEqual(action.target_agent_id, "alex")

    # ── TEST 11 — Contradiction forces clarification ──────────────────────────
    def test_11_contradiction_forced_clarification_no_nemotron(self) -> None:
        """Contradiction always forces clarification regardless of Nemotron routing."""
        ctx = self._alex_context()
        ev = EvidenceItem(id="ev-c1", competency="scalability", signal="contradictory statement")
        analysis = AnswerAnalysis(
            answer_id="ans-c1",
            overall_performance=0.40,
            confidence=0.70,
            vague=False,
            contradiction_detected=True,
            contradiction_details="Stated no Postgres experience but earlier claimed Postgres architect.",
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Contradiction.", confidence=0.70, evidence_ids=["ev-c1"])
            ],
            recommended_follow_up="Please clarify your Postgres experience.",
        )

        # Even if Nemotron wants to SWITCH_AGENT, contradiction must force clarification
        async def always_switch(**kwargs):
            return {
                "action": "SWITCH_AGENT",
                "target_agent_id": "jordan",
                "competency": "prioritization",
                "rationale": "Nemotron wants to switch.",
                "cross_agent_opportunity": True,
                "trigger_signals": [],
                "unresolved_target_competencies": [],
                "metadata": {},
            }

        with patch("app.orchestrator.graph.call_groq", new=always_switch):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertIn("contradiction", action.rationale.lower())
        # Must NOT have switched agent even though Nemotron wanted to
        self.assertEqual(action.target_agent_id, "alex")

    # ── TEST 12 — Question history prevents repetition ──────────────────────
    def test_12_question_history_sufficient_status_respected(self) -> None:
        """QuestionHistoryItem with SUFFICIENT status is tracked in context."""
        ctx = self._alex_context()
        item = QuestionHistoryItem(
            agent_id="alex",
            competency="scalability",
            question_text="How did you design for partition tolerance?",
            difficulty=DifficultyLevel.MEDIUM,
            exploration_status="SUFFICIENT",
        )
        ctx.add_question_history(item)

        self.assertTrue(ctx.is_competency_sufficiently_asked("scalability"))
        self.assertFalse(ctx.is_competency_sufficiently_asked("debugging"))
        self.assertEqual(len(ctx.get_questions_for_competency("scalability")), 1)

    # ── TEST 13 — Invalid Nemotron target agent → safe fallback ─────────────
    def test_13_invalid_nemotron_target_agent_falls_back(self) -> None:
        """Invalid Nemotron target_agent_id → validation rejects, deterministic fallback applied."""
        ctx = self._alex_context(missing_comps=["scalability"])
        ev = EvidenceItem(id="ev-inv", competency="scalability", signal="answer")
        analysis = AnswerAnalysis(
            answer_id="ans-inv",
            overall_performance=0.85,
            confidence=0.88,
            vague=False,
            contradiction_detected=False,
            missing_information=["details"],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Good.", confidence=0.88, evidence_ids=["ev-inv"])
            ],
        )

        # Nemotron returns a non-existent agent
        nemotron_invalid = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "nonexistent_agent_xyz",
            "competency": "scalability",
            "rationale": "Some rationale.",
            "cross_agent_opportunity": True,
            "trigger_signals": [],
            "unresolved_target_competencies": [],
            "question_text": None,
            "metadata": {},
        }

        async def fake_invalid(**kwargs):
            return nemotron_invalid

        with patch("app.orchestrator.graph.call_groq", new=fake_invalid):
            action = self.orchestrator.decide(ctx, analysis)

        # Should NOT use the invalid Nemotron decision
        self.assertNotEqual(action.target_agent_id, "nonexistent_agent_xyz")
        self.assertFalse(action.metadata.get("nemotron_used", False))
        # Should fall back to probe_missing_info
        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")

    # ── TEST 14 — Malformed Nemotron output → safe fallback ─────────────────
    def test_14_malformed_nemotron_output_falls_back(self) -> None:
        """Malformed Nemotron JSON → NemotronRoutingDecision validation fails, deterministic fallback applied."""
        ctx = self._alex_context(missing_comps=["debugging"])
        ev = EvidenceItem(id="ev-malformed", competency="debugging", signal="answer")
        analysis = AnswerAnalysis(
            answer_id="ans-malformed",
            overall_performance=0.75,
            confidence=0.80,
            vague=False,
            contradiction_detected=False,
            missing_information=["stack trace analysis"],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="debugging", assessment="Good.", confidence=0.80, evidence_ids=["ev-malformed"])
            ],
        )

        # Nemotron returns completely malformed output
        async def fake_malformed(**kwargs):
            return {"garbage_field": "not_valid", "wrong_action": "INVALID_ACTION"}

        with patch("app.orchestrator.graph.call_groq", new=fake_malformed):
            action = self.orchestrator.decide(ctx, analysis)

        # Should fall back safely
        self.assertIsNotNone(action)
        self.assertIn(action.action, [ActionType.ASK_QUESTION, ActionType.SWITCH_AGENT, ActionType.COMPLETE])
        self.assertFalse(action.metadata.get("nemotron_used", False))

    # ── TEST 15 — Completion respects all agents ─────────────────────────────
    def test_15_completion_only_when_all_agents_objectives_covered(self) -> None:
        """COMPLETE is only returned when ALL agents' objectives are sufficiently covered."""
        ctx = InterviewAIContext(
            interview_id="int-comp-1",
            candidate_id="cand-comp-1",
            current_round_id="r1",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            evaluated_competencies=[
                "system_design", "scalability", "debugging",  # Alex competencies
                "customer_understanding", "prioritization",    # Jordan competencies
            ],
            accumulated_evidence=[EvidenceItem(id="ev-c1", competency="scalability", signal="evidence")],
            missing_competencies=[],
        )

        ev = EvidenceItem(id="ev-comp", competency="scalability", signal="final answer")
        analysis = AnswerAnalysis(
            answer_id="ans-comp",
            overall_performance=0.90,
            confidence=0.90,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Deep.", confidence=0.90, evidence_ids=["ev-comp"])
            ],
        )

        with patch("app.orchestrator.graph.call_groq", side_effect=Exception("mocked offline")):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.COMPLETE)

    # ── TEST 16 — record_question helper works ────────────────────────────────
    def test_16_record_question_helper(self) -> None:
        """MetaOrchestrator.record_question() correctly adds QuestionHistoryItem."""
        from app.agents.models import NextAction
        ctx = self._alex_context()
        action = NextAction(
            action=ActionType.ASK_QUESTION,
            target_agent_id="alex",
            competency="scalability",
            difficulty=DifficultyLevel.MEDIUM,
            question_text="How did you handle partition tolerance?",
            rationale="Test rationale.",
        )

        self.assertEqual(len(ctx.question_history), 0)
        MetaOrchestrator.record_question(ctx, action, exploration_status="PARTIAL")
        self.assertEqual(len(ctx.question_history), 1)
        self.assertEqual(ctx.question_history[0].competency, "scalability")
        self.assertEqual(ctx.question_history[0].exploration_status, "PARTIAL")
        self.assertEqual(ctx.question_history[0].question_text, "How did you handle partition tolerance?")

    # ── TEST 17 — NemotronRoutingDecision validates correctly ────────────────
    def test_17_nemotron_routing_decision_validates(self) -> None:
        """NemotronRoutingDecision accepts valid decisions and rejects malformed ones."""
        valid = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "jordan",
            "competency": "prioritization",
            "rationale": "Product signal detected.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["customer impact"],
            "unresolved_target_competencies": ["prioritization"],
            "metadata": {},
        }
        decision = NemotronRoutingDecision.model_validate(valid)
        self.assertEqual(decision.action, "SWITCH_AGENT")
        self.assertEqual(decision.target_agent_id, "jordan")
        self.assertEqual(decision.to_action_type(), ActionType.SWITCH_AGENT)

    def test_18_nemotron_routing_decision_rejects_invalid_action(self) -> None:
        """NemotronRoutingDecision rejects an invalid action string."""
        from pydantic import ValidationError as PydanticValidationError
        invalid = {
            "action": "INVALID_ACTION",
            "target_agent_id": "jordan",
            "competency": "prioritization",
            "rationale": "Some rationale.",
        }
        with self.assertRaises(PydanticValidationError):
            NemotronRoutingDecision.model_validate(invalid)

    def test_19_nemotron_switch_to_current_agent_rejected(self) -> None:
        """Nemotron SWITCH_AGENT to the current agent is rejected by validate_nemotron."""
        ctx = self._alex_context(missing_comps=["scalability"])
        ev = EvidenceItem(id="ev-self", competency="scalability", signal="answer")
        analysis = AnswerAnalysis(
            answer_id="ans-self",
            overall_performance=0.80,
            confidence=0.80,
            vague=False,
            contradiction_detected=False,
            missing_information=["details"],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Good.", confidence=0.80, evidence_ids=["ev-self"])
            ],
        )

        # Nemotron incorrectly switches to the current agent (alex → alex)
        async def fake_self_switch(**kwargs):
            return {
                "action": "SWITCH_AGENT",
                "target_agent_id": "alex",  # Same as current!
                "competency": "scalability",
                "rationale": "Some rationale.",
                "cross_agent_opportunity": False,
                "trigger_signals": [],
                "unresolved_target_competencies": [],
                "metadata": {},
            }

        with patch("app.orchestrator.graph.call_groq", new=fake_self_switch):
            action = self.orchestrator.decide(ctx, analysis)

        # Should reject this and use fallback
        self.assertFalse(action.metadata.get("nemotron_used", False))

    def test_20_metadata_tracks_routing_trace(self) -> None:
        """Routing trace (cross_agent, trigger_signals, nemotron_used) appears in NextAction.metadata."""
        ctx = self._alex_context(missing_comps=["scalability", "prioritization"])
        analysis = self._analysis_with_product_signal()

        nemotron_resp = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "jordan",
            "competency": "prioritization",
            "rationale": "Cross-agent opportunity.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["customer abandonment"],
            "unresolved_target_competencies": ["prioritization"],
            "metadata": {"priority_applied": "cross_agent_opportunity"},
        }

        async def fake_valid(**kwargs):
            return nemotron_resp

        with patch("app.orchestrator.graph.call_groq", new=fake_valid):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertTrue(action.metadata.get("nemotron_used"))
        self.assertTrue(action.metadata.get("cross_agent_opportunity"))
        self.assertIn("customer abandonment", action.metadata.get("trigger_signals", []))
        self.assertIn("alex", action.metadata.get("source_agent", ""))
        self.assertIn("jordan", action.metadata.get("target_agent", ""))


class TestTask6PersonaGroundedDialogue(unittest.TestCase):
    """Test suite verifying Task 6: Persona-Grounded Dialogue Phrasing in Nemotron Routing & Handoff Verbalization."""

    def setUp(self) -> None:
        self.registry = AgentRegistry(register_defaults=True)
        from app.agents import JORDAN_PROFILE
        try:
            self.registry.register(JORDAN_PROFILE)
        except Exception:
            pass
        self.orchestrator = MetaOrchestrator(registry=self.registry)
        self._orig_orch_key = getattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
        settings.GROQ_ORCHESTRATOR_API_KEY = "mock-orch-key"

    def tearDown(self) -> None:
        settings.GROQ_ORCHESTRATOR_API_KEY = self._orig_orch_key

    def _alex_context(self, missing_comps=None, evaluated=None):
        return InterviewAIContext(
            interview_id="int-task6-1",
            candidate_id="cand-task6-1",
            current_round_id="r1",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            evaluated_competencies=evaluated or ["system_design"],
            accumulated_evidence=[EvidenceItem(id="ev-t6-1", competency="system_design", signal="evidence")],
            missing_competencies=missing_comps or ["scalability", "prioritization"],
        )

    def _analysis(self):
        ev = EvidenceItem(
            id="ev-t6-2",
            competency="scalability",
            signal="caching layer in Redis",
            metadata={"subject": "caching"},
        )
        return AnswerAnalysis(
            answer_id="ans-t6-1",
            overall_performance=0.85,
            confidence=0.88,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(
                    competency_id="scalability",
                    assessment="Good understanding of Redis caching.",
                    confidence=0.88,
                    evidence_ids=["ev-t6-2"],
                )
            ],
            recommended_follow_up="How did you handle cache invalidation?",
        )

    # ── TEST 1 — Persona fields and spoken dialogue rules serialized in prompt ──
    def test_01_persona_fields_and_rules_serialized_in_prompt(self) -> None:
        """Prompt receives active agent persona instructions, role, questioning style, and spoken dialogue rules."""
        import json
        from app.orchestrator.prompts import build_nemotron_routing_messages

        ctx = self._alex_context()
        analysis = self._analysis()

        messages = build_nemotron_routing_messages(
            context=ctx,
            analysis=analysis,
            registry=self.registry,
            current_question_text="Tell me about your architecture.",
        )

        # 1. Check system prompt contains spoken dialogue rules
        sys_content = messages[0]["content"]
        self.assertIn("SPOKEN DIALOGUE RULES", sys_content)
        self.assertIn("SWITCH_AGENT", sys_content)
        self.assertIn("verbal handoff", sys_content)
        self.assertIn("display_name", sys_content)
        self.assertIn("COMPLETE", sys_content)

        # 2. Check user prompt includes serialized agent questioning style & instructions
        user_content = messages[1]["content"]
        state_str = user_content.split("INTERVIEW STATE:\n")[1].split("\n\nReturn your routing decision")[0]
        state = json.loads(state_str)

        agent_reg = {a["agent_id"]: a for a in state["agent_registry"]}
        self.assertIn("alex", agent_reg)
        self.assertIn("jordan", agent_reg)

        # Verify persona fields exist and are populated
        self.assertTrue(len(agent_reg["alex"]["questioning_style"]) > 0)
        self.assertTrue(len(agent_reg["alex"]["instructions"]) > 0)
        self.assertTrue(len(agent_reg["jordan"]["questioning_style"]) > 0)
        self.assertTrue(len(agent_reg["jordan"]["instructions"]) > 0)

    # ── TEST 2 — Nemotron question_text preserved for ASK_QUESTION ────────────
    def test_02_nemotron_question_text_used_for_ask_question(self) -> None:
        """Nemotron's candidate-facing question_text is preserved in NextAction for ASK_QUESTION."""
        ctx = self._alex_context(missing_comps=["scalability"])
        analysis = self._analysis()

        custom_q = "Under peak load, how did you ensure cache invalidation didn't trigger a thundering herd?"
        nemotron_resp = {
            "action": "ASK_QUESTION",
            "target_agent_id": "alex",
            "competency": "scalability",
            "rationale": "Probe deeper into caching resilience.",
            "cross_agent_opportunity": False,
            "trigger_signals": ["caching"],
            "unresolved_target_competencies": ["scalability"],
            "question_text": custom_q,
            "metadata": {"source_agent": "alex", "priority_applied": "probe_current_competency"},
        }

        async def fake_groq(**kwargs):
            return nemotron_resp

        with patch("app.orchestrator.graph.call_groq", new=fake_groq):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.ASK_QUESTION)
        self.assertEqual(action.target_agent_id, "alex")
        self.assertEqual(action.question_text, custom_q)

    # ── TEST 3 — Nemotron verbal handoff preserved for SWITCH_AGENT ───────────
    def test_03_nemotron_switch_agent_handoff_dialogue_preserved(self) -> None:
        """Nemotron's verbal handoff dialogue is preserved in NextAction for SWITCH_AGENT."""
        ctx = self._alex_context(missing_comps=["scalability", "prioritization"])
        analysis = self._analysis()

        handoff_text = (
            "Thank you for explaining the Redis caching layer. I'm going to pass you over to "
            "Jordan to discuss how you prioritized this technical investment against other user-facing features."
        )
        nemotron_resp = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "jordan",
            "competency": "prioritization",
            "rationale": "Cross-agent product trade-off signal.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["trade-off"],
            "unresolved_target_competencies": ["prioritization"],
            "question_text": handoff_text,
            "metadata": {"source_agent": "alex", "priority_applied": "cross_agent_opportunity"},
        }

        async def fake_groq(**kwargs):
            return nemotron_resp

        with patch("app.orchestrator.graph.call_groq", new=fake_groq):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "jordan")
        self.assertEqual(action.question_text, handoff_text)

    # ── TEST 4 — SWITCH_AGENT fallback names target agent display name ─────────
    def test_04_switch_agent_fallback_names_target_agent(self) -> None:
        """When Nemotron returns empty or missing question_text, fallback handoff names target agent's display_name."""
        ctx = self._alex_context(missing_comps=["scalability", "prioritization"])
        analysis = self._analysis()

        for empty_q in [None, "", "   ", "short"]:
            nemotron_resp = {
                "action": "SWITCH_AGENT",
                "target_agent_id": "jordan",
                "competency": "prioritization",
                "rationale": "Switching to product interviewer.",
                "cross_agent_opportunity": True,
                "trigger_signals": ["product"],
                "unresolved_target_competencies": ["prioritization"],
                "question_text": empty_q,
                "metadata": {"source_agent": "alex", "priority_applied": "cross_agent_opportunity"},
            }

            async def fake_groq(**kwargs):
                return nemotron_resp

            with patch("app.orchestrator.graph.call_groq", new=fake_groq):
                action = self.orchestrator.decide(ctx, analysis)

            self.assertEqual(action.action, ActionType.SWITCH_AGENT)
            self.assertEqual(action.target_agent_id, "jordan")
            self.assertIn("Jordan", action.question_text)
            self.assertIn("hand over to Jordan", action.question_text)
            self.assertIn("prioritization", action.question_text)

    # ── TEST 5 — Safeguard 1: Safe fallback on unregistered/invalid target ────
    def test_05_switch_agent_safeguard_unregistered_target(self) -> None:
        """SWITCH_AGENT fallback never crashes when target agent profile is missing/unregistered."""
        from app.orchestrator.graph import build_action_from_nemotron

        ctx = self._alex_context()
        analysis = self._analysis()

        # Target agent 'nonexistent_agent' is NOT in registry
        self.assertFalse(self.registry.has_agent("nonexistent_agent"))

        # Case A: Nemotron returns no valid question_text and nonexistent target
        decision = NemotronRoutingDecision(
            action="SWITCH_AGENT",
            target_agent_id="nonexistent_agent",
            competency="unknown_comp",
            rationale="Attempting switch to unlisted agent.",
            cross_agent_opportunity=True,
            trigger_signals=[],
            unresolved_target_competencies=[],
            question_text="",  # triggers fallback
        )

        # Must NOT raise AttributeError or any exception
        action = build_action_from_nemotron(
            decision=decision,
            registry=self.registry,
            context=ctx,
            analysis=analysis,
            curr_profile=self.registry.get_profile("alex"),
            effective_missing=["scalability"],
        )

        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "nonexistent_agent")
        # Difficulty safely falls back to context.difficulty without dereferencing None
        self.assertEqual(action.difficulty, ctx.difficulty)
        # Safe generic handoff used
        self.assertIn("our co-interviewer", action.question_text)

        # Case B: Nemotron returns valid question_text with nonexistent target
        decision_with_text = NemotronRoutingDecision(
            action="SWITCH_AGENT",
            target_agent_id="nonexistent_agent",
            competency="unknown_comp",
            rationale="Switch with valid text.",
            cross_agent_opportunity=True,
            trigger_signals=[],
            unresolved_target_competencies=[],
            question_text="I will now hand you over to another specialist.",
        )
        action_with_text = build_action_from_nemotron(
            decision=decision_with_text,
            registry=self.registry,
            context=ctx,
            analysis=analysis,
            curr_profile=self.registry.get_profile("alex"),
            effective_missing=["scalability"],
        )

        self.assertEqual(action_with_text.question_text, "I will now hand you over to another specialist.")
        self.assertEqual(action_with_text.difficulty, ctx.difficulty)

        # Case C: Full MetaOrchestrator pipeline handles unregistered target via safe fallback
        nemotron_invalid_target = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "nonexistent_agent",
            "competency": "prioritization",
            "rationale": "Switching to unlisted agent.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["product"],
            "unresolved_target_competencies": ["prioritization"],
            "question_text": None,
            "metadata": {},
        }

        async def fake_invalid_target(**kwargs):
            return nemotron_invalid_target

        with patch("app.orchestrator.graph.call_groq", new=fake_invalid_target):
            pipeline_action = self.orchestrator.decide(ctx, analysis)

        # Pipeline completes safely, falls back to deterministic registered target (Jordan)
        self.assertEqual(pipeline_action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(pipeline_action.target_agent_id, "jordan")
        self.assertFalse(pipeline_action.metadata.get("nemotron_used", False))

    # ── TEST 6 — COMPLETE action closing dialogue ─────────────────────────────
    def test_06_complete_action_closing_dialogue(self) -> None:
        """COMPLETE action produces candidate-facing closing statement from Nemotron or fallback."""
        ctx = self._alex_context(missing_comps=[], evaluated=["system_design", "scalability"])
        analysis = self._analysis()

        # Case A: Nemotron provides tailored closing dialogue
        nemotron_closing = "Thank you so much for walking through your system architecture today. That concludes our interview session!"
        resp_with_closing = {
            "action": "COMPLETE",
            "target_agent_id": "alex",
            "competency": None,
            "rationale": "All competencies evaluated.",
            "cross_agent_opportunity": False,
            "trigger_signals": [],
            "unresolved_target_competencies": [],
            "question_text": nemotron_closing,
            "metadata": {"priority_applied": "all_competencies_covered"},
        }

        async def fake_complete(**kwargs):
            return resp_with_closing

        with patch("app.orchestrator.graph.call_groq", new=fake_complete):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.COMPLETE)
        self.assertEqual(action.question_text, nemotron_closing)

        # Case B: Fallback closing dialogue when question_text is missing
        resp_fallback_closing = dict(resp_with_closing)
        resp_fallback_closing["question_text"] = None

        async def fake_fallback_complete(**kwargs):
            return resp_fallback_closing

        with patch("app.orchestrator.graph.call_groq", new=fake_fallback_complete):
            action_fb = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action_fb.action, ActionType.COMPLETE)
        self.assertIn("Thank you for your time today", action_fb.question_text)
        self.assertIn("concludes our interview", action_fb.question_text)

    # ── TEST 7 — N-Agent extensibility with custom 3rd agent persona ───────────
    def test_07_n_agent_extensibility_custom_persona(self) -> None:
        """Custom 3rd agent persona instructions are serialized and handled without hardcoded logic."""
        import json
        from app.orchestrator.prompts import build_nemotron_routing_messages

        taylor = AgentProfile(
            agent_id="taylor",
            display_name="Taylor",
            role="Accessibility & Frontend Architecture Specialist",
            description="Evaluates web standards, WCAG compliance, and UI performance.",
            focal_competencies=["accessibility", "frontend_architecture"],
            questioning_style="Empathy-driven, scenario-based inquiry with emphasis on assistive tech",
            instructions="Challenge candidate on keyboard navigation, ARIA landmarks, and screen reader UX.",
        )
        self.registry.register(taylor)

        ctx = self._alex_context(missing_comps=["scalability", "accessibility"])
        analysis = self._analysis()

        messages = build_nemotron_routing_messages(
            context=ctx,
            analysis=analysis,
            registry=self.registry,
        )

        user_content = messages[1]["content"]
        state_str = user_content.split("INTERVIEW STATE:\n")[1].split("\n\nReturn your routing decision")[0]
        state = json.loads(state_str)

        agent_reg = {a["agent_id"]: a for a in state["agent_registry"]}
        self.assertIn("taylor", agent_reg)
        self.assertEqual(
            agent_reg["taylor"]["questioning_style"],
            "Empathy-driven, scenario-based inquiry with emphasis on assistive tech",
        )
        self.assertIn("keyboard navigation", agent_reg["taylor"]["instructions"])

        # Handoff to Taylor without question_text names Taylor dynamically
        nemotron_switch_to_taylor = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "taylor",
            "competency": "accessibility",
            "rationale": "Candidate mentioned UI accessibility.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["accessibility"],
            "unresolved_target_competencies": ["accessibility"],
            "question_text": None,
            "metadata": {},
        }

        async def fake_switch_taylor(**kwargs):
            return nemotron_switch_to_taylor

        with patch("app.orchestrator.graph.call_groq", new=fake_switch_taylor):
            action = self.orchestrator.decide(ctx, analysis)

        self.assertEqual(action.action, ActionType.SWITCH_AGENT)
        self.assertEqual(action.target_agent_id, "taylor")
        self.assertIn("Taylor", action.question_text)
        self.assertIn("accessibility", action.question_text)


class TestGroqMetaOrchestratorMigration(unittest.TestCase):
    """Test suite verifying Groq migration, credential isolation, and shared transport reuse."""

    def setUp(self) -> None:
        self.registry = AgentRegistry(register_defaults=True)
        from app.agents import JORDAN_PROFILE
        try:
            self.registry.register(JORDAN_PROFILE)
        except Exception:
            pass
        self.orchestrator = MetaOrchestrator(registry=self.registry)
        self.orig_orch_key = getattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "")
        self.orig_m1_key = getattr(settings, "GROQ_API_KEY", "")
        self.orig_m1_alias_key = getattr(settings, "GROQ_M1_API_KEY", "")

    def tearDown(self) -> None:
        settings.GROQ_ORCHESTRATOR_API_KEY = self.orig_orch_key
        settings.GROQ_API_KEY = self.orig_m1_key
        settings.GROQ_M1_API_KEY = self.orig_m1_alias_key

    def _alex_context(self) -> InterviewAIContext:
        return InterviewAIContext(
            interview_id="int-groq-mig-1",
            candidate_id="cand-groq-mig-1",
            current_round_id="technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            evaluated_competencies=["system_design"],
            accumulated_evidence=[EvidenceItem(id="ev-gm-1", competency="system_design", signal="Initial evidence")],
            missing_competencies=["scalability", "prioritization"],
        )

    def _analysis(self) -> AnswerAnalysis:
        ev = EvidenceItem(id="ev-gm-2", competency="scalability", signal="Redis caching discussion")
        return AnswerAnalysis(
            answer_id="ans-gm-1",
            overall_performance=0.88,
            confidence=0.91,
            vague=False,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[
                CompetencyFinding(competency_id="scalability", assessment="Strong understanding.", confidence=0.91, evidence_ids=["ev-gm-2"])
            ],
            recommended_follow_up="How did you handle cache stampede?",
        )

    # ── TEST 1: Orchestrator uses dedicated Groq configuration ────────────────
    def test_01_orchestrator_uses_dedicated_groq_config(self) -> None:
        """Meta-Orchestrator invokes call_groq with dedicated GROQ_ORCHESTRATOR_* settings."""
        settings.GROQ_ORCHESTRATOR_API_KEY = "dedicated-orchestrator-secret-key"
        settings.GROQ_ORCHESTRATOR_MODEL = "openai/gpt-oss-20b"
        settings.GROQ_ORCHESTRATOR_BASE_URL = "https://api.groq.com/openai/v1"
        settings.GROQ_ORCHESTRATOR_TIMEOUT_SECONDS = 15.0

        ctx = self._alex_context()
        analysis = self._analysis()

        mock_decision = {
            "action": "ASK_QUESTION",
            "target_agent_id": "alex",
            "competency": "scalability",
            "rationale": "Deepening caching inquiry.",
            "cross_agent_opportunity": False,
            "trigger_signals": [],
            "unresolved_target_competencies": ["scalability"],
            "question_text": "How do you invalidate cache keys under heavy write bursts?",
        }

        with patch("app.orchestrator.graph.call_groq", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_decision
            action = self.orchestrator.decide(ctx, analysis)

            self.assertTrue(mock_call.called)
            call_kwargs = mock_call.call_args[1]
            self.assertEqual(call_kwargs["api_key"], "dedicated-orchestrator-secret-key")
            self.assertEqual(call_kwargs["model"], "openai/gpt-oss-20b")
            self.assertEqual(call_kwargs["base_url"], "https://api.groq.com/openai/v1")
            self.assertEqual(call_kwargs["timeout_seconds"], 15.0)
            self.assertEqual(action.action, ActionType.ASK_QUESTION)
            self.assertEqual(action.question_text, "How do you invalidate cache keys under heavy write bursts?")

    # ── TEST 2: M1 Groq key not reused by orchestrator ────────────────────────
    def test_02_m1_groq_key_not_reused_by_orchestrator(self) -> None:
        """When GROQ_ORCHESTRATOR_API_KEY is empty, orchestrator does NOT reuse M1 key and falls back safely."""
        settings.GROQ_API_KEY = "m1-private-key-12345"
        settings.GROQ_M1_API_KEY = "m1-private-key-12345"
        settings.GROQ_ORCHESTRATOR_API_KEY = ""  # Unset

        ctx = self._alex_context()
        analysis = self._analysis()

        with patch("app.orchestrator.graph.call_groq", new_callable=AsyncMock) as mock_call:
            action = self.orchestrator.decide(ctx, analysis)

            # Transport call_groq should never have been invoked because orchestrator key is missing
            self.assertFalse(mock_call.called)
            # Deterministic fallback should have taken over
            self.assertFalse(action.metadata.get("nemotron_used", False))
            self.assertIsNotNone(action)
            self.assertIn(action.action, [ActionType.ASK_QUESTION, ActionType.SWITCH_AGENT])

    # ── TEST 3: Orchestrator Groq key not reused by M1 ────────────────────────
    def test_03_orchestrator_groq_key_not_reused_by_m1(self) -> None:
        """When M1 keys are empty, M1 does NOT reuse GROQ_ORCHESTRATOR_API_KEY and raises error."""
        from app.interview_intelligence.provider import get_m1_provider, M1ProviderError

        settings.GROQ_API_KEY = ""
        settings.GROQ_M1_API_KEY = ""
        settings.GROQ_ORCHESTRATOR_API_KEY = "orchestrator-private-key-99999"

        with self.assertRaises(M1ProviderError) as cm:
            get_m1_provider("groq")

        self.assertIn("GROQ_API_KEY is missing or empty", str(cm.exception))

    # ── TEST 4: Default model is openai/gpt-oss-20b ───────────────────────────
    def test_04_gpt_oss_20b_selected_default(self) -> None:
        """Default model configuration for both M1 and Meta-Orchestrator is openai/gpt-oss-20b."""
        from app.orchestrator.graph import _get_nemotron_config
        model, base_url, timeout = _get_nemotron_config()
        self.assertEqual(model, "openai/gpt-oss-20b")
        self.assertEqual(settings.GROQ_ORCHESTRATOR_MODEL, "openai/gpt-oss-20b")
        self.assertEqual(settings.GROQ_MODEL, "openai/gpt-oss-20b")

    # ── TEST 5: NextAction behavior unchanged with Groq ───────────────────────
    def test_05_next_action_behavior_unchanged_with_groq(self) -> None:
        """SWITCH_AGENT, ASK_QUESTION, and COMPLETE work seamlessly when powered by Groq."""
        settings.GROQ_ORCHESTRATOR_API_KEY = "mock-orch-key"
        ctx = self._alex_context()
        analysis = self._analysis()

        # SWITCH_AGENT case
        groq_switch = {
            "action": "SWITCH_AGENT",
            "target_agent_id": "jordan",
            "competency": "prioritization",
            "rationale": "Candidate raised user trade-offs.",
            "cross_agent_opportunity": True,
            "trigger_signals": ["user metrics"],
            "unresolved_target_competencies": ["prioritization"],
            "question_text": "I'll let Jordan explore how you prioritized those user metrics.",
        }

        with patch("app.orchestrator.graph.call_groq", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = groq_switch
            action = self.orchestrator.decide(ctx, analysis)
            self.assertEqual(action.action, ActionType.SWITCH_AGENT)
            self.assertEqual(action.target_agent_id, "jordan")
            self.assertEqual(action.question_text, "I'll let Jordan explore how you prioritized those user metrics.")
            self.assertTrue(action.metadata.get("nemotron_used"))

    # ── TEST 6: Groq failure triggers safe deterministic fallback ─────────────
    def test_06_groq_failure_triggers_safe_fallback(self) -> None:
        """Network, rate-limit, or HTTP failures from Groq trigger safe deterministic fallback."""
        from app.integrations.groq_client import GroqAPIError

        settings.GROQ_ORCHESTRATOR_API_KEY = "mock-orch-key"
        ctx = self._alex_context()
        analysis = self._analysis()

        # Simulate Groq 429 rate limit
        with patch("app.orchestrator.graph.call_groq", side_effect=GroqAPIError("Groq API error [RESOURCE_EXHAUSTED] status 429")):
            action_429 = self.orchestrator.decide(ctx, analysis)
            self.assertIsNotNone(action_429)
            self.assertFalse(action_429.metadata.get("nemotron_used", False))

        # Simulate Groq timeout
        with patch("app.orchestrator.graph.call_groq", side_effect=GroqAPIError("NETWORK_TIMEOUT: Groq API request timed out")):
            action_timeout = self.orchestrator.decide(ctx, analysis)
            self.assertIsNotNone(action_timeout)
            self.assertFalse(action_timeout.metadata.get("nemotron_used", False))


if __name__ == "__main__":
    unittest.main()
