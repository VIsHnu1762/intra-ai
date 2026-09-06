"""Intra AI Knowledge Graph package.

Provides domain models, Neo4j schema definitions, and repository abstractions for
persistent candidate knowledge projection.
"""

from app.knowledge_graph.exceptions import (
    EntityNotFoundError,
    EntityValidationError,
    KnowledgeGraphError,
    Neo4jConfigurationError,
    Neo4jConnectionError,
    RelationshipValidationError,
)
from app.knowledge_graph.models import (
    ALLOWED_RELATIONSHIPS,
    Answer,
    Candidate,
    CandidateGraphResponse,
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
    ENTITY_LABEL_TO_ID_FIELD,
    InMemoryKnowledgeGraphRepository,
    KnowledgeGraphRepository,
)
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
from app.knowledge_graph.schema import (
    ALL_SCHEMA_STATEMENTS,
    CONSTRAINTS,
    INDEXES,
    initialize_neo4j_schema,
)
from app.knowledge_graph.service import (
    KnowledgeGraphPersistenceResult,
    KnowledgeGraphPersistenceService,
    derive_question_id,
    derive_round_id,
    normalize_competency_id,
)

__all__ = [
    # Models
    "Candidate",
    "InterviewRound",
    "Question",
    "Answer",
    "Evidence",
    "Competency",
    "Project",
    "Technology",
    "Skill",
    "GraphRelationship",
    "GraphRelationshipType",
    "CandidateGraphResponse",
    "ALLOWED_RELATIONSHIPS",
    "validate_relationship_compatibility",
    # Repositories
    "KnowledgeGraphRepository",
    "InMemoryKnowledgeGraphRepository",
    "Neo4jKnowledgeGraphRepository",
    "ENTITY_LABEL_TO_ID_FIELD",
    # Services
    "KnowledgeGraphPersistenceService",
    "KnowledgeGraphPersistenceResult",
    "CandidateMemoryService",
    "PersistentCandidateMemory",
    "RetrievedEvidence",
    "CompetencySummary",
    "ProjectSummary",
    "InterviewHistorySummary",
    "MemorySourceType",
    "DEFAULT_MAX_EVIDENCE",
    "DEFAULT_MAX_PROJECTS",
    "DEFAULT_MAX_ROUNDS",
    "DEFAULT_MAX_SKILLS",
    "DEFAULT_MAX_TECHNOLOGIES",
    "normalize_competency_id",
    "derive_round_id",
    "derive_question_id",
    # Schema
    "CONSTRAINTS",
    "INDEXES",
    "ALL_SCHEMA_STATEMENTS",
    "initialize_neo4j_schema",
    # Exceptions
    "KnowledgeGraphError",
    "EntityValidationError",
    "RelationshipValidationError",
    "EntityNotFoundError",
    "Neo4jConfigurationError",
    "Neo4jConnectionError",
]
