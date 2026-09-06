"""Unit tests for Intra AI InterviewAIContext state container."""

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.agents import agent_registry
from app.core.exceptions import AgentNotFoundError
from app.interview_context import (
    ContradictionItem,
    EvidenceItem,
    InterviewAIContext,
)
from app.models.enums import DifficultyLevel


class TestInterviewAIContext(unittest.TestCase):
    """Test suite verifying InterviewAIContext validation, mutation API, and serialization."""

    def setUp(self) -> None:
        agent_registry.reset()

    # ── TEST 1 — Context creation ──────────────────────────────────────────
    def test_01_context_creation(self) -> None:
        """Create a valid InterviewAIContext and verify it validates."""
        ctx = InterviewAIContext(
            interview_id="interview-1",
            candidate_id="candidate-1",
            current_round_id="technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
        )

        self.assertEqual(ctx.interview_id, "interview-1")
        self.assertEqual(ctx.candidate_id, "candidate-1")
        self.assertEqual(ctx.current_round_id, "technical")
        self.assertEqual(ctx.current_agent_id, "alex")
        self.assertEqual(ctx.difficulty, DifficultyLevel.MEDIUM)
        self.assertEqual(ctx.evaluated_competencies, [])
        self.assertEqual(ctx.accumulated_evidence, [])
        self.assertEqual(ctx.open_questions, [])
        self.assertEqual(ctx.missing_competencies, [])
        self.assertEqual(ctx.detected_contradictions, [])

    # ── TEST 2 — Required field validation ──────────────────────────────────
    def test_02_required_field_validation(self) -> None:
        """Verify empty strings for identity fields are rejected."""
        # Empty interview_id
        with self.assertRaises(ValidationError):
            InterviewAIContext(
                interview_id="",
                candidate_id="c-1",
                current_round_id="round-1",
                current_agent_id="alex",
            )

        # Whitespace-only candidate_id
        with self.assertRaises(ValidationError):
            InterviewAIContext(
                interview_id="int-1",
                candidate_id="   ",
                current_round_id="round-1",
                current_agent_id="alex",
            )

        # Empty current_round_id
        with self.assertRaises(ValidationError):
            InterviewAIContext(
                interview_id="int-1",
                candidate_id="c-1",
                current_round_id="",
                current_agent_id="alex",
            )

        # Empty current_agent_id
        with self.assertRaises(ValidationError):
            InterviewAIContext(
                interview_id="int-1",
                candidate_id="c-1",
                current_round_id="round-1",
                current_agent_id="  ",
            )

    # ── TEST 3 — Agent normalization ────────────────────────────────────────
    def test_03_agent_normalization(self) -> None:
        """Verify 'Alex', 'ALEX', ' alex ' normalize consistently to 'alex'."""
        for raw in ["Alex", "ALEX", " alex ", "  ALEX\t "]:
            ctx = InterviewAIContext(
                interview_id="int-1",
                candidate_id="c-1",
                current_round_id="tech",
                current_agent_id=raw,
            )
            self.assertEqual(
                ctx.current_agent_id,
                "alex",
                f"Raw '{raw}' did not normalize to 'alex'",
            )

    # ── TEST 4 — Competency updates ─────────────────────────────────────────
    def test_04_competency_updates(self) -> None:
        """Add system_design and verify stored; add again and verify not duplicated."""
        ctx = InterviewAIContext(
            interview_id="int-1",
            candidate_id="c-1",
            current_round_id="tech",
            current_agent_id="alex",
        )

        added_first = ctx.add_evaluated_competency("system_design")
        self.assertTrue(added_first)
        self.assertIn("system_design", ctx.evaluated_competencies)
        self.assertEqual(len(ctx.evaluated_competencies), 1)

        # Adding same competency again (even with casing/whitespace) does not duplicate
        added_second = ctx.add_evaluated_competency("  System_Design  ")
        self.assertFalse(added_second)
        self.assertEqual(len(ctx.evaluated_competencies), 1)
        self.assertEqual(ctx.evaluated_competencies, ["system_design"])

    # ── TEST 5 — Difficulty update ──────────────────────────────────────────
    def test_05_difficulty_update(self) -> None:
        """Start with medium, change to hard, verify reflection."""
        ctx = InterviewAIContext(
            interview_id="int-1",
            candidate_id="c-1",
            current_round_id="tech",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
        )
        self.assertEqual(ctx.difficulty, DifficultyLevel.MEDIUM)

        # Update using enum
        ctx.set_difficulty(DifficultyLevel.HARD)
        self.assertEqual(ctx.difficulty, DifficultyLevel.HARD)

        # Update using string
        ctx.set_difficulty("expert")
        self.assertEqual(ctx.difficulty, DifficultyLevel.EXPERT)

    # ── TEST 6 — Evidence update ────────────────────────────────────────────
    def test_06_evidence_update(self) -> None:
        """Add a typed evidence item and verify it is retained."""
        ctx = InterviewAIContext(
            interview_id="int-1",
            candidate_id="c-1",
            current_round_id="tech",
            current_agent_id="alex",
        )

        ev = EvidenceItem(
            id="ev-101",
            competency="scalability",
            signal="Candidate explained horizontal partitioning and Redis replication for payment tokens.",
            score=8.5,
            source_agent_id="alex",
            round_id="tech",
        )
        ctx.add_evidence(ev)

        self.assertEqual(len(ctx.accumulated_evidence), 1)
        stored_ev = ctx.accumulated_evidence[0]
        self.assertEqual(stored_ev.id, "ev-101")
        self.assertEqual(stored_ev.competency, "scalability")
        self.assertEqual(stored_ev.score, 8.5)
        self.assertEqual(stored_ev.source_agent_id, "alex")

        # Updating item with same ID updates in place without duplicating
        ev_updated = EvidenceItem(
            id="ev-101",
            competency="scalability",
            signal="Updated signal with concrete benchmark metrics.",
            score=9.0,
            source_agent_id="alex",
            round_id="tech",
        )
        ctx.add_evidence(ev_updated)
        self.assertEqual(len(ctx.accumulated_evidence), 1)
        self.assertEqual(ctx.accumulated_evidence[0].score, 9.0)

    # ── TEST 7 — Open question lifecycle ────────────────────────────────────
    def test_07_open_question_lifecycle(self) -> None:
        """Add an open question, verify it exists, resolve/remove it."""
        ctx = InterviewAIContext(
            interview_id="int-1",
            candidate_id="c-1",
            current_round_id="tech",
            current_agent_id="alex",
        )

        q_text = "Need concrete trade-off example for database indexing choices"
        ctx.add_open_question(q_text)
        self.assertIn(q_text, ctx.open_questions)
        self.assertEqual(len(ctx.open_questions), 1)

        # Deduplication check
        added_again = ctx.add_open_question(q_text)
        self.assertFalse(added_again)
        self.assertEqual(len(ctx.open_questions), 1)

        # Resolve question
        resolved = ctx.resolve_open_question(q_text)
        self.assertTrue(resolved)
        self.assertNotIn(q_text, ctx.open_questions)
        self.assertEqual(len(ctx.open_questions), 0)

        # Resolving non-existent returns False
        self.assertFalse(ctx.resolve_open_question("non-existent"))

    # ── TEST 8 — Missing competency lifecycle ───────────────────────────────
    def test_08_missing_competency_lifecycle(self) -> None:
        """Add scalability, verify represented as missing, resolve it."""
        ctx = InterviewAIContext(
            interview_id="int-1",
            candidate_id="c-1",
            current_round_id="tech",
            current_agent_id="alex",
        )

        ctx.add_missing_competency("scalability")
        self.assertIn("scalability", ctx.missing_competencies)
        self.assertEqual(len(ctx.missing_competencies), 1)

        # Deduplication check
        ctx.add_missing_competency("  Scalability ")
        self.assertEqual(len(ctx.missing_competencies), 1)

        # Resolve competency
        resolved = ctx.resolve_missing_competency("scalability")
        self.assertTrue(resolved)
        self.assertNotIn("scalability", ctx.missing_competencies)
        self.assertEqual(len(ctx.missing_competencies), 0)

    # ── TEST 9 — Contradiction accumulation ─────────────────────────────────
    def test_09_contradiction_accumulation(self) -> None:
        """Add a contradiction, verify retained and not overwritten by other updates."""
        ctx = InterviewAIContext(
            interview_id="int-1",
            candidate_id="c-1",
            current_round_id="tech",
            current_agent_id="alex",
        )

        contra = ContradictionItem(
            id="contra-1",
            claim="Claimed 5 years of production Kubernetes architecture experience.",
            contradiction="Could not explain basic pod lifecycle, ingress controllers, or deployment strategies.",
            severity="high",
            detected_by_agent_id="alex",
            round_id="tech",
        )
        ctx.add_contradiction(contra)

        self.assertEqual(len(ctx.detected_contradictions), 1)
        self.assertEqual(ctx.detected_contradictions[0].id, "contra-1")
        self.assertEqual(ctx.detected_contradictions[0].severity, "high")

        # Perform unrelated updates
        ctx.add_evaluated_competency("networking")
        ctx.set_difficulty(DifficultyLevel.HARD)
        ctx.add_open_question("Need details on container networking")

        # Contradiction is preserved
        self.assertEqual(len(ctx.detected_contradictions), 1)
        self.assertEqual(ctx.detected_contradictions[0].id, "contra-1")

    # ── TEST 10 — Agent switching ───────────────────────────────────────────
    def test_10_agent_switching(self) -> None:
        """Start with current_agent_id = 'alex', switch to 'jordan', verify identity intact."""
        ctx = InterviewAIContext(
            interview_id="int-99",
            candidate_id="cand-42",
            current_round_id="tech_to_product",
            current_agent_id="alex",
        )

        self.assertEqual(ctx.current_agent_id, "alex")

        # Switch to jordan
        ctx.switch_agent("jordan")

        self.assertEqual(ctx.current_agent_id, "jordan")
        # Identity fields must remain untouched
        self.assertEqual(ctx.interview_id, "int-99")
        self.assertEqual(ctx.candidate_id, "cand-42")
        self.assertEqual(ctx.current_round_id, "tech_to_product")

    # ── TEST 11 — Serialization round trip ──────────────────────────────────
    def test_11_serialization_round_trip(self) -> None:
        """Serialize context to dict and JSON, deserialize, verify all state survives."""
        ctx = InterviewAIContext(
            interview_id="int-123",
            candidate_id="cand-456",
            current_round_id="round-technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.HARD,
            evaluated_competencies=["system_design", "databases"],
            open_questions=["Check replication lag handling"],
            missing_competencies=["observability"],
            metadata={"session_version": 2},
        )
        ctx.add_evidence(
            EvidenceItem(
                id="ev-1",
                competency="system_design",
                signal="Explained CQRS and event sourcing architecture.",
                score=9.0,
                source_agent_id="alex",
            )
        )
        ctx.add_contradiction(
            ContradictionItem(
                id="c-1",
                claim="Lead architect on Redis migration",
                contradiction="Admitted teammate drove design",
                severity="low",
            )
        )

        # Dict round trip
        dict_data = ctx.to_dict()
        ctx_from_dict = InterviewAIContext.from_dict(dict_data)
        self.assertEqual(ctx_from_dict.interview_id, ctx.interview_id)
        self.assertEqual(ctx_from_dict.candidate_id, ctx.candidate_id)
        self.assertEqual(ctx_from_dict.current_agent_id, ctx.current_agent_id)
        self.assertEqual(ctx_from_dict.difficulty, DifficultyLevel.HARD)
        self.assertEqual(ctx_from_dict.evaluated_competencies, ["system_design", "databases"])
        self.assertEqual(len(ctx_from_dict.accumulated_evidence), 1)
        self.assertEqual(ctx_from_dict.accumulated_evidence[0].score, 9.0)
        self.assertEqual(len(ctx_from_dict.detected_contradictions), 1)
        self.assertEqual(ctx_from_dict.metadata["session_version"], 2)

        # JSON round trip
        json_data = ctx.to_json()
        ctx_from_json = InterviewAIContext.from_json(json_data)
        self.assertEqual(ctx_from_json.interview_id, ctx.interview_id)
        self.assertEqual(ctx_from_json.evaluated_competencies, ctx.evaluated_competencies)

    # ── TEST 12 — Unknown agent behavior ────────────────────────────────────
    def test_12_unknown_agent_behavior(self) -> None:
        """Verify explicit registry validation fails for unknown agents, while normalized string IDs are accepted by default."""
        ctx = InterviewAIContext(
            interview_id="int-1",
            candidate_id="c-1",
            current_round_id="tech",
            current_agent_id="alex",
        )

        # Alex is registered in default registry
        self.assertTrue(ctx.validate_agent_with_registry())

        # Switching with validate_registry=True to an unknown agent raises AgentNotFoundError
        with self.assertRaises(AgentNotFoundError):
            ctx.switch_agent("unknown_agent_xyz", validate_registry=True)

        # Switching with default validate_registry=False allows custom/future agent IDs (normalized)
        ctx.switch_agent("  Morgan_Behavioral  ", validate_registry=False)
        self.assertEqual(ctx.current_agent_id, "morgan_behavioral")

        # But explicitly validating against registry now fails because Morgan is not yet in registry
        with self.assertRaises(AgentNotFoundError):
            ctx.validate_agent_with_registry()


if __name__ == "__main__":
    unittest.main()
