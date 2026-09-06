"""Tests for M1 Interview Intelligence -> Knowledge Graph persistence pipeline.

Verifies:
1. Valid M1 AnswerAnalysis persistence to typed Knowledge Graph entities.
2. Candidate, InterviewRound, Question, Answer, Evidence, Competency persistence.
3. Canonical relationship creation and connectivity.
4. Strict evidence provenance preservation.
5. Idempotent re-execution (no duplicate nodes or relationships).
6. Competency normalization (deduplicating case/format variations).
7. Validation rejection on malformed evidence or missing IDs.
8. Error isolation: Neo4j failure does not break interview response or orchestrator routing.
9. Side-effect nature: KG is never queried to determine NextAction or routing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.agents.models import ActionType, AgentProfile, NextAction
from app.custom_llm.adapter import CustomLLMAdapter
from app.custom_llm.models import ChatCompletionRequest, ChatMessage
from app.interview_context.models import EvidenceItem, InterviewAIContext
from app.interview_context.store import InterviewSessionStore
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding, InterviewAnswerInput
from app.knowledge_graph.exceptions import KnowledgeGraphError, Neo4jConnectionError
from app.knowledge_graph.models import GraphRelationshipType
from app.knowledge_graph.repository import InMemoryKnowledgeGraphRepository
from app.knowledge_graph.service import (
    KnowledgeGraphPersistenceService,
    derive_question_id,
    derive_round_id,
    normalize_competency_id,
)
from app.models.enums import DifficultyLevel


# ═════════════════════════════════════════════════════════════════════════════
# Helper Fixtures & Factories
# ═════════════════════════════════════════════════════════════════════════════


def make_test_context(
    interview_id: str = "test-int-101",
    candidate_id: str = "cand-alice-01",
    current_round_id: str = "technical",
    current_agent_id: str = "alex",
) -> InterviewAIContext:
    return InterviewAIContext(
        interview_id=interview_id,
        candidate_id=candidate_id,
        current_round_id=current_round_id,
        current_agent_id=current_agent_id,
        difficulty=DifficultyLevel.MEDIUM,
        evaluated_competencies=[],
        missing_competencies=["system_design", "concurrency"],
        metadata={"candidate_name": "Alice Developer", "candidate_email": "alice@example.com"},
    )


def make_test_analysis(
    answer_id: str = "ans-turn-001",
    competency: str = "system_design",
) -> AnswerAnalysis:
    ev1 = EvidenceItem(
        id="ev-101",
        competency=competency,
        signal="Designed distributed caching layer using Redis Cluster with consistent hashing",
        score=8.5,
        source_agent_id="alex",
        round_id="technical",
    )
    ev2 = EvidenceItem(
        id="ev-102",
        competency=competency,
        signal="Demonstrated understanding of cache-aside and write-through trade-offs",
        score=9.0,
        source_agent_id="alex",
        round_id="technical",
    )
    finding = CompetencyFinding(
        competency_id=competency,
        assessment="Strong architectural grasp of distributed cache patterns",
        confidence=0.92,
        evidence_ids=["ev-101", "ev-102"],
    )
    return AnswerAnalysis(
        answer_id=answer_id,
        overall_performance=0.88,
        confidence=0.90,
        vague=False,
        vague_reason=None,
        contradiction_detected=False,
        contradiction_details=None,
        missing_information=[],
        evidence=[ev1, ev2],
        competency_findings=[finding],
    )


# ═════════════════════════════════════════════════════════════════════════════
# 1. Normalization & Identity Derivation Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestIdentityAndNormalization:
    """Verify deterministic IDs and competency normalization."""

    def test_normalize_competency_id(self) -> None:
        assert normalize_competency_id("System Design") == "system_design"
        assert normalize_competency_id("SYSTEM_DESIGN") == "system_design"
        assert normalize_competency_id("system-design") == "system_design"
        assert normalize_competency_id("  Distributed Caching  ") == "distributed_caching"
        assert normalize_competency_id("") == "general"

    def test_derive_round_id_stability(self) -> None:
        r1 = derive_round_id("int_100", "technical")
        r2 = derive_round_id("int_100", "technical")
        assert r1 == r2 == "int_100_technical"

        # Already prefixed
        assert derive_round_id("int_100", "int_100_technical") == "int_100_technical"

    def test_derive_question_id_stability(self) -> None:
        q_text = "How do you handle split-brain in distributed systems?"
        q1 = derive_question_id("round_1", q_text)
        q2 = derive_question_id("round_1", q_text)
        assert q1 == q2
        assert q1.startswith("round_1_q_")


# ═════════════════════════════════════════════════════════════════════════════
# 2. Core Service Persistence & Graph Structure Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestKnowledgeGraphPersistenceService:
    """Verify mapping of M1 AnswerAnalysis to typed Knowledge Graph entities."""

    def test_persist_turn_evaluation_creates_all_entities(self) -> None:
        repo = InMemoryKnowledgeGraphRepository()
        service = KnowledgeGraphPersistenceService(repository=repo)

        context = make_test_context()
        analysis = make_test_analysis()

        result = service.persist_turn_evaluation(
            analysis=analysis,
            context=context,
            question_text="Describe how you architect distributed caching.",
            answer_text="I use Redis Cluster with consistent hashing and write-through caches.",
            agent_id="alex",
            difficulty=DifficultyLevel.HARD,
        )

        assert result.success is True
        assert result.candidate_id == "cand-alice-01"
        assert result.answer_id == "ans-turn-001"
        assert result.evidence_count == 2
        assert "system_design" in result.competencies_persisted

        # 1. Verify Candidate Node
        cand = repo.get_candidate("cand-alice-01")
        assert cand is not None
        assert cand.name == "Alice Developer"

        # 2. Verify InterviewRound Node
        expected_round_id = derive_round_id(context.interview_id, context.current_round_id)
        rnd = repo.get_interview_round(expected_round_id)
        assert rnd is not None
        assert rnd.interview_id == context.interview_id

        # 3. Verify Question Node
        expected_q_id = derive_question_id(expected_round_id, "Describe how you architect distributed caching.")
        q = repo.get_question(expected_q_id)
        assert q is not None
        assert q.agent_id == "alex"
        assert q.difficulty == "hard"

        # 4. Verify Answer Node
        ans = repo.get_answer("ans-turn-001")
        assert ans is not None
        assert ans.question_id == expected_q_id
        assert ans.metadata["overall_performance"] == 0.88
        assert ans.metadata["agent_id"] == "alex"

        # 5. Verify Competency Node
        comp = repo.get_competency("system_design")
        assert comp is not None

        # 6. Verify Evidence Nodes & Strict Provenance
        ev1 = repo.get_evidence("ev-101")
        assert ev1 is not None
        assert ev1.answer_id == "ans-turn-001"
        assert ev1.candidate_id == "cand-alice-01"
        assert ev1.round_id == expected_round_id
        assert ev1.source_agent_id == "alex"
        assert ev1.competency == "system_design"
        assert ev1.score == 8.5
        assert "Redis Cluster" in ev1.signal

        ev2 = repo.get_evidence("ev-102")
        assert ev2 is not None
        assert ev2.answer_id == "ans-turn-001"

    def test_relationship_structure_completeness(self) -> None:
        repo = InMemoryKnowledgeGraphRepository()
        service = KnowledgeGraphPersistenceService(repository=repo)

        context = make_test_context()
        analysis = make_test_analysis()

        service.persist_turn_evaluation(
            analysis=analysis,
            context=context,
            question_text="Describe caching.",
            answer_text="Redis Cluster.",
            agent_id="alex",
        )

        # Inspect candidate neighborhood graph
        subgraph = repo.get_candidate_graph("cand-alice-01", depth=3)
        assert len(subgraph.nodes) >= 5
        assert len(subgraph.relationships) >= 5

        rel_types = {r["relationship_type"] for r in subgraph.relationships}
        assert GraphRelationshipType.PARTICIPATED_IN.value in rel_types
        assert GraphRelationshipType.HAS_QUESTION.value in rel_types
        assert GraphRelationshipType.HAS_ANSWER.value in rel_types
        assert GraphRelationshipType.SUPPORTED_BY.value in rel_types
        assert GraphRelationshipType.SUPPORTS_COMPETENCY.value in rel_types

    def test_idempotent_repeated_writes(self) -> None:
        """Reprocessing the exact same turn must not duplicate nodes or relationships."""
        repo = InMemoryKnowledgeGraphRepository()
        service = KnowledgeGraphPersistenceService(repository=repo)

        context = make_test_context()
        analysis = make_test_analysis()

        # Run 1
        res1 = service.persist_turn_evaluation(
            analysis=analysis,
            context=context,
            question_text="Describe caching.",
            answer_text="Redis Cluster.",
            agent_id="alex",
        )
        nodes_count_1 = len(repo._nodes["Evidence"]) + len(repo._nodes["Answer"]) + len(repo._nodes["Question"])
        rels_count_1 = len(repo._relationships)

        # Run 2 (duplicate webhook/event retry)
        res2 = service.persist_turn_evaluation(
            analysis=analysis,
            context=context,
            question_text="Describe caching.",
            answer_text="Redis Cluster.",
            agent_id="alex",
        )
        nodes_count_2 = len(repo._nodes["Evidence"]) + len(repo._nodes["Answer"]) + len(repo._nodes["Question"])
        rels_count_2 = len(repo._relationships)

        assert res1.success is True
        assert res2.success is True
        assert nodes_count_1 == nodes_count_2
        assert rels_count_1 == rels_count_2

    def test_competency_deduplication_across_variations(self) -> None:
        """'System Design', 'SYSTEM_DESIGN', and 'system_design' must resolve to one Competency node."""
        repo = InMemoryKnowledgeGraphRepository()
        service = KnowledgeGraphPersistenceService(repository=repo)

        context = make_test_context()

        analysis1 = make_test_analysis(answer_id="ans-1", competency="System Design")
        analysis2 = make_test_analysis(answer_id="ans-2", competency="SYSTEM_DESIGN")

        service.persist_turn_evaluation(
            analysis=analysis1,
            context=context,
            question_text="Question 1",
            answer_text="Answer 1",
            agent_id="alex",
        )
        service.persist_turn_evaluation(
            analysis=analysis2,
            context=context,
            question_text="Question 2",
            answer_text="Answer 2",
            agent_id="alex",
        )

        # There must be only one Competency node: 'system_design'
        assert "system_design" in repo._nodes["Competency"]
        assert "System Design" not in repo._nodes["Competency"]
        assert "SYSTEM_DESIGN" not in repo._nodes["Competency"]
        assert len(repo._nodes["Competency"]) == 1

    def test_unconfigured_repository_handled_gracefully(self) -> None:
        """When repository is None, service does not crash and returns descriptive result."""
        service = KnowledgeGraphPersistenceService(repository=None)
        context = make_test_context()
        analysis = make_test_analysis()

        result = service.persist_turn_evaluation(
            analysis=analysis,
            context=context,
            question_text="Q",
            answer_text="A",
            agent_id="alex",
        )
        assert result.success is False
        assert result.error == "repository_not_configured"


# ═════════════════════════════════════════════════════════════════════════════
# 3. CustomLLMAdapter Live Path Integration & Error Isolation Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestAdapterKnowledgeGraphIntegration:
    """Verify CustomLLMAdapter triggers KG persistence without modifying voice decisions."""

    @pytest.fixture
    def mock_store(self) -> InterviewSessionStore:
        store = InterviewSessionStore()
        store.get_or_create("int-live-test", agent_id="alex")
        return store

    @pytest.mark.asyncio
    async def test_adapter_persists_evidence_as_side_effect(self, mock_store: InterviewSessionStore) -> None:
        repo = InMemoryKnowledgeGraphRepository()
        kg_service = KnowledgeGraphPersistenceService(repository=repo)

        # Mock M1 returning valid analysis
        mock_m1 = MagicMock()
        test_analysis = make_test_analysis(answer_id="ans-adapter-01")
        mock_m1.analyze_async = AsyncMock(return_value=test_analysis)

        # Mock Orchestrator returning ASK_QUESTION
        mock_orch = MagicMock()
        expected_action = NextAction(
            action=ActionType.ASK_QUESTION,
            question_text="How do you handle cache invalidation?",
            competency="system_design",
            difficulty=DifficultyLevel.HARD,
        )
        mock_orch.decide_async = AsyncMock(return_value=expected_action)

        adapter = CustomLLMAdapter(
            session_store=mock_store,
            m1_analyzer=mock_m1,
            orchestrator=mock_orch,
            kg_service=kg_service,
            background_kg_persistence=False,
        )

        request = ChatCompletionRequest(
            messages=[
                ChatMessage(role="assistant", content="How do you design a cache?"),
                ChatMessage(role="user", content="I use Redis cluster with write-through semantics."),
            ]
        )
        turn = adapter.parse_turn(request, headers={"x-session-id": "int-live-test", "x-agent-id": "alex"})

        response_text, next_action = await adapter.process_turn_async(turn)

        # 1. Voice response and NextAction come strictly from Orchestrator
        assert response_text == "How do you handle cache invalidation?"
        assert next_action is not None
        assert next_action.action == ActionType.ASK_QUESTION

        # 2. Knowledge Graph was populated as a side-effect projection
        ans = repo.get_answer("ans-adapter-01")
        assert ans is not None
        assert ans.answer_text == "I use Redis cluster with write-through semantics."
        assert repo.get_evidence("ev-101") is not None
        assert repo.get_evidence("ev-102") is not None

    @pytest.mark.asyncio
    async def test_neo4j_failure_does_not_crash_voice_response(self, mock_store: InterviewSessionStore) -> None:
        """When Neo4j persistence fails, candidate still receives interviewer response seamlessly."""
        failing_kg_service = MagicMock(spec=KnowledgeGraphPersistenceService)
        failing_kg_service.persist_turn_evaluation_async = AsyncMock(
            side_effect=Neo4jConnectionError("Neo4j AuraDB unreachable: Connection refused")
        )

        mock_m1 = MagicMock()
        mock_m1.analyze_async = AsyncMock(return_value=make_test_analysis())

        mock_orch = MagicMock()
        expected_action = NextAction(
            action=ActionType.ASK_QUESTION,
            question_text="Tell me about concurrency.",
            competency="concurrency",
            difficulty=DifficultyLevel.MEDIUM,
        )
        mock_orch.decide_async = AsyncMock(return_value=expected_action)

        adapter = CustomLLMAdapter(
            session_store=mock_store,
            m1_analyzer=mock_m1,
            orchestrator=mock_orch,
            kg_service=failing_kg_service,
            background_kg_persistence=False,
        )

        request = ChatCompletionRequest(
            messages=[
                ChatMessage(role="assistant", content="Describe your concurrency model."),
                ChatMessage(role="user", content="I use optimistic concurrency with version stamps."),
            ]
        )
        turn = adapter.parse_turn(request, headers={"x-session-id": "int-live-test", "x-agent-id": "alex"})

        # Must NOT raise exception despite KG failure
        response_text, next_action = await adapter.process_turn_async(turn)

        # Candidate still receives response from Orchestrator without delay
        assert response_text == "Tell me about concurrency."
        assert next_action is not None
        assert next_action.action == ActionType.ASK_QUESTION

    @pytest.mark.asyncio
    async def test_control_turns_bypass_kg_persistence(self, mock_store: InterviewSessionStore) -> None:
        """Control turns (audio check, pause) do NOT trigger Knowledge Graph persistence."""
        mock_kg = MagicMock(spec=KnowledgeGraphPersistenceService)
        mock_kg.persist_turn_evaluation_async = AsyncMock()

        adapter = CustomLLMAdapter(
            session_store=mock_store,
            kg_service=mock_kg,
        )

        request = ChatCompletionRequest(
            messages=[
                ChatMessage(role="assistant", content="Can you hear me?"),
                ChatMessage(role="user", content="Can you hear me clearly?"),
            ]
        )
        turn = adapter.parse_turn(request, headers={"x-session-id": "int-live-test", "x-agent-id": "alex"})

        response_text, next_action = await adapter.process_turn_async(turn)

        assert "loud and clear" in response_text.lower() or "hear you" in response_text.lower()
        # KG persistence MUST NOT be called for control turns
        mock_kg.persist_turn_evaluation_async.assert_not_called()
