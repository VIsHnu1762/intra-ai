"""Repository abstraction and in-memory implementation for Intra AI Knowledge Graph."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime
from typing import Any, Optional
import structlog

from app.knowledge_graph.exceptions import (
    EntityNotFoundError,
    EntityValidationError,
    RelationshipValidationError,
)
from app.knowledge_graph.models import (
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

logger = structlog.stdlib.get_logger("intra_ai.knowledge_graph.repository")

ENTITY_LABEL_TO_ID_FIELD: dict[str, str] = {
    "Candidate": "candidate_id",
    "InterviewRound": "round_id",
    "Question": "question_id",
    "Answer": "answer_id",
    "Evidence": "evidence_id",
    "Competency": "competency_id",
    "Project": "project_id",
    "Technology": "technology_id",
    "Skill": "skill_id",
}


def _validate_depth(depth: int) -> int:
    """Validate graph traversal depth. Must be between 1 and 3."""
    if not isinstance(depth, int) or depth < 1 or depth > 3:
        raise EntityValidationError(f"Graph traversal depth must be an integer between 1 and 3, got: {depth}")
    return depth


def _serialize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Serialize datetime and non-primitive objects to JSON-compatible types."""
    serialized: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, datetime):
            serialized[k] = v.isoformat()
        elif isinstance(v, dict):
            serialized[k] = _serialize_dict(v)
        else:
            serialized[k] = v
    return serialized


