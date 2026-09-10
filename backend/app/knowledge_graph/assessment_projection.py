"""New assessment sources in the existing graph, isolated from INTERVIEW_EVIDENCE reads."""
from app.knowledge_graph.neo4j_repository import Neo4jKnowledgeGraphRepository


class AssessmentEvidenceProjection(Neo4jKnowledgeGraphRepository):
    """Reuse Neo4j connection/query infrastructure without changing legacy models."""

    def initialize(self):
        for label, field in [("AssessmentSession", "session_id"), ("AssessmentEvent", "event_id"), ("AssessmentEvidence", "evidence_id")]:
            self._execute_write(f"CREATE CONSTRAINT {label.lower()}_identity IF NOT EXISTS FOR (n:{label}) REQUIRE n.{field} IS UNIQUE", {})

    def project(self, evidence, *, owner_id, tenant_key, source_text):
        props = evidence.model_dump(mode="json")
        self._execute_write("""
         MERGE (c:Candidate {candidate_id:$candidate_id})
         MERGE (s:AssessmentSession {session_id:$session_id})
         SET s.source_type=$source_type,s.owner_id=$owner_id,s.tenant_key=$tenant_key
         MERGE (t:AssessmentEvent {event_id:$event_id})
         SET t.session_id=$session_id,t.candidate_id=$candidate_id,t.source_text=$source_text,t.observed_at=$observed_at
         MERGE (e:AssessmentEvidence {evidence_id:$id})
         SET e += $props
         SET e.owner_id=$owner_id,e.tenant_key=$tenant_key
         MERGE (k:Competency {competency_id:$competency})
         ON CREATE SET k.name=$competency,k.category='behavioral'
         MERGE (c)-[:PARTICIPATED_IN_ASSESSMENT]->(s)
         MERGE (s)-[:HAS_ASSESSMENT_EVENT]->(t)
         MERGE (c)-[:HAS_ASSESSMENT_EVIDENCE]->(e)
         MERGE (t)-[:SUPPORTED_BY]->(e)
         MERGE (e)-[:SUPPORTS_COMPETENCY]->(k)
         RETURN e.evidence_id AS id
        """, {**props,"props":props,"owner_id":owner_id,"tenant_key":tenant_key,"source_text":source_text})

    def candidate_memory(self, *, candidate_id, owner_id, tenant_key, limit=12):
        limit=max(1,min(20,limit))
        with self._driver.session(database=self._database) as session:
            return [dict(row["e"]) for row in session.run("""
             MATCH (c:Candidate {candidate_id:$candidate_id})-[:HAS_ASSESSMENT_EVIDENCE]->(e:AssessmentEvidence)
             WHERE e.owner_id=$owner_id AND e.tenant_key=$tenant_key
             RETURN e ORDER BY e.observed_at DESC,e.evidence_id LIMIT $limit
            """,candidate_id=candidate_id,owner_id=owner_id,tenant_key=tenant_key,limit=limit)]
