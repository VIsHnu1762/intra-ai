"""Neo4j AuraDB implementation of KnowledgeGraphRepository."""

from __future__ import annotations

from typing import Any, Optional
import json
import structlog

try:
    from neo4j import Driver, GraphDatabase
    from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable
except ImportError:  # pragma: no cover
    Driver = None  # type: ignore[assignment, misc]
    GraphDatabase = None  # type: ignore[assignment, misc]
    AuthError = Exception  # type: ignore[assignment, misc]
    Neo4jError = Exception  # type: ignore[assignment, misc]
    ServiceUnavailable = Exception  # type: ignore[assignment, misc]

from app.core.config import Settings
from app.knowledge_graph.exceptions import (
    EntityNotFoundError,
    EntityValidationError,
    Neo4jConfigurationError,
    Neo4jConnectionError,
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
from app.knowledge_graph.repository import (
    ENTITY_LABEL_TO_ID_FIELD,
    KnowledgeGraphRepository,
    _serialize_dict as _serialize_generic,
    _validate_depth,
)


def _entity_props(value: Any) -> dict[str, Any]:
    """Convert a Neo4j node mapping back into typed model-friendly values."""
    props = dict(value)
    for key in ("metadata",):
        raw = props.get(key)
        if isinstance(raw, str):
            try:
                props[key] = json.loads(raw)
            except json.JSONDecodeError:
                props[key] = {}
    return props


def _serialize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Serialize nested maps as JSON text because Neo4j properties are flat."""
    import json as _json

    serialized: dict[str, Any] = {}
    for key, value in _serialize_generic(data).items():
        if isinstance(value, dict):
            serialized[key] = _json.dumps(value, default=str, separators=(",", ":"))
        elif isinstance(value, list) and any(isinstance(item, (dict, list)) for item in value):
            serialized[key] = _json.dumps(value, default=str, separators=(",", ":"))
        else:
            serialized[key] = value
    return serialized

logger = structlog.stdlib.get_logger("intra_ai.knowledge_graph.neo4j")


class Neo4jKnowledgeGraphRepository(KnowledgeGraphRepository):
    """Neo4j AuraDB implementation of KnowledgeGraphRepository using official Python driver.

    Enforces strictly parameterized Cypher queries, validates domain labels and
    relationship types, and manages connection lifecycle cleanly.
    """

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
        driver: Optional[Any] = None,
    ) -> None:
        self._uri = uri
        self._username = username
        self._password = password
        self._database = database

        if driver is not None:
            self._driver = driver
        else:
            if GraphDatabase is None:  # pragma: no cover
                raise Neo4jConfigurationError("The neo4j package is not installed.")
            try:
                self._driver = GraphDatabase.driver(
                    self._uri,
                    auth=(self._username, self._password),
                )
            except Exception as exc:
                logger.error("neo4j_driver_creation_failed", error=str(exc))
                raise Neo4jConnectionError(f"Failed to create Neo4j driver: {exc}") from exc

    @classmethod
    def from_settings(
        cls,
        app_settings: Optional[Settings] = None,
        driver: Optional[Any] = None,
    ) -> Neo4jKnowledgeGraphRepository:
        """Instantiate repository using application configuration.

        Raises:
            Neo4jConfigurationError: If any required Neo4j setting is missing.
        """
        if app_settings is None:
            from app.core.config import settings
            app_settings = settings

        uri = (app_settings.NEO4J_URI or "").strip()
        username = (app_settings.NEO4J_USERNAME or "").strip()
        password = (app_settings.NEO4J_PASSWORD or "").strip()
        database = (app_settings.NEO4J_DATABASE or "neo4j").strip()

        missing: list[str] = []
        if not uri:
            missing.append("NEO4J_URI")
        if not username:
            missing.append("NEO4J_USERNAME")
        if not password:
            missing.append("NEO4J_PASSWORD")

        if missing:
            raise Neo4jConfigurationError(
                f"Missing required Neo4j configuration: {', '.join(missing)}. "
                "Please configure them in your environment or backend/.env"
            )

        return cls(
            uri=uri,
            username=username,
            password=password,
            database=database,
            driver=driver,
        )

    # ── Health & Lifecycle ───────────────────────────────────────────────────

    def verify_connectivity(self) -> bool:
        """Verify driver connectivity to Neo4j AuraDB."""
        try:
            self._driver.verify_connectivity()
            return True
        except (AuthError, ServiceUnavailable, Neo4jError, Exception) as exc:
            logger.warning("neo4j_connectivity_failed", error=str(exc))
            return False

    def close(self) -> None:
        """Close Neo4j driver connection cleanly."""
        try:
            self._driver.close()
        except Exception as exc:
            logger.warning("neo4j_driver_close_error", error=str(exc))

    # ── Internal Query Execution Helpers ─────────────────────────────────────

    def _execute_write(self, query: str, parameters: dict[str, Any]) -> Any:
        """Execute parameterized write query within a managed session."""
        try:
            with self._driver.session(database=self._database) as session:
                result = session.run(query, parameters)
                record = result.single()
                return record
        except (AuthError, ServiceUnavailable, Neo4jError) as exc:
            logger.error("neo4j_write_error", error=str(exc), query=query)
            raise Neo4jConnectionError(f"Neo4j write query failed: {exc}") from exc

    def _execute_read_one(self, query: str, parameters: dict[str, Any]) -> Optional[Any]:
        """Execute parameterized read query returning a single record."""
        try:
            with self._driver.session(database=self._database) as session:
                result = session.run(query, parameters)
                return result.single()
        except (AuthError, ServiceUnavailable, Neo4jError) as exc:
            logger.error("neo4j_read_error", error=str(exc), query=query)
            raise Neo4jConnectionError(f"Neo4j read query failed: {exc}") from exc

    def _execute_read_many(self, query: str, parameters: dict[str, Any]) -> list[Any]:
        """Execute parameterized read query returning all records."""
        try:
            with self._driver.session(database=self._database) as session:
                result = session.run(query, parameters)
                return list(result)
        except (AuthError, ServiceUnavailable, Neo4jError) as exc:
            logger.error("neo4j_read_many_error", error=str(exc), query=query)
            raise Neo4jConnectionError(f"Neo4j read many query failed: {exc}") from exc

    # ── Entity Upsert Operations ─────────────────────────────────────────────

    def upsert_candidate(self, candidate: Candidate) -> Candidate:
        query = (
            "MERGE (c:Candidate {candidate_id: $id}) "
            "SET c += $props "
            "RETURN c"
        )
        props = _serialize_dict(candidate.model_dump())
        self._execute_write(query, {"id": candidate.candidate_id, "props": props})
        return candidate

    def upsert_interview_round(self, round_data: InterviewRound) -> InterviewRound:
        query = (
            "MERGE (r:InterviewRound {round_id: $id}) "
            "SET r += $props "
            "RETURN r"
        )
        props = _serialize_dict(round_data.model_dump())
        self._execute_write(query, {"id": round_data.round_id, "props": props})
        return round_data

    def upsert_question(self, question: Question) -> Question:
        query = (
            "MERGE (q:Question {question_id: $id}) "
            "SET q += $props "
            "RETURN q"
        )
        props = _serialize_dict(question.model_dump())
        self._execute_write(query, {"id": question.question_id, "props": props})
        return question

    def upsert_answer(self, answer: Answer) -> Answer:
        query = (
            "MERGE (a:Answer {answer_id: $id}) "
            "SET a += $props "
            "RETURN a"
        )
        props = _serialize_dict(answer.model_dump())
        self._execute_write(query, {"id": answer.answer_id, "props": props})
        return answer

    def upsert_evidence(self, evidence: Evidence) -> Evidence:
        query = (
            "MERGE (e:Evidence {evidence_id: $id}) "
            "SET e += $props "
            "RETURN e"
        )
        props = _serialize_dict(evidence.model_dump())
        self._execute_write(query, {"id": evidence.evidence_id, "props": props})
        return evidence

    def upsert_competency(self, competency: Competency) -> Competency:
        query = (
            "MERGE (c:Competency {competency_id: $id}) "
            "SET c += $props "
            "RETURN c"
        )
        props = _serialize_dict(competency.model_dump())
        self._execute_write(query, {"id": competency.competency_id, "props": props})
        return competency

    def upsert_project(self, project: Project) -> Project:
        query = (
            "MERGE (p:Project {project_id: $id}) "
            "SET p += $props "
            "RETURN p"
        )
        props = _serialize_dict(project.model_dump())
        self._execute_write(query, {"id": project.project_id, "props": props})
        return project

    def upsert_technology(self, technology: Technology) -> Technology:
        query = (
            "MERGE (t:Technology {technology_id: $id}) "
            "SET t += $props "
            "RETURN t"
        )
        props = _serialize_dict(technology.model_dump())
        self._execute_write(query, {"id": technology.technology_id, "props": props})
        return technology

    def upsert_skill(self, skill: Skill) -> Skill:
        query = (
            "MERGE (s:Skill {skill_id: $id}) "
            "SET s += $props "
            "RETURN s"
        )
        props = _serialize_dict(skill.model_dump())
        self._execute_write(query, {"id": skill.skill_id, "props": props})
        return skill

    # ── Relationship Operations ──────────────────────────────────────────────

    def create_relationship(self, relationship: GraphRelationship) -> GraphRelationship:
        # Validate endpoint compatibility
        validate_relationship_compatibility(
            source_label=relationship.source_label,
            target_label=relationship.target_label,
            relationship_type=relationship.relationship_type,
        )

        source_label = relationship.source_label
        target_label = relationship.target_label

        if source_label not in ENTITY_LABEL_TO_ID_FIELD:
            raise EntityValidationError(f"Invalid source label '{source_label}'")
        if target_label not in ENTITY_LABEL_TO_ID_FIELD:
            raise EntityValidationError(f"Invalid target label '{target_label}'")

        source_id_field = ENTITY_LABEL_TO_ID_FIELD[source_label]
        target_id_field = ENTITY_LABEL_TO_ID_FIELD[target_label]
        rel_type = relationship.relationship_type.value

        # First check that both source and target exist
        if not self.get_entity_by_id(source_label, relationship.source_id):
            raise EntityNotFoundError(f"Source node {source_label} '{relationship.source_id}' does not exist")
        if not self.get_entity_by_id(target_label, relationship.target_id):
            raise EntityNotFoundError(f"Target node {target_label} '{relationship.target_id}' does not exist")

        query = (
            f"MATCH (s:{source_label} {{{source_id_field}: $source_id}}) "
            f"MATCH (t:{target_label} {{{target_id_field}: $target_id}}) "
            f"MERGE (s)-[r:{rel_type}]->(t) "
            "SET r += $props "
            "RETURN r"
        )
        props = _serialize_dict(relationship.properties)
        self._execute_write(
            query,
            {
                "source_id": relationship.source_id,
                "target_id": relationship.target_id,
                "props": props,
            },
        )
        return relationship

    # ── Entity Retrieval Operations ──────────────────────────────────────────

    def get_candidate(self, candidate_id: str) -> Optional[Candidate]:
        query = "MATCH (c:Candidate {candidate_id: $id}) RETURN c"
        record = self._execute_read_one(query, {"id": candidate_id})
        if not record or not record.get("c"):
            return None
        return Candidate(**_entity_props(record["c"]))

    def get_interview_round(self, round_id: str) -> Optional[InterviewRound]:
        query = "MATCH (r:InterviewRound {round_id: $id}) RETURN r"
        record = self._execute_read_one(query, {"id": round_id})
        if not record or not record.get("r"):
            return None
        return InterviewRound(**_entity_props(record["r"]))

    def get_question(self, question_id: str) -> Optional[Question]:
        query = "MATCH (q:Question {question_id: $id}) RETURN q"
        record = self._execute_read_one(query, {"id": question_id})
        if not record or not record.get("q"):
            return None
        return Question(**_entity_props(record["q"]))

    def get_answer(self, answer_id: str) -> Optional[Answer]:
        query = "MATCH (a:Answer {answer_id: $id}) RETURN a"
        record = self._execute_read_one(query, {"id": answer_id})
        if not record or not record.get("a"):
            return None
        return Answer(**_entity_props(record["a"]))

    def get_evidence(self, evidence_id: str) -> Optional[Evidence]:
        query = "MATCH (e:Evidence {evidence_id: $id}) RETURN e"
        record = self._execute_read_one(query, {"id": evidence_id})
        if not record or not record.get("e"):
            return None
        return Evidence(**_entity_props(record["e"]))

    def get_competency(self, competency_id: str) -> Optional[Competency]:
        query = "MATCH (c:Competency {competency_id: $id}) RETURN c"
        record = self._execute_read_one(query, {"id": competency_id})
        if not record or not record.get("c"):
            return None
        return Competency(**_entity_props(record["c"]))

    def get_project(self, project_id: str) -> Optional[Project]:
        query = "MATCH (p:Project {project_id: $id}) RETURN p"
        record = self._execute_read_one(query, {"id": project_id})
        if not record or not record.get("p"):
            return None
        return Project(**_entity_props(record["p"]))

    def get_technology(self, technology_id: str) -> Optional[Technology]:
        query = "MATCH (t:Technology {technology_id: $id}) RETURN t"
        record = self._execute_read_one(query, {"id": technology_id})
        if not record or not record.get("t"):
            return None
        return Technology(**_entity_props(record["t"]))

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        query = "MATCH (s:Skill {skill_id: $id}) RETURN s"
        record = self._execute_read_one(query, {"id": skill_id})
        if not record or not record.get("s"):
            return None
        return Skill(**_entity_props(record["s"]))

    def get_entity_by_id(self, label: str, entity_id: str) -> Optional[dict[str, Any]]:
        if label not in ENTITY_LABEL_TO_ID_FIELD:
            raise EntityValidationError(f"Invalid entity label '{label}'. Allowed: {list(ENTITY_LABEL_TO_ID_FIELD.keys())}")
        id_field = ENTITY_LABEL_TO_ID_FIELD[label]
        query = f"MATCH (n:{label} {{{id_field}: $id}}) RETURN n"
        record = self._execute_read_one(query, {"id": entity_id})
        if not record or not record.get("n"):
            return None
        return dict(record["n"])

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

        query = (
            "MATCH (c:Candidate {candidate_id: $candidate_id})-[:HAS_EVIDENCE]->(e:Evidence) "
            "WHERE ($competency IS NULL OR e.competency = $competency) "
            "  AND ($round_id IS NULL OR e.round_id = $round_id) "
            "  AND ($source_agent_id IS NULL OR e.source_agent_id = $source_agent_id) "
            "RETURN e "
            "ORDER BY e.timestamp DESC "
            "LIMIT $limit"
        )
        params = {
            "candidate_id": cid,
            "competency": competency.strip().lower() if competency else None,
            "round_id": round_id.strip() if round_id else None,
            "source_agent_id": source_agent_id.strip().lower() if source_agent_id else None,
            "limit": int(limit),
        }
        records = self._execute_read_many(query, params)
        return [Evidence(**_entity_props(rec["e"])) for rec in records if rec.get("e")]

    def get_candidate_competencies(self, candidate_id: str) -> list[Competency]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()

        query = (
            "MATCH (c:Candidate {candidate_id: $candidate_id})-[:HAS_EVIDENCE]->(:Evidence)-[:SUPPORTS_COMPETENCY]->(comp:Competency) "
            "RETURN DISTINCT comp"
        )
        records = self._execute_read_many(query, {"candidate_id": cid})
        return [Competency(**_entity_props(rec["comp"])) for rec in records if rec.get("comp")]

    def get_candidate_projects(self, candidate_id: str, limit: int = 10) -> list[Project]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()

        query = (
            "MATCH (c:Candidate {candidate_id: $candidate_id})-[:HAS_PROJECT]->(p:Project) "
            "RETURN p "
            "LIMIT $limit"
        )
        records = self._execute_read_many(query, {"candidate_id": cid, "limit": int(limit)})
        return [Project(**_entity_props(rec["p"])) for rec in records if rec.get("p")]

    def get_candidate_skills(self, candidate_id: str, limit: int = 20) -> list[Skill]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()

        query = (
            "MATCH (c:Candidate {candidate_id: $candidate_id}) "
            "OPTIONAL MATCH (c)-[:HAS_SKILL]->(s1:Skill) "
            "OPTIONAL MATCH (c)-[:HAS_PROJECT]->(:Project)-[:DEMONSTRATES_SKILL]->(s2:Skill) "
            "WITH [s IN collect(DISTINCT s1) + collect(DISTINCT s2) WHERE s IS NOT NULL] AS all_skills "
            "UNWIND all_skills AS s "
            "RETURN DISTINCT s "
            "LIMIT $limit"
        )
        records = self._execute_read_many(query, {"candidate_id": cid, "limit": int(limit)})
        return [Skill(**_entity_props(rec["s"])) for rec in records if rec.get("s")]

    def get_candidate_technologies(self, candidate_id: str, limit: int = 20) -> list[Technology]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()

        query = (
            "MATCH (c:Candidate {candidate_id: $candidate_id}) "
            "OPTIONAL MATCH (c)-[:KNOWS_TECHNOLOGY]->(t1:Technology) "
            "OPTIONAL MATCH (c)-[:HAS_PROJECT]->(:Project)-[:USES_TECHNOLOGY]->(t2:Technology) "
            "WITH [t IN collect(DISTINCT t1) + collect(DISTINCT t2) WHERE t IS NOT NULL] AS all_techs "
            "UNWIND all_techs AS t "
            "RETURN DISTINCT t "
            "LIMIT $limit"
        )
        records = self._execute_read_many(query, {"candidate_id": cid, "limit": int(limit)})
        return [Technology(**_entity_props(rec["t"])) for rec in records if rec.get("t")]

    def get_candidate_interview_rounds(self, candidate_id: str, limit: int = 10) -> list[InterviewRound]:
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")
        cid = candidate_id.strip()

        query = (
            "MATCH (c:Candidate {candidate_id: $candidate_id})-[:PARTICIPATED_IN]->(r:InterviewRound) "
            "RETURN r "
            "ORDER BY r.created_at DESC "
            "LIMIT $limit"
        )
        records = self._execute_read_many(query, {"candidate_id": cid, "limit": int(limit)})
        return [InterviewRound(**_entity_props(rec["r"])) for rec in records if rec.get("r")]

    # ── Candidate Graph Retrieval ────────────────────────────────────────────

    def get_candidate_graph(self, candidate_id: str, depth: int = 1) -> CandidateGraphResponse:
        valid_depth = _validate_depth(depth)
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string")

        candidate_id = candidate_id.strip()

        # Check candidate existence
        candidate_dict = self.get_entity_by_id("Candidate", candidate_id)
        if not candidate_dict:
            return CandidateGraphResponse(
                candidate_id=candidate_id,
                depth=valid_depth,
                nodes=[],
                relationships=[],
            )

        query = (
            "MATCH (c:Candidate {candidate_id: $candidate_id}) "
            f"OPTIONAL MATCH path = (c)-[*1..{valid_depth}]-(m) "
            "WITH c, [p IN collect(path) WHERE p IS NOT NULL] AS valid_paths "
            "RETURN c, valid_paths"
        )

        record = self._execute_read_one(query, {"candidate_id": candidate_id})
        if not record:
            return CandidateGraphResponse(candidate_id=candidate_id, depth=valid_depth, nodes=[], relationships=[])

        nodes_map: dict[tuple[str, str], dict[str, Any]] = {
            ("Candidate", candidate_id): candidate_dict
        }
        collected_relationships: list[dict[str, Any]] = []

        valid_paths = record.get("valid_paths", [])
        for path in valid_paths:
            # path is a neo4j.graph.Path or mock object with nodes and relationships
            for node in getattr(path, "nodes", []):
                labels = list(getattr(node, "labels", ["Unknown"]))
                label = labels[0] if labels else "Unknown"
                id_field = ENTITY_LABEL_TO_ID_FIELD.get(label, "id")
                props = dict(node)
                node_id = props.get(id_field, str(getattr(node, "element_id", "")))
                nodes_map[(label, str(node_id))] = props

            for rel in getattr(path, "relationships", []):
                rel_type = getattr(rel, "type", "RELATED_TO")
                rel_props = dict(rel)
                start_node = getattr(rel, "start_node", None)
                end_node = getattr(rel, "end_node", None)

                start_labels = list(getattr(start_node, "labels", ["Unknown"])) if start_node else ["Unknown"]
                start_label = start_labels[0] if start_labels else "Unknown"
                start_id_field = ENTITY_LABEL_TO_ID_FIELD.get(start_label, "id")
                start_id = dict(start_node).get(start_id_field, "") if start_node else ""

                end_labels = list(getattr(end_node, "labels", ["Unknown"])) if end_node else ["Unknown"]
                end_label = end_labels[0] if end_labels else "Unknown"
                end_id_field = ENTITY_LABEL_TO_ID_FIELD.get(end_label, "id")
                end_id = dict(end_node).get(end_id_field, "") if end_node else ""

                rel_dict = {
                    "source_id": str(start_id),
                    "source_label": start_label,
                    "relationship_type": rel_type,
                    "target_id": str(end_id),
                    "target_label": end_label,
                    "properties": rel_props,
                }
                if rel_dict not in collected_relationships:
                    collected_relationships.append(rel_dict)

        formatted_nodes = [
            {"label": k[0], "id": k[1], "properties": v}
            for k, v in nodes_map.items()
        ]

        return CandidateGraphResponse(
            candidate_id=candidate_id,
            depth=valid_depth,
            nodes=formatted_nodes,
            relationships=collected_relationships,
        )
