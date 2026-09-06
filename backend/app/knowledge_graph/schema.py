"""Neo4j schema, uniqueness constraints, and index definitions for Intra AI Knowledge Graph."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.stdlib.get_logger("intra_ai.knowledge_graph.schema")

# ── Idempotent Constraint Definitions ────────────────────────────────────────

CONSTRAINTS: list[str] = [
    "CREATE CONSTRAINT candidate_id_unique IF NOT EXISTS FOR (c:Candidate) REQUIRE c.candidate_id IS UNIQUE",
    "CREATE CONSTRAINT round_id_unique IF NOT EXISTS FOR (r:InterviewRound) REQUIRE r.round_id IS UNIQUE",
    "CREATE CONSTRAINT question_id_unique IF NOT EXISTS FOR (q:Question) REQUIRE q.question_id IS UNIQUE",
    "CREATE CONSTRAINT answer_id_unique IF NOT EXISTS FOR (a:Answer) REQUIRE a.answer_id IS UNIQUE",
    "CREATE CONSTRAINT evidence_id_unique IF NOT EXISTS FOR (e:Evidence) REQUIRE e.evidence_id IS UNIQUE",
    "CREATE CONSTRAINT competency_id_unique IF NOT EXISTS FOR (c:Competency) REQUIRE c.competency_id IS UNIQUE",
    "CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.project_id IS UNIQUE",
    "CREATE CONSTRAINT technology_id_unique IF NOT EXISTS FOR (t:Technology) REQUIRE t.technology_id IS UNIQUE",
    "CREATE CONSTRAINT skill_id_unique IF NOT EXISTS FOR (s:Skill) REQUIRE s.skill_id IS UNIQUE",
]

# ── Idempotent Lookup Index Definitions ──────────────────────────────────────

INDEXES: list[str] = [
    "CREATE INDEX candidate_email_idx IF NOT EXISTS FOR (c:Candidate) ON (c.email)",
    "CREATE INDEX round_interview_id_idx IF NOT EXISTS FOR (r:InterviewRound) ON (r.interview_id)",
    "CREATE INDEX round_candidate_id_idx IF NOT EXISTS FOR (r:InterviewRound) ON (r.candidate_id)",
    "CREATE INDEX question_round_id_idx IF NOT EXISTS FOR (q:Question) ON (q.round_id)",
    "CREATE INDEX question_agent_id_idx IF NOT EXISTS FOR (q:Question) ON (q.agent_id)",
    "CREATE INDEX answer_question_id_idx IF NOT EXISTS FOR (a:Answer) ON (a.question_id)",
    "CREATE INDEX answer_candidate_id_idx IF NOT EXISTS FOR (a:Answer) ON (a.candidate_id)",
    "CREATE INDEX evidence_answer_id_idx IF NOT EXISTS FOR (e:Evidence) ON (e.answer_id)",
    "CREATE INDEX evidence_candidate_id_idx IF NOT EXISTS FOR (e:Evidence) ON (e.candidate_id)",
    "CREATE INDEX evidence_source_agent_idx IF NOT EXISTS FOR (e:Evidence) ON (e.source_agent_id)",
    "CREATE INDEX evidence_competency_idx IF NOT EXISTS FOR (e:Evidence) ON (e.competency)",
    "CREATE INDEX project_candidate_id_idx IF NOT EXISTS FOR (p:Project) ON (p.candidate_id)",
]

ALL_SCHEMA_STATEMENTS: list[str] = CONSTRAINTS + INDEXES


def initialize_neo4j_schema(driver: Any, database: str = "neo4j") -> list[str]:
    """Execute all uniqueness constraints and indexes idempotently against Neo4j.

    Args:
        driver: A connected Neo4j Driver instance (neo4j.Driver).
        database: Target Neo4j database name (default: "neo4j").

    Returns:
        list of executed statement strings.
    """
    executed: list[str] = []
    logger.info("initializing_neo4j_schema_start", database=database, total_statements=len(ALL_SCHEMA_STATEMENTS))

    with driver.session(database=database) as session:
        for stmt in ALL_SCHEMA_STATEMENTS:
            try:
                session.run(stmt).consume()
                executed.append(stmt)
            except Exception as exc:
                logger.error("schema_statement_failed", statement=stmt, error=str(exc))
                raise

    logger.info("initializing_neo4j_schema_complete", executed_count=len(executed))
    return executed
