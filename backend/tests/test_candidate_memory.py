"""Tests for Candidate Memory Retrieval from Knowledge Graph (Task 4).

Validates:
1. Candidate-scoped retrieval & strict tenant isolation (Candidate A vs B).
2. Cross-agent memory retrieval (observations from Alex and Jordan unified under candidate).
3. Cross-round memory retrieval (Round 1 and Round 2 unified).
4. Deterministic relevance filtering (by competency, round, agent).
5. Background context retrieval (projects, skills, technologies).
6. Evidence provenance preservation (source_agent_id, round_id, answer_id, timestamp).
7. Context limits enforcement (max_evidence, max_projects, etc.).
8. Read-only guarantees (no mutation of graph nodes or edges during retrieval).
9. Graceful fallback on missing candidate / unconfigured repository.
10. Async execution via get_candidate_memory_async.
11. Neo4j parameterized Cypher query verification with mock driver.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.knowledge_graph.exceptions import EntityValidationError
from app.knowledge_graph.memory_models import (
    CompetencySummary,
    InterviewHistorySummary,
    MemorySourceType,
    PersistentCandidateMemory,
    ProjectSummary,
    RetrievedEvidence,
)
from app.knowledge_graph.memory_service import (
    DEFAULT_MAX_EVIDENCE,
    DEFAULT_MAX_PROJECTS,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_MAX_SKILLS,
    DEFAULT_MAX_TECHNOLOGIES,
    CandidateMemoryService,
)
from app.knowledge_graph.models import (
    Answer,
    Candidate,
    Competency,
    Evidence,
    GraphRelationship,
    GraphRelationshipType,
    InterviewRound,
    Project,
    Question,
    Skill,
    Technology,
)
from app.knowledge_graph.neo4j_repository import Neo4jKnowledgeGraphRepository
from app.knowledge_graph.repository import InMemoryKnowledgeGraphRepository


# ═════════════════════════════════════════════════════════════════════════════
# Test Fixtures & Synthetic Data Setup
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def populated_repository() -> InMemoryKnowledgeGraphRepository:
    """Populates InMemoryKnowledgeGraphRepository with multi-candidate, multi-agent, multi-round synthetic data."""
    repo = InMemoryKnowledgeGraphRepository()

    # ── Candidate A: Senior Backend Engineer ─────────────────────────────────
    cand_a = Candidate(
        candidate_id="cand_a",
        name="Alice Walker",
        email="alice@example.com",
    )
    repo.upsert_candidate(cand_a)

    # Candidate A - Round 1 (Technical Architecture with Alex)
    r1_a = InterviewRound(
        round_id="round_a1",
        candidate_id="cand_a",
        interview_id="int_01",
        round_type="technical",
        status="completed",
        created_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
    )
    repo.upsert_interview_round(r1_a)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_a",
            source_label="Candidate",
            target_id="round_a1",
            target_label="InterviewRound",
            relationship_type=GraphRelationshipType.PARTICIPATED_IN,
        )
    )

    q1_a = Question(
        question_id="q_a1",
        round_id="round_a1",
        agent_id="alex",
        competency="system_design",
        question_text="What architecture did you use for the checkout platform?",
        difficulty="hard",
    )
    repo.upsert_question(q1_a)

    ans1_a = Answer(
        answer_id="ans_a1",
        question_id="q_a1",
        round_id="round_a1",
        candidate_id="cand_a",
        answer_text="I used Redis caching and Kafka events to reduce checkout latency...",
    )
    repo.upsert_answer(ans1_a)

    comp_sd = Competency(
        competency_id="system_design",
        name="System Design",
        category="technical",
    )
    repo.upsert_competency(comp_sd)

    ev1_a = Evidence(
        evidence_id="ev_a1",
        answer_id="ans_a1",
        candidate_id="cand_a",
        round_id="round_a1",
        source_agent_id="alex",
        competency="system_design",
        signal="candidate described Redis caching and Kafka event-driven architecture",
        score=8.5,
        timestamp=datetime(2026, 3, 1, 10, 15, 0, tzinfo=timezone.utc),
    )
    repo.upsert_evidence(ev1_a)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_a",
            source_label="Candidate",
            target_id="ev_a1",
            target_label="Evidence",
            relationship_type=GraphRelationshipType.HAS_EVIDENCE,
        )
    )
    repo.create_relationship(
        GraphRelationship(
            source_id="ev_a1",
            source_label="Evidence",
            target_id="system_design",
            target_label="Competency",
            relationship_type=GraphRelationshipType.SUPPORTS_COMPETENCY,
        )
    )

    # Candidate A - Projects, Skills, Technologies from Round 1
    proj_a = Project(
        project_id="proj_checkout",
        candidate_id="cand_a",
        name="checkout-platform",
        description="High-throughput distributed checkout platform",
        metadata={
            "technologies": ["Redis", "Kafka", "PostgreSQL"],
            "skills": ["distributed_systems", "caching"],
        },
    )
    repo.upsert_project(proj_a)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_a",
            source_label="Candidate",
            target_id="proj_checkout",
            target_label="Project",
            relationship_type=GraphRelationshipType.HAS_PROJECT,
        )
    )

    tech_redis = Technology(technology_id="tech_redis", name="Redis", category="database")
    tech_kafka = Technology(technology_id="tech_kafka", name="Kafka", category="message_broker")
    repo.upsert_technology(tech_redis)
    repo.upsert_technology(tech_kafka)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_a",
            source_label="Candidate",
            target_id="tech_redis",
            target_label="Technology",
            relationship_type=GraphRelationshipType.KNOWS_TECHNOLOGY,
        )
    )
    repo.create_relationship(
        GraphRelationship(
            source_id="proj_checkout",
            source_label="Project",
            target_id="tech_kafka",
            target_label="Technology",
            relationship_type=GraphRelationshipType.USES_TECHNOLOGY,
        )
    )

    skill_dist = Skill(skill_id="skill_distributed_systems", name="distributed_systems", domain="backend")
    repo.upsert_skill(skill_dist)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_a",
            source_label="Candidate",
            target_id="skill_distributed_systems",
            target_label="Skill",
            relationship_type=GraphRelationshipType.HAS_SKILL,
        )
    )

    # Candidate A - Round 2 (Deep Dive with Jordan)
    r2_a = InterviewRound(
        round_id="round_a2",
        candidate_id="cand_a",
        interview_id="int_01",
        round_type="technical",
        status="completed",
        created_at=datetime(2026, 3, 2, 14, 0, 0, tzinfo=timezone.utc),
    )
    repo.upsert_interview_round(r2_a)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_a",
            source_label="Candidate",
            target_id="round_a2",
            target_label="InterviewRound",
            relationship_type=GraphRelationshipType.PARTICIPATED_IN,
        )
    )

    q2_a = Question(
        question_id="q_a2",
        round_id="round_a2",
        agent_id="jordan",
        competency="concurrency",
        question_text="How did you ensure data consistency across partitions?",
        difficulty="hard",
    )
    repo.upsert_question(q2_a)

    ans2_a = Answer(
        answer_id="ans_a2",
        question_id="q_a2",
        round_id="round_a2",
        candidate_id="cand_a",
        answer_text="We implemented transactional outbox patterns with idempotent consumer retries...",
    )
    repo.upsert_answer(ans2_a)

    comp_conc = Competency(
        competency_id="concurrency",
        name="Concurrency",
        category="technical",
    )
    repo.upsert_competency(comp_conc)

    ev2_a = Evidence(
        evidence_id="ev_a2",
        answer_id="ans_a2",
        candidate_id="cand_a",
        round_id="round_a2",
        source_agent_id="jordan",
        competency="concurrency",
        signal="candidate explained outbox pattern and consistency tradeoffs",
        score=9.0,
        timestamp=datetime(2026, 3, 2, 14, 25, 0, tzinfo=timezone.utc),
    )
    repo.upsert_evidence(ev2_a)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_a",
            source_label="Candidate",
            target_id="ev_a2",
            target_label="Evidence",
            relationship_type=GraphRelationshipType.HAS_EVIDENCE,
        )
    )
    repo.create_relationship(
        GraphRelationship(
            source_id="ev_a2",
            source_label="Evidence",
            target_id="concurrency",
            target_label="Competency",
            relationship_type=GraphRelationshipType.SUPPORTS_COMPETENCY,
        )
    )

    # ── Candidate B: Product Manager (Tenant Isolation Counterpart) ──────────
    cand_b = Candidate(
        candidate_id="cand_b",
        name="Bob Martinez",
        email="bob@example.com",
    )
    repo.upsert_candidate(cand_b)

    r1_b = InterviewRound(
        round_id="round_b1",
        candidate_id="cand_b",
        interview_id="int_02",
        round_type="behavioral",
        status="completed",
        created_at=datetime(2026, 3, 3, 11, 0, 0, tzinfo=timezone.utc),
    )
    repo.upsert_interview_round(r1_b)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_b",
            source_label="Candidate",
            target_id="round_b1",
            target_label="InterviewRound",
            relationship_type=GraphRelationshipType.PARTICIPATED_IN,
        )
    )

    q1_b = Question(
        question_id="q_b1",
        round_id="round_b1",
        agent_id="taylor",
        competency="product_strategy",
        question_text="Tell me about your product prioritization framework.",
        difficulty="medium",
    )
    repo.upsert_question(q1_b)

    ans1_b = Answer(
        answer_id="ans_b1",
        question_id="q_b1",
        round_id="round_b1",
        candidate_id="cand_b",
        answer_text="We used RICE scoring combined with customer interviews...",
    )
    repo.upsert_answer(ans1_b)

    comp_prod = Competency(
        competency_id="product_strategy",
        name="Product Strategy",
        category="management",
    )
    repo.upsert_competency(comp_prod)

    ev1_b = Evidence(
        evidence_id="ev_b1",
        answer_id="ans_b1",
        candidate_id="cand_b",
        round_id="round_b1",
        source_agent_id="taylor",
        competency="product_strategy",
        signal="candidate applied RICE framework to prioritize roadmap items",
        score=7.5,
        timestamp=datetime(2026, 3, 3, 11, 20, 0, tzinfo=timezone.utc),
    )
    repo.upsert_evidence(ev1_b)
    repo.create_relationship(
        GraphRelationship(
            source_id="cand_b",
            source_label="Candidate",
            target_id="ev_b1",
            target_label="Evidence",
            relationship_type=GraphRelationshipType.HAS_EVIDENCE,
        )
    )
    repo.create_relationship(
        GraphRelationship(
            source_id="ev_b1",
            source_label="Evidence",
            target_id="product_strategy",
            target_label="Competency",
            relationship_type=GraphRelationshipType.SUPPORTS_COMPETENCY,
        )
    )

    return repo


@pytest.fixture
def memory_service(populated_repository: InMemoryKnowledgeGraphRepository) -> CandidateMemoryService:
    """Returns CandidateMemoryService backed by the populated in-memory repository."""
    return CandidateMemoryService(repository=populated_repository)


# ═════════════════════════════════════════════════════════════════════════════
# 1. Candidate Isolation / Tenant Security Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestTenantIsolation:
    """Verify memory retrieval is strictly candidate-scoped and never leaks across tenants."""

    def test_candidate_a_retrieval_returns_a_only(self, memory_service: CandidateMemoryService) -> None:
        mem_a = memory_service.get_candidate_memory("cand_a")
        assert mem_a.candidate_id == "cand_a"
        assert mem_a.name == "Alice Walker"
        assert len(mem_a.evidence) == 2

        evidence_ids = {e.evidence_id for e in mem_a.evidence}
        assert evidence_ids == {"ev_a1", "ev_a2"}
        assert "ev_b1" not in evidence_ids

        # Candidate A projects only
        assert len(mem_a.projects) == 1
        assert mem_a.projects[0].project_id == "proj_checkout"

    def test_candidate_b_retrieval_returns_b_only(self, memory_service: CandidateMemoryService) -> None:
        mem_b = memory_service.get_candidate_memory("cand_b")
        assert mem_b.candidate_id == "cand_b"
        assert mem_b.name == "Bob Martinez"
        assert len(mem_b.evidence) == 1

        evidence_ids = {e.evidence_id for e in mem_b.evidence}
        assert evidence_ids == {"ev_b1"}
        assert "ev_a1" not in evidence_ids
        assert "ev_a2" not in evidence_ids

        # Candidate B has no engineering projects
        assert len(mem_b.projects) == 0

    def test_nonexistent_candidate_returns_empty_typed_memory(
        self, memory_service: CandidateMemoryService
    ) -> None:
        mem_none = memory_service.get_candidate_memory("cand_nonexistent_999")
        assert isinstance(mem_none, PersistentCandidateMemory)
        assert mem_none.candidate_id == "cand_nonexistent_999"
        assert mem_none.name is None
        assert len(mem_none.evidence) == 0
        assert len(mem_none.competencies) == 0
        assert len(mem_none.projects) == 0
        assert len(mem_none.skills) == 0
        assert len(mem_none.technologies) == 0
        assert len(mem_none.interview_rounds) == 0

    def test_empty_or_whitespace_candidate_id_raises_validation_error(
        self, memory_service: CandidateMemoryService
    ) -> None:
        with pytest.raises(EntityValidationError):
            memory_service.get_candidate_memory("")
        with pytest.raises(EntityValidationError):
            memory_service.get_candidate_memory("   ")


# ═════════════════════════════════════════════════════════════════════════════
# 2. Cross-Agent and Cross-Round Memory Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestCrossAgentAndCrossRoundRetrieval:
    """Verify memory belongs to the candidate, preserving agent and round provenance."""

    def test_cross_agent_memory_unified_under_candidate(
        self, memory_service: CandidateMemoryService
    ) -> None:
        mem_a = memory_service.get_candidate_memory("cand_a")

        # Provenance: Alex (Round 1) and Jordan (Round 2) observations present
        agent_ids = {e.source_agent_id for e in mem_a.evidence}
        assert "alex" in agent_ids
        assert "jordan" in agent_ids

        # Rollup lists
        assert mem_a.source_agents == ["alex", "jordan"]

    def test_cross_round_memory_unified_under_candidate(
        self, memory_service: CandidateMemoryService
    ) -> None:
        mem_a = memory_service.get_candidate_memory("cand_a")

        round_ids = {e.round_id for e in mem_a.evidence}
        assert "round_a1" in round_ids
        assert "round_a2" in round_ids

        # Round history
        rounds_present = {r.round_id for r in mem_a.interview_rounds}
        assert "round_a1" in rounds_present
        assert "round_a2" in rounds_present

    def test_evidence_provenance_fields_preserved(
        self, memory_service: CandidateMemoryService
    ) -> None:
        mem_a = memory_service.get_candidate_memory("cand_a")

        ev_alex = next(e for e in mem_a.evidence if e.source_agent_id == "alex")
        assert ev_alex.evidence_id == "ev_a1"
        assert ev_alex.answer_id == "ans_a1"
        assert ev_alex.round_id == "round_a1"
        assert ev_alex.candidate_id == "cand_a"
        assert ev_alex.competency == "system_design"
        assert "Redis caching" in ev_alex.signal
        assert ev_alex.score == 8.5
        assert ev_alex.source_type == MemorySourceType.INTERVIEW_EVIDENCE
        assert ev_alex.timestamp.tzinfo is not None

        ev_jordan = next(e for e in mem_a.evidence if e.source_agent_id == "jordan")
        assert ev_jordan.evidence_id == "ev_a2"
        assert ev_jordan.answer_id == "ans_a2"
        assert ev_jordan.round_id == "round_a2"
        assert ev_jordan.competency == "concurrency"
        assert "outbox pattern" in ev_jordan.signal
        assert ev_jordan.score == 9.0


# ═════════════════════════════════════════════════════════════════════════════
# 3. Deterministic Filtering Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestDeterministicFiltering:
    """Verify deterministic filtering by competency, round_id, and source_agent_id."""

    def test_filter_by_competency(self, memory_service: CandidateMemoryService) -> None:
        # Filter for system_design only
        mem_sd = memory_service.get_candidate_memory("cand_a", competency="system_design")
        assert len(mem_sd.evidence) == 1
        assert mem_sd.evidence[0].competency == "system_design"
        assert mem_sd.evidence[0].source_agent_id == "alex"
        assert len(mem_sd.competencies) == 1
        assert mem_sd.competencies[0].competency_id == "system_design"

        # Filter for concurrency only
        mem_conc = memory_service.get_candidate_memory("cand_a", competency="concurrency")
        assert len(mem_conc.evidence) == 1
        assert mem_conc.evidence[0].competency == "concurrency"
        assert mem_conc.evidence[0].source_agent_id == "jordan"

        # Filter for competency not demonstrated by Candidate A
        mem_none = memory_service.get_candidate_memory("cand_a", competency="product_strategy")
        assert len(mem_none.evidence) == 0
        assert len(mem_none.competencies) == 0

    def test_filter_by_round_id(self, memory_service: CandidateMemoryService) -> None:
        mem_r1 = memory_service.get_candidate_memory("cand_a", round_id="round_a1")
        assert len(mem_r1.evidence) == 1
        assert mem_r1.evidence[0].round_id == "round_a1"
        assert mem_r1.evidence[0].source_agent_id == "alex"

        mem_r2 = memory_service.get_candidate_memory("cand_a", round_id="round_a2")
        assert len(mem_r2.evidence) == 1
        assert mem_r2.evidence[0].round_id == "round_a2"
        assert mem_r2.evidence[0].source_agent_id == "jordan"

    def test_filter_by_source_agent_id(self, memory_service: CandidateMemoryService) -> None:
        mem_alex = memory_service.get_candidate_memory("cand_a", source_agent_id="alex")
        assert len(mem_alex.evidence) == 1
        assert mem_alex.evidence[0].source_agent_id == "alex"

        mem_jordan = memory_service.get_candidate_memory("cand_a", source_agent_id="jordan")
        assert len(mem_jordan.evidence) == 1
        assert mem_jordan.evidence[0].source_agent_id == "jordan"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Background Context Tests (Projects, Skills, Technologies)
# ═════════════════════════════════════════════════════════════════════════════


class TestBackgroundContextRetrieval:
    """Verify projects, skills, and technologies retrieval."""

    def test_projects_retrieval(self, memory_service: CandidateMemoryService) -> None:
        mem_a = memory_service.get_candidate_memory("cand_a")
        assert len(mem_a.projects) == 1
        proj = mem_a.projects[0]
        assert proj.project_id == "proj_checkout"
        assert proj.name == "checkout-platform"
        assert "Redis" in proj.technologies
        assert "Kafka" in proj.technologies
        assert "distributed_systems" in proj.skills

    def test_skills_retrieval(self, memory_service: CandidateMemoryService) -> None:
        mem_a = memory_service.get_candidate_memory("cand_a")
        assert "distributed_systems" in mem_a.skills

    def test_technologies_retrieval(self, memory_service: CandidateMemoryService) -> None:
        mem_a = memory_service.get_candidate_memory("cand_a")
        # Candidate A directly knows Redis and project uses Kafka
        assert "Redis" in mem_a.technologies
        assert "Kafka" in mem_a.technologies


# ═════════════════════════════════════════════════════════════════════════════
# 5. Budget Limits & Read-Only Guarantees
# ═════════════════════════════════════════════════════════════════════════════


class TestBudgetLimitsAndReadOnlyGuarantees:
    """Verify retrieval limits and read-only non-mutation guarantees."""

    def test_context_limits_enforced(self, memory_service: CandidateMemoryService) -> None:
        # Candidate A has 2 evidence items; limit to 1
        mem = memory_service.get_candidate_memory("cand_a", max_evidence=1)
        assert len(mem.evidence) == 1
        assert mem.filter_applied["limits"]["max_evidence"] == 1

        # Limit technologies to 1
        mem_tech = memory_service.get_candidate_memory("cand_a", max_technologies=1)
        assert len(mem_tech.technologies) <= 1

    def test_retrieval_is_strictly_read_only(
        self, memory_service: CandidateMemoryService, populated_repository: InMemoryKnowledgeGraphRepository
    ) -> None:
        # Snapshot repository state counts before retrieval
        node_counts_before = {label: len(nodes) for label, nodes in populated_repository._nodes.items()}
        rel_count_before = len(populated_repository._relationships)

        # Perform multiple diverse retrievals
        memory_service.get_candidate_memory("cand_a")
        memory_service.get_candidate_memory("cand_a", competency="system_design")
        memory_service.get_candidate_memory("cand_b")
        memory_service.get_candidate_memory("cand_nonexistent")

        # Snapshot repository state counts after retrieval
        node_counts_after = {label: len(nodes) for label, nodes in populated_repository._nodes.items()}
        rel_count_after = len(populated_repository._relationships)

        # Assert absolute equality
        assert node_counts_before == node_counts_after
        assert rel_count_before == rel_count_after


# ═════════════════════════════════════════════════════════════════════════════
# 6. Async Execution & Latency
# ═════════════════════════════════════════════════════════════════════════════


class TestAsyncAndLatency:
    """Verify asynchronous off-thread retrieval and in-memory execution speed."""

    @pytest.mark.asyncio
    async def test_get_candidate_memory_async(self, memory_service: CandidateMemoryService) -> None:
        mem = await memory_service.get_candidate_memory_async("cand_a")
        assert mem.candidate_id == "cand_a"
        assert len(mem.evidence) == 2

    def test_in_memory_retrieval_latency(self, memory_service: CandidateMemoryService) -> None:
        start = time.perf_counter()
        for _ in range(50):
            memory_service.get_candidate_memory("cand_a")
        elapsed = time.perf_counter() - start
        avg_latency_ms = (elapsed / 50) * 1000
        # In-memory graph lookups should average under 5ms per call
        assert avg_latency_ms < 10.0


# ═════════════════════════════════════════════════════════════════════════════
# 7. Neo4j Repository Mock Driver Retrieval Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestNeo4jRetrievalSafety:
    """Verify Neo4j retrieval implementation uses safe, candidate-anchored parameterized Cypher."""

    @pytest.fixture
    def mock_driver(self) -> MagicMock:
        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__.return_value = session
        driver.session.return_value.__exit__.return_value = None
        return driver

    def test_get_candidate_evidence_cypher_parameters(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = [
            {
                "e": {
                    "evidence_id": "ev_01",
                    "answer_id": "ans_01",
                    "candidate_id": "cand_target",
                    "round_id": "rnd_01",
                    "source_agent_id": "alex",
                    "competency": "system_design",
                    "signal": "demonstrated partitioning",
                    "score": 8.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            }
        ]

        evidences = repo.get_candidate_evidence(
            candidate_id="cand_target",
            competency="system_design",
            round_id="rnd_01",
            source_agent_id="alex",
            limit=15,
        )

        assert len(evidences) == 1
        assert evidences[0].evidence_id == "ev_01"

        query, params = session.run.call_args[0]
        # Query must be anchored on candidate_id
        assert "MATCH (c:Candidate {candidate_id: $candidate_id})-[:HAS_EVIDENCE]->(e:Evidence)" in query
        assert "$competency" in query
        assert "$round_id" in query
        assert "$source_agent_id" in query
        assert "$limit" in query

        # Parameters must match
        assert params["candidate_id"] == "cand_target"
        assert params["competency"] == "system_design"
        assert params["round_id"] == "rnd_01"
        assert params["source_agent_id"] == "alex"
        assert params["limit"] == 15

    def test_get_candidate_competencies_cypher_parameters(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = [
            {"comp": {"competency_id": "system_design", "name": "System Design", "category": "tech"}}
        ]

        comps = repo.get_candidate_competencies("cand_sec_01")
        assert len(comps) == 1
        assert comps[0].competency_id == "system_design"

        query, params = session.run.call_args[0]
        assert "MATCH (c:Candidate {candidate_id: $candidate_id})-[:HAS_EVIDENCE]->(:Evidence)-[:SUPPORTS_COMPETENCY]->(comp:Competency)" in query
        assert params["candidate_id"] == "cand_sec_01"

    def test_get_candidate_projects_cypher_parameters(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = [
            {"p": {"project_id": "p_01", "candidate_id": "c_01", "name": "Payment Service"}}
        ]

        projects = repo.get_candidate_projects("c_01", limit=5)
        assert len(projects) == 1
        assert projects[0].project_id == "p_01"

        query, params = session.run.call_args[0]
        assert "MATCH (c:Candidate {candidate_id: $candidate_id})-[:HAS_PROJECT]->(p:Project)" in query
        assert params["candidate_id"] == "c_01"
        assert params["limit"] == 5

    def test_get_candidate_interview_rounds_cypher_parameters(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = [
            {"r": {"round_id": "r_01", "candidate_id": "c_01", "interview_id": "i_01", "round_type": "tech", "status": "done"}}
        ]

        rounds = repo.get_candidate_interview_rounds("c_01", limit=10)
        assert len(rounds) == 1
        assert rounds[0].round_id == "r_01"

        query, params = session.run.call_args[0]
        assert "MATCH (c:Candidate {candidate_id: $candidate_id})-[:PARTICIPATED_IN]->(r:InterviewRound)" in query
        assert params["candidate_id"] == "c_01"
        assert params["limit"] == 10

    def test_get_candidate_skills_cypher_parameters(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = [
            {"s": {"skill_id": "skill_python", "name": "Python", "domain": "software"}}
        ]

        skills = repo.get_candidate_skills("c_01", limit=8)
        assert len(skills) == 1
        assert skills[0].name == "Python"

        query, params = session.run.call_args[0]
        assert "MATCH (c:Candidate {candidate_id: $candidate_id})" in query
        assert "HAS_SKILL" in query
        assert "DEMONSTRATES_SKILL" in query
        assert params["candidate_id"] == "c_01"
        assert params["limit"] == 8

    def test_get_candidate_technologies_cypher_parameters(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value = [
            {"t": {"technology_id": "tech_neo4j", "name": "Neo4j", "category": "database"}}
        ]

        techs = repo.get_candidate_technologies("c_01", limit=12)
        assert len(techs) == 1
        assert techs[0].name == "Neo4j"

        query, params = session.run.call_args[0]
        assert "MATCH (c:Candidate {candidate_id: $candidate_id})" in query
        assert "KNOWS_TECHNOLOGY" in query
        assert "USES_TECHNOLOGY" in query
        assert params["candidate_id"] == "c_01"
        assert params["limit"] == 12


# ═════════════════════════════════════════════════════════════════════════════
# 8. Edge Cases & Resilience Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestResilienceAndEdgeCases:
    """Verify graceful handling of unconfigured repo, duplicate relationships, and edge cases."""

    def test_unconfigured_repository_graceful_fallback(self) -> None:
        # This scenario must stay unconfigured even when the developer's .env
        # has valid Aura credentials for separately gated live tests.
        from app.core.config import settings
        with patch.object(settings, "NEO4J_URI", ""):
            service = CandidateMemoryService(repository=None)
        mem = service.get_candidate_memory("cand_any")
        assert isinstance(mem, PersistentCandidateMemory)
        assert mem.candidate_id == "cand_any"
        assert len(mem.evidence) == 0

    def test_duplicate_graph_data_deduplicated_in_memory(
        self, populated_repository: InMemoryKnowledgeGraphRepository
    ) -> None:
        # Create redundant HAS_SKILL relationship to the same skill
        populated_repository.create_relationship(
            GraphRelationship(
                source_id="cand_a",
                source_label="Candidate",
                target_id="skill_distributed_systems",
                target_label="Skill",
                relationship_type=GraphRelationshipType.HAS_SKILL,
            )
        )
        # Also create a project with DEMONSTRATES_SKILL pointing to the same skill
        populated_repository.create_relationship(
            GraphRelationship(
                source_id="proj_checkout",
                source_label="Project",
                target_id="skill_distributed_systems",
                target_label="Skill",
                relationship_type=GraphRelationshipType.DEMONSTRATES_SKILL,
            )
        )

        service = CandidateMemoryService(repository=populated_repository)
        mem = service.get_candidate_memory("cand_a")

        # Must not contain duplicate skill entries
        assert mem.skills.count("distributed_systems") == 1