class KnowledgeGraphRepository(ABC):
    """Abstract interface defining operations for Knowledge Graph persistence."""

    # ── Entity Upsert Operations ─────────────────────────────────────────────

    @abstractmethod
    def upsert_candidate(self, candidate: Candidate) -> Candidate:
        """Create or update a Candidate node."""
        ...

    @abstractmethod
    def upsert_interview_round(self, round_data: InterviewRound) -> InterviewRound:
        """Create or update an InterviewRound node."""
        ...

    @abstractmethod
    def upsert_question(self, question: Question) -> Question:
        """Create or update a Question node."""
        ...

    @abstractmethod
    def upsert_answer(self, answer: Answer) -> Answer:
        """Create or update an Answer node."""
        ...

    @abstractmethod
    def upsert_evidence(self, evidence: Evidence) -> Evidence:
        """Create or update an Evidence node with provenance."""
        ...

    @abstractmethod
    def upsert_competency(self, competency: Competency) -> Competency:
        """Create or update a Competency node."""
        ...

    @abstractmethod
    def upsert_project(self, project: Project) -> Project:
        """Create or update a Project node."""
        ...

    @abstractmethod
    def upsert_technology(self, technology: Technology) -> Technology:
        """Create or update a Technology node."""
        ...

    @abstractmethod
    def upsert_skill(self, skill: Skill) -> Skill:
        """Create or update a Skill node."""
        ...

    # ── Relationship Operations ──────────────────────────────────────────────

    @abstractmethod
    def create_relationship(self, relationship: GraphRelationship) -> GraphRelationship:
        """Create a validated directed relationship between two nodes."""
        ...

    # ── Entity Retrieval Operations ──────────────────────────────────────────

    @abstractmethod
    def get_candidate(self, candidate_id: str) -> Optional[Candidate]:
        """Fetch Candidate by candidate_id."""
        ...

    @abstractmethod
    def get_interview_round(self, round_id: str) -> Optional[InterviewRound]:
        """Fetch InterviewRound by round_id."""
        ...

    @abstractmethod
    def get_question(self, question_id: str) -> Optional[Question]:
        """Fetch Question by question_id."""
        ...

    @abstractmethod
    def get_answer(self, answer_id: str) -> Optional[Answer]:
        """Fetch Answer by answer_id."""
        ...

    @abstractmethod
    def get_evidence(self, evidence_id: str) -> Optional[Evidence]:
        """Fetch Evidence by evidence_id."""
        ...

    @abstractmethod
    def get_competency(self, competency_id: str) -> Optional[Competency]:
        """Fetch Competency by competency_id."""
        ...

    @abstractmethod
    def get_project(self, project_id: str) -> Optional[Project]:
        """Fetch Project by project_id."""
        ...

    @abstractmethod
    def get_technology(self, technology_id: str) -> Optional[Technology]:
        """Fetch Technology by technology_id."""
        ...

    @abstractmethod
    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """Fetch Skill by skill_id."""
        ...

    @abstractmethod
    def get_entity_by_id(self, label: str, entity_id: str) -> Optional[dict[str, Any]]:
        """Fetch generic node properties by label and ID."""
        ...

    # ── Candidate-Scoped Retrieval Operations ────────────────────────────────

    @abstractmethod
    def get_candidate_evidence(
        self,
        candidate_id: str,
        competency: Optional[str] = None,
        round_id: Optional[str] = None,
        source_agent_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[Evidence]:
        """Retrieve evidence items for a candidate with optional filtering."""
        ...

    @abstractmethod
    def get_candidate_competencies(
        self,
        candidate_id: str,
    ) -> list[Competency]:
        """Retrieve all competencies evaluated for a candidate."""
        ...

    @abstractmethod
    def get_candidate_projects(
        self,
        candidate_id: str,
        limit: int = 10,
    ) -> list[Project]:
        """Retrieve projects associated with a candidate."""
        ...

    @abstractmethod
    def get_candidate_skills(
        self,
        candidate_id: str,
        limit: int = 20,
    ) -> list[Skill]:
        """Retrieve skills demonstrated by or associated with a candidate."""
        ...

    @abstractmethod
    def get_candidate_technologies(
        self,
        candidate_id: str,
        limit: int = 20,
    ) -> list[Technology]:
        """Retrieve technologies known by or used by a candidate."""
        ...

    @abstractmethod
    def get_candidate_interview_rounds(
        self,
        candidate_id: str,
        limit: int = 10,
    ) -> list[InterviewRound]:
        """Retrieve all interview rounds attended by a candidate."""
        ...

    # ── Graph Query Operations ───────────────────────────────────────────────

    @abstractmethod
    def get_candidate_graph(self, candidate_id: str, depth: int = 1) -> CandidateGraphResponse:
        """Retrieve candidate subgraph up to the specified depth."""
        ...

    # ── Health & Lifecycle ───────────────────────────────────────────────────

    @abstractmethod
    def verify_connectivity(self) -> bool:
        """Check if graph database is reachable."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close client connections cleanly."""
        ...


class InMemoryKnowledgeGraphRepository(KnowledgeGraphRepository):
    """In-memory reference implementation of KnowledgeGraphRepository for testing and offline development."""

    def __init__(self) -> None:
        # Structure: _nodes[label][id] = property_dict
        self._nodes: dict[str, dict[str, dict[str, Any]]] = {
            label: {} for label in ENTITY_LABEL_TO_ID_FIELD
        }
        # List of relationship dicts: {source_id, source_label, rel_type, target_id, target_label, properties}
        self._relationships: list[dict[str, Any]] = []

    def verify_connectivity(self) -> bool:
        return True

    def close(self) -> None:
        pass

    # ── Upserts ──────────────────────────────────────────────────────────────

    def upsert_candidate(self, candidate: Candidate) -> Candidate:
        data = _serialize_dict(candidate.model_dump())
        self._nodes["Candidate"][candidate.candidate_id] = data
        return candidate

    def upsert_interview_round(self, round_data: InterviewRound) -> InterviewRound:
        data = _serialize_dict(round_data.model_dump())
        self._nodes["InterviewRound"][round_data.round_id] = data
        return round_data

    def upsert_question(self, question: Question) -> Question:
        data = _serialize_dict(question.model_dump())
        self._nodes["Question"][question.question_id] = data
        return question

    def upsert_answer(self, answer: Answer) -> Answer:
        data = _serialize_dict(answer.model_dump())
        self._nodes["Answer"][answer.answer_id] = data
        return answer

    def upsert_evidence(self, evidence: Evidence) -> Evidence:
        data = _serialize_dict(evidence.model_dump())
        self._nodes["Evidence"][evidence.evidence_id] = data
        return evidence

    def upsert_competency(self, competency: Competency) -> Competency:
        data = _serialize_dict(competency.model_dump())
        self._nodes["Competency"][competency.competency_id] = data
        return competency

    def upsert_project(self, project: Project) -> Project:
        data = _serialize_dict(project.model_dump())
        self._nodes["Project"][project.project_id] = data
        return project

    def upsert_technology(self, technology: Technology) -> Technology:
        data = _serialize_dict(technology.model_dump())
        self._nodes["Technology"][technology.technology_id] = data
        return technology

    def upsert_skill(self, skill: Skill) -> Skill:
        data = _serialize_dict(skill.model_dump())
        self._nodes["Skill"][skill.skill_id] = data
        return skill

    # ── Relationship Operations ──────────────────────────────────────────────

    def create_relationship(self, relationship: GraphRelationship) -> GraphRelationship:
        # Validate endpoint compatibility
        validate_relationship_compatibility(
            source_label=relationship.source_label,
            target_label=relationship.target_label,
            relationship_type=relationship.relationship_type,
        )

        # Ensure source and target nodes exist
        if not self.get_entity_by_id(relationship.source_label, relationship.source_id):
            raise EntityNotFoundError(
                f"Source node {relationship.source_label} with id '{relationship.source_id}' does not exist"
            )
        if not self.get_entity_by_id(relationship.target_label, relationship.target_id):
            raise EntityNotFoundError(
                f"Target node {relationship.target_label} with id '{relationship.target_id}' does not exist"
            )

        # Avoid duplicate relationships (idempotent write)
        for existing in self._relationships:
            if (
                existing["source_id"] == relationship.source_id
                and existing["source_label"] == relationship.source_label
                and existing["relationship_type"] == relationship.relationship_type.value
                and existing["target_id"] == relationship.target_id
                and existing["target_label"] == relationship.target_label
            ):
                existing["properties"].update(_serialize_dict(relationship.properties))
                return relationship

        self._relationships.append(
            {
                "source_id": relationship.source_id,
                "source_label": relationship.source_label,
                "relationship_type": relationship.relationship_type.value,
                "target_id": relationship.target_id,
                "target_label": relationship.target_label,
                "properties": _serialize_dict(relationship.properties),
            }
        )
        return relationship

    # ── Retrievals ───────────────────────────────────────────────────────────

    def get_candidate(self, candidate_id: str) -> Optional[Candidate]:
        data = self._nodes["Candidate"].get(candidate_id)
        return Candidate(**data) if data else None

    def get_interview_round(self, round_id: str) -> Optional[InterviewRound]:
        data = self._nodes["InterviewRound"].get(round_id)
        return InterviewRound(**data) if data else None

    def get_question(self, question_id: str) -> Optional[Question]:
        data = self._nodes["Question"].get(question_id)
        return Question(**data) if data else None

    def get_answer(self, answer_id: str) -> Optional[Answer]:
        data = self._nodes["Answer"].get(answer_id)
        return Answer(**data) if data else None

    def get_evidence(self, evidence_id: str) -> Optional[Evidence]:
        data = self._nodes["Evidence"].get(evidence_id)
        return Evidence(**data) if data else None

    def get_competency(self, competency_id: str) -> Optional[Competency]:
        data = self._nodes["Competency"].get(competency_id)
        return Competency(**data) if data else None

    def get_project(self, project_id: str) -> Optional[Project]:
        data = self._nodes["Project"].get(project_id)
        return Project(**data) if data else None

    def get_technology(self, technology_id: str) -> Optional[Technology]:
        data = self._nodes["Technology"].get(technology_id)
        return Technology(**data) if data else None

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        data = self._nodes["Skill"].get(skill_id)
        return Skill(**data) if data else None

    def get_entity_by_id(self, label: str, entity_id: str) -> Optional[dict[str, Any]]:
        if label not in self._nodes:
            raise EntityValidationError(f"Invalid entity label '{label}'. Allowed: {list(self._nodes.keys())}")
        return self._nodes[label].get(entity_id)

    # ── Candidate-Scoped Retrieval Operations ────────────────────────────────

    def get_candidate_evidence(
        self,
        candidate_id: str,
        competency: Optional[str] = None,
        round_id: Optional[str] = None,
        source_agent_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[Evidence]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()

        matched: list[Evidence] = []
        for ev_data in self._nodes["Evidence"].values():
            if ev_data.get("candidate_id") != cid:
                continue
            if competency and ev_data.get("competency", "").strip().lower() != competency.strip().lower():
                continue
            if round_id and ev_data.get("round_id") != round_id.strip():
                continue
            if source_agent_id and ev_data.get("source_agent_id", "").strip().lower() != source_agent_id.strip().lower():
                continue
            matched.append(Evidence(**ev_data))

        # Sort by timestamp descending
        matched.sort(key=lambda e: e.timestamp, reverse=True)
        return matched[:limit]

    def get_candidate_competencies(self, candidate_id: str) -> list[Competency]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()

        evidences = self.get_candidate_evidence(cid, limit=1000)
        comp_ids = {e.competency for e in evidences if e.competency}
        result = []
        for comp_id in sorted(comp_ids):
            c_data = self._nodes["Competency"].get(comp_id)
            if c_data:
                result.append(Competency(**c_data))
        return result

    def get_candidate_projects(self, candidate_id: str, limit: int = 10) -> list[Project]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()
        matched = [
            Project(**p) for p in self._nodes["Project"].values()
            if p.get("candidate_id") == cid
        ]
        return matched[:limit]

    def get_candidate_skills(self, candidate_id: str, limit: int = 20) -> list[Skill]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()
        skill_ids: set[str] = set()

        for rel in self._relationships:
            if rel["source_label"] == "Candidate" and rel["source_id"] == cid and rel["relationship_type"] == "HAS_SKILL":
                skill_ids.add(rel["target_id"])

        candidate_project_ids = {
            rel["target_id"] for rel in self._relationships
            if rel["source_label"] == "Candidate" and rel["source_id"] == cid and rel["relationship_type"] == "HAS_PROJECT"
        }
        for rel in self._relationships:
            if rel["source_label"] == "Project" and rel["source_id"] in candidate_project_ids and rel["relationship_type"] == "DEMONSTRATES_SKILL":
                skill_ids.add(rel["target_id"])

        skills = [Skill(**self._nodes["Skill"][sid]) for sid in sorted(skill_ids) if sid in self._nodes["Skill"]]
        return skills[:limit]

    def get_candidate_technologies(self, candidate_id: str, limit: int = 20) -> list[Technology]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()
        tech_ids: set[str] = set()

        for rel in self._relationships:
            if rel["source_label"] == "Candidate" and rel["source_id"] == cid and rel["relationship_type"] == "KNOWS_TECHNOLOGY":
                tech_ids.add(rel["target_id"])

        candidate_project_ids = {
            rel["target_id"] for rel in self._relationships
            if rel["source_label"] == "Candidate" and rel["source_id"] == cid and rel["relationship_type"] == "HAS_PROJECT"
        }
        for rel in self._relationships:
            if rel["source_label"] == "Project" and rel["source_id"] in candidate_project_ids and rel["relationship_type"] == "USES_TECHNOLOGY":
                tech_ids.add(rel["target_id"])

        techs = [Technology(**self._nodes["Technology"][tid]) for tid in sorted(tech_ids) if tid in self._nodes["Technology"]]
        return techs[:limit]

    def get_candidate_interview_rounds(self, candidate_id: str, limit: int = 10) -> list[InterviewRound]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()
        matched = [
            InterviewRound(**r) for r in self._nodes["InterviewRound"].values()
            if r.get("candidate_id") == cid
        ]
        matched.sort(key=lambda r: r.created_at, reverse=True)
        return matched[:limit]

    # ── Graph Query ──────────────────────────────────────────────────────────

    def get_candidate_graph(self, candidate_id: str, depth: int = 1) -> CandidateGraphResponse:
        valid_depth = _validate_depth(depth)
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")

        candidate_data = self.get_candidate(candidate_id.strip())
        if not candidate_data:
            return CandidateGraphResponse(candidate_id=candidate_id, depth=valid_depth, nodes=[], relationships=[])

        visited_nodes: dict[tuple[str, str], dict[str, Any]] = {
            ("Candidate", candidate_id.strip()): _serialize_dict(candidate_data.model_dump())
        }
        collected_relationships: list[dict[str, Any]] = []

        # Queue contains (node_label, node_id, current_depth)
        queue: deque[tuple[str, str, int]] = deque([("Candidate", candidate_id.strip(), 0)])

        while queue:
            curr_label, curr_id, curr_d = queue.popleft()
            if curr_d >= valid_depth:
                continue

            for rel in self._relationships:
                # Outgoing
                if rel["source_label"] == curr_label and rel["source_id"] == curr_id:
                    target_key = (rel["target_label"], rel["target_id"])
                    if rel not in collected_relationships:
                        collected_relationships.append(rel)
                    if target_key not in visited_nodes:
                        target_node = self.get_entity_by_id(rel["target_label"], rel["target_id"])
                        if target_node:
                            visited_nodes[target_key] = target_node
                            queue.append((rel["target_label"], rel["target_id"], curr_d + 1))
                # Incoming
                elif rel["target_label"] == curr_label and rel["target_id"] == curr_id:
                    source_key = (rel["source_label"], rel["source_id"])
                    if rel not in collected_relationships:
                        collected_relationships.append(rel)
                    if source_key not in visited_nodes:
                        source_node = self.get_entity_by_id(rel["source_label"], rel["source_id"])
                        if source_node:
                            visited_nodes[source_key] = source_node
                            queue.append((rel["source_label"], rel["source_id"], curr_d + 1))

        formatted_nodes = [
            {"label": k[0], "id": k[1], "properties": v}
            for k, v in visited_nodes.items()
        ]

        return CandidateGraphResponse(
            candidate_id=candidate_id.strip(),
            depth=valid_depth,
            nodes=formatted_nodes,
            relationships=collected_relationships,
        )
