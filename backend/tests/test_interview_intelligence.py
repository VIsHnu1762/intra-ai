"""Unit tests for Intra AI M1 Interview Intelligence."""

import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.agents import ALEX_PROFILE, ActionType, AgentProfile
from app.interview_context import ContradictionItem, EvidenceItem, InterviewAIContext
from app.interview_intelligence import (
    AnswerAnalysis,
    CompetencyFinding,
    DeterministicMockM1Provider,
    InterviewAnswerInput,
    M1InterviewAnalyzer,
    M1ProviderError,
    OpenAIAnalysisProvider,
    apply_analysis_to_context,
    build_m1_system_prompt,
    build_m1_user_prompt,
    m1_analyzer,
)
from app.models.enums import DifficultyLevel


class TestInterviewIntelligence(unittest.TestCase):
    """Test suite verifying M1 AnswerAnalysis, semantic evaluation, and contract boundaries."""

    def setUp(self) -> None:
        self.context = InterviewAIContext(
            interview_id="int-101",
            candidate_id="cand-202",
            current_round_id="technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )
        self.analyzer = M1InterviewAnalyzer(provider=DeterministicMockM1Provider())

    # ── TEST 1 — AnswerAnalysis creation ───────────────────────────────────
    def test_01_answer_analysis_creation(self) -> None:
        """Create a valid AnswerAnalysis instance and verify all fields."""
        ev = EvidenceItem(
            id="ev-1",
            competency="system_design",
            signal="Explained distributed caching architecture.",
            score=8.5,
        )
        finding = CompetencyFinding(
            competency_id="system_design",
            assessment="Candidate demonstrated strong knowledge of Redis caching.",
            confidence=0.9,
            evidence_ids=["ev-1"],
        )
        analysis = AnswerAnalysis(
            answer_id="ans-001",
            overall_performance=0.85,
            confidence=0.92,
            vague=False,
            vague_reason=None,
            contradiction_detected=False,
            missing_information=[],
            evidence=[ev],
            competency_findings=[finding],
            recommended_follow_up="How would you handle Redis node failover?",
        )

        self.assertEqual(analysis.answer_id, "ans-001")
        self.assertEqual(analysis.overall_performance, 0.85)
        self.assertEqual(analysis.confidence, 0.92)
        self.assertFalse(analysis.vague)
        self.assertEqual(len(analysis.evidence), 1)
        self.assertEqual(len(analysis.competency_findings), 1)
        self.assertEqual(analysis.competency_findings[0].evidence_ids, ["ev-1"])

    # ── TEST 2 — Score validation ──────────────────────────────────────────
    def test_02_score_validation(self) -> None:
        """Verify overall_performance must be normalized between 0.0 and 1.0."""
        # Score > 1.0 fails
        with self.assertRaises(ValidationError):
            AnswerAnalysis(
                answer_id="ans-1",
                overall_performance=1.2,
                confidence=0.9,
                vague=False,
                contradiction_detected=False,
            )

        # Score < 0.0 fails
        with self.assertRaises(ValidationError):
            AnswerAnalysis(
                answer_id="ans-1",
                overall_performance=-0.1,
                confidence=0.9,
                vague=False,
                contradiction_detected=False,
            )

    # ── TEST 3 — Confidence validation ─────────────────────────────────────
    def test_03_confidence_validation(self) -> None:
        """Verify confidence must be normalized between 0.0 and 1.0."""
        # Confidence > 1.0 fails
        with self.assertRaises(ValidationError):
            AnswerAnalysis(
                answer_id="ans-1",
                overall_performance=0.8,
                confidence=1.05,
                vague=False,
                contradiction_detected=False,
            )

        # CompetencyFinding confidence validation
        with self.assertRaises(ValidationError):
            CompetencyFinding(
                competency_id="system_design",
                assessment="Solid",
                confidence=1.5,
            )

    # ── TEST 4 — Evidence validation ───────────────────────────────────────
    def test_04_evidence_validation(self) -> None:
        """Verify evidence items are retained and structured using canonical EvidenceItem."""
        ev1 = EvidenceItem(id="ev-1", competency="system_design", signal="CQRS pattern.")
        ev2 = EvidenceItem(id="ev-2", competency="scalability", signal="Horizontal sharding.")

        analysis = AnswerAnalysis(
            answer_id="ans-1",
            overall_performance=0.88,
            confidence=0.95,
            vague=False,
            contradiction_detected=False,
            evidence=[ev1, ev2],
        )
        self.assertEqual(len(analysis.evidence), 2)
        self.assertEqual(analysis.evidence[0].id, "ev-1")
        self.assertEqual(analysis.evidence[1].id, "ev-2")

    # ── TEST 5 — Competency finding validation (evidence_ids) ───────────────
    def test_05_competency_finding_evidence_ids_integrity(self) -> None:
        """Verify evidence_ids in CompetencyFinding must exist in AnswerAnalysis.evidence."""
        ev = EvidenceItem(id="ev-valid-1", competency="system_design", signal="Valid signal.")

        # Referencing unknown evidence_id fails
        with self.assertRaises(ValidationError) as ctx:
            AnswerAnalysis(
                answer_id="ans-1",
                overall_performance=0.7,
                confidence=0.8,
                vague=False,
                contradiction_detected=False,
                evidence=[ev],
                competency_findings=[
                    CompetencyFinding(
                        competency_id="system_design",
                        assessment="Demonstrated caching.",
                        confidence=0.8,
                        evidence_ids=["ev-nonexistent-999"],
                    )
                ],
            )
        self.assertIn("references unknown evidence_id", str(ctx.exception))

    # ── TEST 6 — Vague answer analysis ─────────────────────────────────────
    def test_06_vague_answer_analysis(self) -> None:
        """Analyze a vague answer and verify vague=True and vague_reason populated."""
        input_data = InterviewAnswerInput(
            answer_id="ans-vague",
            question_text="How did you scale your database for high-volume transactions?",
            answer_text="We basically just used some tools and things worked pretty good etc.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)
        self.assertTrue(analysis.vague)
        self.assertIsNotNone(analysis.vague_reason)
        self.assertLess(analysis.overall_performance, 0.50)
        self.assertGreater(len(analysis.missing_information), 0)

    # ── TEST 7 — Clear answer analysis ─────────────────────────────────────
    def test_07_clear_answer_analysis(self) -> None:
        """Analyze a clear, technical answer and verify vague=False."""
        input_data = InterviewAnswerInput(
            answer_id="ans-clear",
            question_text="How did you handle read scalability in your microservices?",
            answer_text="We deployed Redis read replicas with write-through invalidation and partitioned by customer ID.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)
        self.assertFalse(analysis.vague)
        self.assertIsNone(analysis.vague_reason)
        self.assertGreater(analysis.overall_performance, 0.70)
        self.assertGreater(len(analysis.evidence), 0)

    # ── TEST 8 — Contradiction detection ───────────────────────────────────
    def test_08_contradiction_detection(self) -> None:
        """Verify contradiction detected when candidate answer conflicts with documented claims."""
        # Seed context with a prior contradiction/claim
        self.context.add_contradiction(
            ContradictionItem(
                claim="Lead architect of distributed PostgreSQL clustering",
                contradiction="Admitted never worked on distributed databases",
            )
        )

        input_data = InterviewAnswerInput(
            answer_id="ans-contra",
            question_text="Tell me about your distributed PostgreSQL clustering work.",
            answer_text="I have never used or configured distributed databases in production.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)
        self.assertTrue(analysis.contradiction_detected)
        self.assertIsNotNone(analysis.contradiction_details)

    # ── TEST 9 — Missing information ───────────────────────────────────────
    def test_09_missing_information_reporting(self) -> None:
        """Verify missing_information is populated when technical depth is omitted."""
        input_data = InterviewAnswerInput(
            answer_id="ans-partial",
            question_text="Describe your Kafka streaming setup.",
            answer_text="I sort of helped the team set up Kafka topics.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)
        self.assertIsInstance(analysis.missing_information, list)
        self.assertGreater(len(analysis.missing_information), 0)

    # ── TEST 10 — Recommended follow-up ────────────────────────────────────
    def test_10_recommended_follow_up_generation(self) -> None:
        """Verify recommended_follow_up produces an informational probe."""
        input_data = InterviewAnswerInput(
            answer_id="ans-followup",
            question_text="Explain your caching strategy.",
            answer_text="We used Redis to cache frequently accessed user profiles and session tokens.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)
        self.assertIsNotNone(analysis.recommended_follow_up)
        self.assertIn("?", analysis.recommended_follow_up)

    # ── TEST 11 — Dynamic agent competencies ────────────────────────────────
    def test_11_dynamic_agent_competencies(self) -> None:
        """Verify competencies are analyzed dynamically from agent_profile.focal_competencies."""
        custom_agent = AgentProfile(
            agent_id="security_lead",
            display_name="Samantha",
            role="Security Lead",
            description="Evaluates application security and cryptography.",
            focal_competencies=["oauth2", "encryption_at_rest", "threat_modeling"],
            questioning_style="probing security auditor",
            instructions="You are Samantha, Security Lead...",
        )

        input_data = InterviewAnswerInput(
            answer_id="ans-sec",
            question_text="How do you secure API access tokens?",
            answer_text="We implemented OAuth2 JWTs with short expiry and encryption at rest using AES-256.",
            context=self.context,
            agent_profile=custom_agent,
        )

        analysis = self.analyzer.analyze(input_data)
        self.assertEqual(len(analysis.competency_findings), 1)
        # Should map to one of the custom agent's focal competencies
        self.assertIn(
            analysis.competency_findings[0].competency_id,
            custom_agent.focal_competencies,
        )

    # ── TEST 12 — Alex competency analysis ─────────────────────────────────
    def test_12_alex_competency_analysis(self) -> None:
        """Verify analysis under Alex persona evaluates Alex's focal competencies."""
        input_data = InterviewAnswerInput(
            answer_id="ans-alex",
            question_text="How did you architect your payment processing pipeline?",
            answer_text="We built a distributed system design using event-driven microservices for high scalability.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)
        self.assertGreater(len(analysis.competency_findings), 0)
        self.assertIn(
            analysis.competency_findings[0].competency_id,
            ALEX_PROFILE.focal_competencies,
        )

    # ── TEST 13 — Non-Alex competency analysis (Jordan) ────────────────────
    def test_13_non_alex_competency_analysis(self) -> None:
        """Verify analyzer functions cleanly for non-Alex agent (Jordan - Product Lead)."""
        jordan_profile = AgentProfile(
            agent_id="jordan",
            display_name="Jordan",
            role="Product Lead",
            description="Evaluates product sense and customer impact.",
            focal_competencies=["product_sense", "customer_impact", "metrics"],
            questioning_style="empathetic product inquiry",
            instructions="You are Jordan, Product Lead...",
        )

        input_data = InterviewAnswerInput(
            answer_id="ans-jordan",
            question_text="How did you measure the success of the checkout redesign?",
            answer_text="We tracked customer impact and conversion metrics, increasing completion by 14%.",
            context=self.context,
            agent_profile=jordan_profile,
        )

        analysis = self.analyzer.analyze(input_data)
        self.assertFalse(analysis.vague)
        self.assertIn(
            analysis.competency_findings[0].competency_id,
            jordan_profile.focal_competencies,
        )

    # ── TEST 14 — Malformed provider response handling ──────────────────────
    def test_14_malformed_provider_response_handling(self) -> None:
        """Verify malformed provider output raises an explicit error and does not fabricate data."""
        mock_provider = MagicMock()
        mock_provider.analyze_answer.side_effect = M1ProviderError("Invalid JSON from LLM")

        analyzer = M1InterviewAnalyzer(provider=mock_provider)
        input_data = InterviewAnswerInput(
            answer_id="ans-fail",
            question_text="Test question",
            answer_text="Test answer",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        with self.assertRaises(M1ProviderError):
            analyzer.analyze(input_data)

    # ── TEST 15 — Provider isolation ────────────────────────────────────────
    def test_15_provider_isolation(self) -> None:
        """Verify custom provider can be injected via M1AnalysisProvider interface."""
        class CustomTestProvider:
            def analyze_answer(self, input_data: InterviewAnswerInput) -> AnswerAnalysis:
                return AnswerAnalysis(
                    answer_id=input_data.answer_id,
                    overall_performance=0.99,
                    confidence=1.0,
                    vague=False,
                    contradiction_detected=False,
                    missing_information=[],
                    evidence=[],
                    competency_findings=[],
                    recommended_follow_up="Custom follow-up",
                )

            async def analyze_answer_async(self, input_data: InterviewAnswerInput) -> AnswerAnalysis:
                return self.analyze_answer(input_data)

        custom_analyzer = M1InterviewAnalyzer(provider=CustomTestProvider())
        input_data = InterviewAnswerInput(
            answer_id="ans-iso",
            question_text="Question",
            answer_text="Answer",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )
        res = custom_analyzer.analyze(input_data)
        self.assertEqual(res.overall_performance, 0.99)
        self.assertEqual(res.recommended_follow_up, "Custom follow-up")

    # ── TEST 16 — Analyzer does not mutate InterviewAIContext ───────────────
    def test_16_analyzer_does_not_mutate_context(self) -> None:
        """Verify analyzer.analyze() strictly preserves input context without mutation."""
        initial_evidence_count = len(self.context.accumulated_evidence)
        initial_missing_count = len(self.context.missing_competencies)
        initial_agent = self.context.current_agent_id
        initial_difficulty = self.context.difficulty

        input_data = InterviewAnswerInput(
            answer_id="ans-immutable",
            question_text="How did you scale PostgreSQL?",
            answer_text="We used connection pooling with PgBouncer and horizontal read replicas.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)

        # Output has evidence
        self.assertGreater(len(analysis.evidence), 0)

        # But context itself was NOT mutated by analyze()
        self.assertEqual(len(self.context.accumulated_evidence), initial_evidence_count)
        self.assertEqual(len(self.context.missing_competencies), initial_missing_count)
        self.assertEqual(self.context.current_agent_id, initial_agent)
        self.assertEqual(self.context.difficulty, initial_difficulty)

    # ── TEST 17 — No NextAction generated by M1 ─────────────────────────────
    def test_17_no_next_action_generated_by_m1(self) -> None:
        """Verify AnswerAnalysis contains zero NextAction or routing decision logic."""
        input_data = InterviewAnswerInput(
            answer_id="ans-norouting",
            question_text="Explain debugging reasoning.",
            answer_text="I analyzed thread dumps and pinpointed the locked mutex.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)

        # Verify no NextAction or ActionType attributes exist on AnswerAnalysis
        self.assertFalse(hasattr(analysis, "action"))
        self.assertFalse(hasattr(analysis, "next_action"))
        self.assertFalse(hasattr(analysis, "target_agent_id"))

    # ── TEST 18 — No external provider required ─────────────────────────────
    def test_18_no_external_provider_required(self) -> None:
        """Verify the test suite runs with zero OpenAI or external API credentials set."""
        with patch.dict("os.environ", {}, clear=True):
            input_data = InterviewAnswerInput(
                answer_id="ans-offline",
                question_text="How do you handle API errors?",
                answer_text="We return standard RFC 7807 problem details with structured machine codes.",
                context=self.context,
                agent_profile=ALEX_PROFILE,
            )
            analysis = self.analyzer.analyze(input_data)
            self.assertEqual(analysis.answer_id, "ans-offline")
            self.assertGreater(analysis.overall_performance, 0.0)

    # ── TEST 19 — Integration with existing contracts ───────────────────────
    def test_19_integration_with_existing_contracts(self) -> None:
        """Verify AnswerAnalysis seamlessly applies to InterviewAIContext using explicit helper."""
        input_data = InterviewAnswerInput(
            answer_id="ans-integration",
            question_text="How did you design the notification system?",
            answer_text="We used system design principles with RabbitMQ and Redis to achieve high scalability.",
            context=self.context,
            agent_profile=ALEX_PROFILE,
        )

        analysis = self.analyzer.analyze(input_data)

        # Apply using explicit helper
        apply_analysis_to_context(analysis, self.context)

        # Verify context updated properly
        self.assertIn("system_design", self.context.evaluated_competencies)
        self.assertNotIn("system_design", self.context.missing_competencies)
        self.assertGreater(len(self.context.accumulated_evidence), 0)


if __name__ == "__main__":
    unittest.main()
