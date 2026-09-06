"""Unit tests for Intra AI Knowledge Graph domain models, schema, and repositories.

All tests run fully offline without requiring a live Neo4j AuraDB instance.
An optional live integration test is gated behind RUN_NEO4J_INTEGRATION_TESTS=1.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.knowledge_graph.exceptions import (
    EntityNotFoundError,
    EntityValidationError,
    Neo4jConfigurationError,
    RelationshipValidationError,
)
from app.knowledge_graph.models import (
    ALLOWED_RELATIONSHIPS,
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
    validate_relationship_compatibility,
)
from app.knowledge_graph.neo4j_repository import Neo4jKnowledgeGraphRepository
from app.knowledge_graph.repository import (
    InMemoryKnowledgeGraphRepository,
    KnowledgeGraphRepository,
)
from app.knowledge_graph.schema import (
    ALL_SCHEMA_STATEMENTS,
    CONSTRAINTS,
    INDEXES,
    initialize_neo4j_schema,
)


# ═════════════════════════════════════════════════════════════════════════════
# A. Domain Model Validation Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestDomainModels:
    """Test strongly-typed Pydantic graph models and validation constraints."""

    def test_candidate_valid(self) -> None:
        cand = Candidate(candidate_id="cand_123", name="Alice Chen", email="alice@example.com")
        assert cand.candidate_id == "cand_123"
        assert cand.name == "Alice Chen"
        assert cand.email == "alice@example.com"
        assert cand.created_at is not None

    def test_candidate_invalid_id(self) -> None:
        with pytest.raises(Exception):
            Candidate(candidate_id="")
        with pytest.raises(Exception):
            Candidate(candidate_id="   ")

    def test_interview_round_valid_and_invalid(self) -> None:
        rnd = InterviewRound(
            round_id="rnd_01",
            interview_id="int_01",
            candidate_id="cand_123",
            round_type="technical",
        )
        assert rnd.round_id == "rnd_01"

        with pytest.raises(Exception):
            InterviewRound(round_id="", interview_id="int_01", candidate_id="cand_123")
        with pytest.raises(Exception):
            InterviewRound(round_id="rnd_01", interview_id="", candidate_id="cand_123")

    def test_question_valid_and_invalid(self) -> None:
        q = Question(
            question_id="q_101",
            round_id="rnd_01",
            agent_id="alex",
            question_text="How do you handle distributed race conditions?",
            competency="concurrency",
            difficulty="hard",
        )
        assert q.question_id == "q_101"
        assert q.agent_id == "alex"

        with pytest.raises(Exception):
            Question(question_id="", round_id="rnd_01", agent_id="alex", question_text="text")
        with pytest.raises(Exception):
            Question(question_id="q_101", round_id="rnd_01", agent_id="alex", question_text=" ")

    def test_answer_valid_and_invalid(self) -> None:
        ans = Answer(
            answer_id="ans_201",
            question_id="q_101",
            candidate_id="cand_123",
            round_id="rnd_01",
            answer_text="I use distributed locks with TTL or optimistic locking.",
            duration_seconds=45,
        )
        assert ans.answer_id == "ans_201"
        assert ans.duration_seconds == 45

        with pytest.raises(Exception):
            Answer(
                answer_id="",
                question_id="q_101",
                candidate_id="cand_123",
                round_id="rnd_01",
                answer_text="valid",
            )

    def test_evidence_provenance_validation(self) -> None:
        """Evidence must strictly track source_agent_id, round_id, answer_id, candidate_id, signal."""
        ev = Evidence(
            evidence_id="ev_301",
            answer_id="ans_201",
            candidate_id="cand_123",
            round_id="rnd_01",
            source_agent_id="alex",
            competency="concurrency",
            signal="Understands distributed locks with Redis Redlock and fallback fencing tokens",
            score=8.5,
        )
        assert ev.evidence_id == "ev_301"
        assert ev.source_agent_id == "alex"
        assert ev.score == 8.5
        assert ev.timestamp is not None

        # Missing or empty provenance must fail
        with pytest.raises(Exception):
            Evidence(
                evidence_id="",
                answer_id="ans_201",
                candidate_id="cand_123",
                round_id="rnd_01",
                source_agent_id="alex",
                signal="signal",
            )
        with pytest.raises(Exception):
            Evidence(
                evidence_id="ev_301",
                answer_id="",
                candidate_id="cand_123",
                round_id="rnd_01",
                source_agent_id="alex",
                signal="signal",
            )
        with pytest.raises(Exception):
            Evidence(
                evidence_id="ev_301",
                answer_id="ans_201",
                candidate_id="cand_123",
                round_id="rnd_01",
                source_agent_id="",
                signal="signal",
            )
        with pytest.raises(Exception):
            Evidence(
                evidence_id="ev_301",
                answer_id="ans_201",
                candidate_id="cand_123",
                round_id="rnd_01",
                source_agent_id="alex",
                signal="",
            )

    def test_competency_project_technology_skill_models(self) -> None:
        comp = Competency(competency_id="system_design", name="System Design")
        assert comp.competency_id == "system_design"

        proj = Project(
            project_id="proj_01",
            candidate_id="cand_123",
            name="Streaming Pipeline",
            description="Real-time event processing with Kafka and Flink",
        )
        assert proj.project_id == "proj_01"

        tech = Technology(technology_id="kafka", name="Apache Kafka", category="streaming")
        assert tech.technology_id == "kafka"

        skill = Skill(skill_id="stream_processing", name="Stream Processing")
        assert skill.skill_id == "stream_processing"

        with pytest.raises(Exception):
            Competency(competency_id="", name="Valid")
        with pytest.raises(Exception):
            Project(project_id="", candidate_id="cand_123", name="Valid")
        with pytest.raises(Exception):
            Technology(technology_id="", name="Valid")
        with pytest.raises(Exception):
            Skill(skill_id="", name="Valid")


# ═════════════════════════════════════════════════════════════════════════════
# B. Relationship Validation Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestRelationshipValidation:
    """Test relationship vocabulary and endpoint compatibility rules."""

    @pytest.mark.parametrize(
        "source,target,rel_type",
        [
            ("Candidate", "InterviewRound", GraphRelationshipType.PARTICIPATED_IN),
            ("Candidate", "Project", GraphRelationshipType.HAS_PROJECT),
            ("Candidate", "Skill", GraphRelationshipType.HAS_SKILL),
            ("Candidate", "Technology", GraphRelationshipType.KNOWS_TECHNOLOGY),
            ("Candidate", "Evidence", GraphRelationshipType.HAS_EVIDENCE),
            ("InterviewRound", "Question", GraphRelationshipType.HAS_QUESTION),
            ("InterviewRound", "Answer", GraphRelationshipType.HAS_ANSWER),
            ("Question", "Answer", GraphRelationshipType.HAS_ANSWER),
            ("Question", "Competency", GraphRelationshipType.TARGETS_COMPETENCY),
            ("Answer", "Evidence", GraphRelationshipType.SUPPORTED_BY),
            ("Evidence", "Competency", GraphRelationshipType.SUPPORTS_COMPETENCY),
            ("Project", "Technology", GraphRelationshipType.USES_TECHNOLOGY),
            ("Project", "Skill", GraphRelationshipType.DEMONSTRATES_SKILL),
        ],
    )
    def test_valid_relationships(
        self, source: str, target: str, rel_type: GraphRelationshipType
    ) -> None:
        validated = validate_relationship_compatibility(source, target, rel_type)
        assert validated == rel_type

    def test_invalid_relationship_type_string(self) -> None:
        with pytest.raises(RelationshipValidationError) as excinfo:
            validate_relationship_compatibility("Candidate", "Project", "NON_EXISTENT_REL")
        assert "Unknown relationship type" in str(excinfo.value)

    def test_incompatible_endpoint_combination(self) -> None:
        # Candidate cannot directly TARGETS_COMPETENCY
        with pytest.raises(RelationshipValidationError) as excinfo:
            validate_relationship_compatibility(
                "Candidate", "Competency", GraphRelationshipType.TARGETS_COMPETENCY
            )
        assert "is not permitted between source" in str(excinfo.value)

        # Question cannot USES_TECHNOLOGY
        with pytest.raises(RelationshipValidationError):
            validate_relationship_compatibility(
                "Question", "Technology", GraphRelationshipType.USES_TECHNOLOGY
            )


# ═════════════════════════════════════════════════════════════════════════════
# C. Repository Behavior Tests (InMemory Repository)
# ═════════════════════════════════════════════════════════════════════════════


class TestInMemoryRepository:
    """Verify repository operations and idempotency using InMemory implementation."""

    def test_crud_and_idempotent_upsert(self) -> None:
        repo = InMemoryKnowledgeGraphRepository()

        # Create Candidate
        cand1 = Candidate(candidate_id="c_01", name="Alice", email="alice@test.com")
        repo.upsert_candidate(cand1)
        fetched = repo.get_candidate("c_01")
        assert fetched is not None
        assert fetched.name == "Alice"

        # Update Candidate (idempotent write)
        cand2 = Candidate(candidate_id="c_01", name="Alice Updated", email="alice@test.com")
        repo.upsert_candidate(cand2)
        updated = repo.get_candidate("c_01")
        assert updated is not None
        assert updated.name == "Alice Updated"

    def test_all_entity_types_roundtrip(self) -> None:
        repo = InMemoryKnowledgeGraphRepository()

        rnd = InterviewRound(round_id="r_01", interview_id="int_01", candidate_id="c_01")
        repo.upsert_interview_round(rnd)
        assert repo.get_interview_round("r_01") is not None

        q = Question(
            question_id="q_01",
            round_id="r_01",
            agent_id="alex",
            question_text="Describe CAP theorem.",
        )
        repo.upsert_question(q)
        assert repo.get_question("q_01") is not None

        ans = Answer(
            answer_id="a_01",
            question_id="q_01",
            candidate_id="c_01",
            round_id="r_01",
            answer_text="Consistency, Availability, Partition tolerance.",
        )
        repo.upsert_answer(ans)
        assert repo.get_answer("a_01") is not None

        ev = Evidence(
            evidence_id="e_01",
            answer_id="a_01",
            candidate_id="c_01",
            round_id="r_01",
            source_agent_id="alex",
            signal="Accurately explained PACELC trade-offs",
            score=9.0,
        )
        repo.upsert_evidence(ev)
        assert repo.get_evidence("e_01") is not None

        comp = Competency(competency_id="distributed_systems", name="Distributed Systems")
        repo.upsert_competency(comp)
        assert repo.get_competency("distributed_systems") is not None

        proj = Project(project_id="p_01", candidate_id="c_01", name="Ledger DB")
        repo.upsert_project(proj)
        assert repo.get_project("p_01") is not None

        tech = Technology(technology_id="postgres", name="PostgreSQL")
        repo.upsert_technology(tech)
        assert repo.get_technology("postgres") is not None

        skill = Skill(skill_id="acid_tx", name="ACID Transactions")
        repo.upsert_skill(skill)
        assert repo.get_skill("acid_tx") is not None

    def test_relationship_creation_and_validation(self) -> None:
        repo = InMemoryKnowledgeGraphRepository()
        cand = Candidate(candidate_id="c_01", name="Bob")
        proj = Project(project_id="p_01", candidate_id="c_01", name="Crawler")
        repo.upsert_candidate(cand)
        repo.upsert_project(proj)

        # Valid relationship
        rel = GraphRelationship(
            source_id="c_01",
            source_label="Candidate",
            target_id="p_01",
            target_label="Project",
            relationship_type=GraphRelationshipType.HAS_PROJECT,
        )
        created = repo.create_relationship(rel)
        assert created.relationship_type == GraphRelationshipType.HAS_PROJECT

        # Non-existent target node raises EntityNotFoundError
        rel_bad_target = GraphRelationship(
            source_id="c_01",
            source_label="Candidate",
            target_id="p_missing",
            target_label="Project",
            relationship_type=GraphRelationshipType.HAS_PROJECT,
        )
        with pytest.raises(EntityNotFoundError):
            repo.create_relationship(rel_bad_target)

        # Non-existent source node raises EntityNotFoundError
        rel_bad_source = GraphRelationship(
            source_id="c_missing",
            source_label="Candidate",
            target_id="p_01",
            target_label="Project",
            relationship_type=GraphRelationshipType.HAS_PROJECT,
        )
        with pytest.raises(EntityNotFoundError):
            repo.create_relationship(rel_bad_source)

    def test_get_candidate_graph_neighborhood(self) -> None:
        repo = InMemoryKnowledgeGraphRepository()

        # Build connected subgraph
        cand = Candidate(candidate_id="c_01", name="Carol")
        rnd = InterviewRound(round_id="r_01", interview_id="int_01", candidate_id="c_01")
        q = Question(
            question_id="q_01",
            round_id="r_01",
            agent_id="alex",
            question_text="Explain sharding.",
        )
        ans = Answer(
            answer_id="a_01",
            question_id="q_01",
            candidate_id="c_01",
            round_id="r_01",
            answer_text="Horizontal partitioning of data.",
        )
        ev = Evidence(
            evidence_id="e_01",
            answer_id="a_01",
            candidate_id="c_01",
            round_id="r_01",
            source_agent_id="alex",
            signal="Understands range vs hash partitioning",
            score=8.0,
        )

        repo.upsert_candidate(cand)
        repo.upsert_interview_round(rnd)
        repo.upsert_question(q)
        repo.upsert_answer(ans)
        repo.upsert_evidence(ev)

        repo.create_relationship(
            GraphRelationship(
                source_id="c_01",
                source_label="Candidate",
                target_id="r_01",
                target_label="InterviewRound",
                relationship_type=GraphRelationshipType.PARTICIPATED_IN,
            )
        )
        repo.create_relationship(
            GraphRelationship(
                source_id="c_01",
                source_label="Candidate",
                target_id="e_01",
                target_label="Evidence",
                relationship_type=GraphRelationshipType.HAS_EVIDENCE,
            )
        )

        # Depth 1 traversal
        subgraph = repo.get_candidate_graph(candidate_id="c_01", depth=1)
        assert subgraph.candidate_id == "c_01"
        assert subgraph.depth == 1
        node_ids = {n["id"] for n in subgraph.nodes}
        assert "c_01" in node_ids
        assert "r_01" in node_ids
        assert "e_01" in node_ids
        assert len(subgraph.relationships) == 2

    def test_candidate_graph_depth_validation(self) -> None:
        repo = InMemoryKnowledgeGraphRepository()
        with pytest.raises(EntityValidationError):
            repo.get_candidate_graph("c_01", depth=0)
        with pytest.raises(EntityValidationError):
            repo.get_candidate_graph("c_01", depth=4)
        with pytest.raises(EntityValidationError):
            repo.get_candidate_graph("   ", depth=1)


# ═════════════════════════════════════════════════════════════════════════════
# D. Neo4j Repository & Query Safety Tests (Mocked Driver)
# ═════════════════════════════════════════════════════════════════════════════


class TestNeo4jRepositorySafety:
    """Verify Neo4j repository enforces parameterized queries without text interpolation."""

    @pytest.fixture
    def mock_driver(self) -> MagicMock:
        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__.return_value = session
        driver.session.return_value.__exit__.return_value = None
        return driver

    def test_upsert_candidate_parameterized_query(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        cand = Candidate(
            candidate_id="cand_safe_01",
            name="Inject'); DROP (n); --",
            email="safe@example.com",
        )
        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value.single.return_value = {"c": cand.model_dump()}

        repo.upsert_candidate(cand)

        # Verify session.run was called
        assert session.run.called
        query, params = session.run.call_args[0]

        # 1. The query MUST NOT contain candidate text
        assert "Inject'); DROP (n); --" not in query
        assert "$id" in query
        assert "$props" in query

        # 2. The parameters MUST contain the raw values safely
        assert params["id"] == "cand_safe_01"
        assert params["props"]["name"] == "Inject'); DROP (n); --"

    def test_upsert_evidence_parameterized_query(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        ev = Evidence(
            evidence_id="ev_safe_01",
            answer_id="ans_01",
            candidate_id="cand_01",
            round_id="rnd_01",
            source_agent_id="alex",
            signal="Critical quote: 'DROP ALL TABLES;' should be handled gracefully",
            score=9.2,
        )
        session = mock_driver.session.return_value.__enter__.return_value
        session.run.return_value.single.return_value = {"e": ev.model_dump()}

        repo.upsert_evidence(ev)

        query, params = session.run.call_args[0]
        assert "DROP ALL TABLES" not in query
        assert "$id" in query
        assert "$props" in query
        assert params["props"]["signal"] == "Critical quote: 'DROP ALL TABLES;' should be handled gracefully"

    def test_create_relationship_parameterized(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        session = mock_driver.session.return_value.__enter__.return_value

        # Mock existence check returning source & target
        session.run.side_effect = [
            MagicMock(single=lambda: {"n": {"candidate_id": "c_01"}}),  # source exists
            MagicMock(single=lambda: {"n": {"project_id": "p_01"}}),    # target exists
            MagicMock(single=lambda: {"r": {}}),                        # rel merged
        ]

        rel = GraphRelationship(
            source_id="c_01",
            source_label="Candidate",
            target_id="p_01",
            target_label="Project",
            relationship_type=GraphRelationshipType.HAS_PROJECT,
            properties={"weight": 1.0},
        )

        repo.create_relationship(rel)

        rel_query, rel_params = session.run.call_args[0]
        assert "$source_id" in rel_query
        assert "$target_id" in rel_query
        assert "$props" in rel_query
        assert rel_params["source_id"] == "c_01"
        assert rel_params["target_id"] == "p_01"
        assert rel_params["props"]["weight"] == 1.0

    def test_connectivity_and_close(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        mock_driver.verify_connectivity.return_value = None
        assert repo.verify_connectivity() is True

        mock_driver.verify_connectivity.side_effect = Exception("Network unreachable")
        assert repo.verify_connectivity() is False

        repo.close()
        mock_driver.close.assert_called_once()

    def test_get_candidate_graph_neo4j_parameterized(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )

        session = mock_driver.session.return_value.__enter__.return_value

        # Mock node and path objects
        mock_cand_node = MagicMock()
        mock_cand_node.labels = ["Candidate"]
        mock_cand_node.__iter__.return_value = ["candidate_id", "name"].__iter__()
        mock_cand_node.get.side_effect = lambda k, default=None: {"candidate_id": "cand_01", "name": "Carol"}.get(k, default)
        mock_cand_node.items.return_value = [("candidate_id", "cand_01"), ("name", "Carol")]

        mock_proj_node = MagicMock()
        mock_proj_node.labels = ["Project"]
        mock_proj_node.items.return_value = [("project_id", "proj_01"), ("name", "Crawler")]

        mock_rel = MagicMock()
        mock_rel.type = "HAS_PROJECT"
        mock_rel.items.return_value = [("weight", 1.0)]
        mock_rel.start_node = mock_cand_node
        mock_rel.end_node = mock_proj_node

        mock_path = MagicMock()
        mock_path.nodes = [mock_cand_node, mock_proj_node]
        mock_path.relationships = [mock_rel]

        # 1st call: existence check for Candidate
        # 2nd call: traversal query
        session.run.side_effect = [
            MagicMock(single=lambda: {"n": {"candidate_id": "cand_01", "name": "Carol"}}),
            MagicMock(single=lambda: {"c": mock_cand_node, "valid_paths": [mock_path]}),
        ]

        graph = repo.get_candidate_graph("cand_01", depth=1)
        assert graph.candidate_id == "cand_01"
        assert graph.depth == 1
        assert len(graph.nodes) >= 1
        assert len(graph.relationships) == 1
        assert graph.relationships[0]["relationship_type"] == "HAS_PROJECT"

    def test_get_entity_by_id_invalid_label_rejected(self, mock_driver: MagicMock) -> None:
        repo = Neo4jKnowledgeGraphRepository(
            uri="neo4j+s://example.databases.neo4j.io",
            username="neo4j",
            password="secret_password",
            driver=mock_driver,
        )
        with pytest.raises(EntityValidationError) as excinfo:
            repo.get_entity_by_id("ArbitraryUnsafeLabel", "id_123")
        assert "Invalid entity label" in str(excinfo.value)


# ═════════════════════════════════════════════════════════════════════════════
# E. Configuration & Settings Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestNeo4jConfiguration:
    """Verify configuration loading and missing credentials error handling."""

    def test_from_settings_missing_credentials_raises_error(self) -> None:
        empty_settings = Settings(
            SUPABASE_URL="http://mock",
            SUPABASE_ANON_KEY="mock",
            SUPABASE_SERVICE_ROLE_KEY="mock",
            DATABASE_URL="postgresql://mock",
            OPENAI_API_KEY="mock",
            JWT_SECRET="mock-secret-key-at-least-32-chars-long!",
            NEO4J_URI="",
            NEO4J_USERNAME="",
            NEO4J_PASSWORD="",
        )
        with pytest.raises(Neo4jConfigurationError) as excinfo:
            Neo4jKnowledgeGraphRepository.from_settings(empty_settings)
        assert "Missing required Neo4j configuration: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD" in str(
            excinfo.value
        )

    def test_from_settings_partial_missing_raises_error(self) -> None:
        partial_settings = Settings(
            SUPABASE_URL="http://mock",
            SUPABASE_ANON_KEY="mock",
            SUPABASE_SERVICE_ROLE_KEY="mock",
            DATABASE_URL="postgresql://mock",
            OPENAI_API_KEY="mock",
            JWT_SECRET="mock-secret-key-at-least-32-chars-long!",
            NEO4J_URI="neo4j+s://aura.databases.neo4j.io",
            NEO4J_USERNAME="neo4j",
            NEO4J_PASSWORD="",
        )
        with pytest.raises(Neo4jConfigurationError) as excinfo:
            Neo4jKnowledgeGraphRepository.from_settings(partial_settings)
        assert "NEO4J_PASSWORD" in str(excinfo.value)

    def test_from_settings_valid(self) -> None:
        valid_settings = Settings(
            SUPABASE_URL="http://mock",
            SUPABASE_ANON_KEY="mock",
            SUPABASE_SERVICE_ROLE_KEY="mock",
            DATABASE_URL="postgresql://mock",
            OPENAI_API_KEY="mock",
            JWT_SECRET="mock-secret-key-at-least-32-chars-long!",
            NEO4J_URI="neo4j+s://aura.databases.neo4j.io",
            NEO4J_USERNAME="neo4j",
            NEO4J_PASSWORD="super-secret-password",
        )
        mock_driver = MagicMock()
        repo = Neo4jKnowledgeGraphRepository.from_settings(valid_settings, driver=mock_driver)
        assert repo._uri == "neo4j+s://aura.databases.neo4j.io"
        assert repo._username == "neo4j"
        assert repo._password == "super-secret-password"


# ═════════════════════════════════════════════════════════════════════════════
# F. Schema Initialization Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestSchemaInitialization:
    """Verify idempotent constraint and index creation."""

    def test_schema_statements_definitions(self) -> None:
        # All 9 entity stable-ID constraints must be defined
        assert len(CONSTRAINTS) == 9
        for constraint in CONSTRAINTS:
            assert "CREATE CONSTRAINT" in constraint
            assert "IF NOT EXISTS" in constraint
            assert "IS UNIQUE" in constraint

        # Lookup indexes must be defined
        assert len(INDEXES) >= 9
        for index in INDEXES:
            assert "CREATE INDEX" in index
            assert "IF NOT EXISTS" in index

        assert len(ALL_SCHEMA_STATEMENTS) == len(CONSTRAINTS) + len(INDEXES)

    def test_schema_initialization_execution(self) -> None:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        mock_driver.session.return_value.__exit__.return_value = None

        executed = initialize_neo4j_schema(mock_driver, database="testdb")

        assert len(executed) == len(ALL_SCHEMA_STATEMENTS)
        assert mock_session.run.call_count == len(ALL_SCHEMA_STATEMENTS)


# ═════════════════════════════════════════════════════════════════════════════
# G. Optional Live Integration Test (Gated)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    os.getenv("RUN_NEO4J_INTEGRATION_TESTS") != "1",
    reason="Opt-in live Neo4j integration test requires RUN_NEO4J_INTEGRATION_TESTS=1",
)
def test_live_neo4j_integration() -> None:  # pragma: no cover
    """Optional end-to-end integration test against live Neo4j AuraDB."""
    repo = Neo4jKnowledgeGraphRepository.from_settings()
    assert repo.verify_connectivity() is True

    # Test candidate roundtrip
    cand = Candidate(candidate_id="live_test_01", name="Live Integration Candidate")
    repo.upsert_candidate(cand)

    fetched = repo.get_candidate("live_test_01")
    assert fetched is not None
    assert fetched.candidate_id == "live_test_01"

    repo.close()
