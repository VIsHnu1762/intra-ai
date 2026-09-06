"""Candidate Memory Retrieval Service for reading persistent candidate knowledge from the Knowledge Graph."""

from __future__ import annotations

import asyncio
from typing import Any, Optional
import structlog

from app.knowledge_graph.exceptions import EntityValidationError, KnowledgeGraphError
from app.knowledge_graph.memory_models import (
    CompetencySummary,
    InterviewHistorySummary,
    MemorySourceType,
    PersistentCandidateMemory,
    ProjectSummary,
    RetrievedEvidence,
)
from app.knowledge_graph.models import Competency, Evidence, InterviewRound, Project, Skill, Technology
from app.knowledge_graph.repository import KnowledgeGraphRepository
from app.knowledge_graph.service import normalize_competency_id

logger = structlog.stdlib.get_logger("intra_ai.knowledge_graph.memory_service")

# Explicit contextual retrieval limits to prevent unbounded context growth
DEFAULT_MAX_EVIDENCE: int = 20
DEFAULT_MAX_PROJECTS: int = 10
DEFAULT_MAX_SKILLS: int = 20
DEFAULT_MAX_TECHNOLOGIES: int = 20
DEFAULT_MAX_ROUNDS: int = 10


class CandidateMemoryService:
    """Read-only service for retrieving structured persistent candidate memory from the Knowledge Graph.

    Guarantees:
    - Strictly read-only: Never mutates, creates, or deletes graph elements.
    - Candidate scoped: Strict tenant isolation keyed by candidate_id.
    - Cross-agent & cross-round: Unifies observations across interviewer personas and rounds.
    - Deterministic relevance filtering: Filter by competency, round, or source agent without LLM rewrite.
    - Provenance retention: Every evidence item preserves origin, source agent, and timestamp.
    """

    def __init__(self, repository: Optional[KnowledgeGraphRepository] = None) -> None:
        if repository is not None:
            self._repository: Optional[KnowledgeGraphRepository] = repository
        else:
            try:
                from app.knowledge_graph.neo4j_repository import Neo4jKnowledgeGraphRepository
                self._repository = Neo4jKnowledgeGraphRepository.from_settings()
                logger.info("candidate_memory_service_initialized_with_neo4j")
            except Exception as exc:
                logger.info("candidate_memory_service_disabled_no_config", reason=str(exc))
                self._repository = None

    @property
    def repository(self) -> Optional[KnowledgeGraphRepository]:
        return self._repository

    def get_candidate_memory(
        self,
        candidate_id: str,
        competency: Optional[str] = None,
        round_id: Optional[str] = None,
        source_agent_id: Optional[str] = None,
        max_evidence: int = DEFAULT_MAX_EVIDENCE,
        max_projects: int = DEFAULT_MAX_PROJECTS,
        max_skills: int = DEFAULT_MAX_SKILLS,
        max_technologies: int = DEFAULT_MAX_TECHNOLOGIES,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> PersistentCandidateMemory:
        """Retrieve structured persistent candidate memory from the Knowledge Graph.

        Args:
            candidate_id: Authoritative candidate identifier.
            competency: Optional filter targeting a specific competency (e.g. 'system_design').
            round_id: Optional filter targeting a specific interview round.
            source_agent_id: Optional filter targeting evidence elicited by a specific agent.
            max_evidence: Maximum evidence items to return.
            max_projects: Maximum projects to return.
            max_skills: Maximum skills to return.
            max_technologies: Maximum technologies to return.
            max_rounds: Maximum interview rounds to return.

        Returns:
            PersistentCandidateMemory object containing typed graph projections.
        """
        if not candidate_id or not candidate_id.strip():
            raise EntityValidationError("candidate_id must be a non-empty string for memory retrieval")

        cid = candidate_id.strip()

        if not self._repository:
            logger.debug("candidate_memory_retrieval_skipped_no_repository", candidate_id=cid)
            return PersistentCandidateMemory(candidate_id=cid)

        # Normalize optional competency filter
        norm_competency = normalize_competency_id(competency) if competency and competency.strip() else None

        filter_applied = {
            "competency": norm_competency,
            "round_id": round_id.strip() if round_id else None,
            "source_agent_id": source_agent_id.strip().lower() if source_agent_id else None,
            "limits": {
                "max_evidence": max_evidence,
                "max_projects": max_projects,
                "max_skills": max_skills,
                "max_technologies": max_technologies,
                "max_rounds": max_rounds,
            },
        }

        try:
            # 1. Fetch Candidate Node
            candidate = self._repository.get_candidate(cid)
            if not candidate:
                logger.info("candidate_not_found_in_graph", candidate_id=cid)
                return PersistentCandidateMemory(
                    candidate_id=cid,
                    filter_applied=filter_applied,
                )

            # 2. Fetch Evidence with Provenance
            raw_evidence = self._repository.get_candidate_evidence(
                candidate_id=cid,
                competency=norm_competency,
                round_id=round_id.strip() if round_id else None,
                source_agent_id=source_agent_id.strip().lower() if source_agent_id else None,
                limit=max_evidence,
            )

            retrieved_evidence: list[RetrievedEvidence] = []
            source_agents: set[str] = set()
            source_rounds: set[str] = set()

            for ev in raw_evidence:
                retrieved_evidence.append(
                    RetrievedEvidence(
                        evidence_id=ev.evidence_id,
                        answer_id=ev.answer_id,
                        candidate_id=ev.candidate_id,
                        round_id=ev.round_id,
                        source_agent_id=ev.source_agent_id,
                        competency=ev.competency,
                        signal=ev.signal,
                        score=ev.score,
                        timestamp=ev.timestamp,
                        source_type=MemorySourceType.INTERVIEW_EVIDENCE,
                        metadata=ev.metadata,
                    )
                )
                if ev.source_agent_id:
                    source_agents.add(ev.source_agent_id)
                if ev.round_id:
                    source_rounds.add(ev.round_id)

            # 3. Aggregate Competency Summaries
            competency_map: dict[str, list[RetrievedEvidence]] = {}
            for ev_item in retrieved_evidence:
                competency_map.setdefault(ev_item.competency, []).append(ev_item)

            competency_summaries: list[CompetencySummary] = []
            for comp_id, ev_list in sorted(competency_map.items()):
                scores = [e.score for e in ev_list if e.score is not None]
                avg_score = round(sum(scores) / len(scores), 2) if scores else None
                competency_summaries.append(
                    CompetencySummary(
                        competency_id=comp_id,
                        name=comp_id.replace("_", " ").title(),
                        evidence_count=len(ev_list),
                        evidence_ids=[e.evidence_id for e in ev_list],
                        average_score=avg_score,
                        assessments=[e.signal for e in ev_list[:3]],
                    )
                )

            # 4. Fetch Projects
            raw_projects = self._repository.get_candidate_projects(cid, limit=max_projects)
            project_summaries: list[ProjectSummary] = []
            for p in raw_projects:
                project_summaries.append(
                    ProjectSummary(
                        project_id=p.project_id,
                        name=p.name,
                        description=p.description,
                        technologies=p.metadata.get("technologies", []),
                        skills=p.metadata.get("skills", []),
                    )
                )

            # 5. Fetch Skills & Technologies
            raw_skills = self._repository.get_candidate_skills(cid, limit=max_skills)
            skills = [s.name for s in raw_skills]

            raw_techs = self._repository.get_candidate_technologies(cid, limit=max_technologies)
            technologies = [t.name for t in raw_techs]

            # 6. Fetch Interview Round History
            raw_rounds = self._repository.get_candidate_interview_rounds(cid, limit=max_rounds)
            round_summaries: list[InterviewHistorySummary] = []
            for r in raw_rounds:
                source_rounds.add(r.round_id)
                round_summaries.append(
                    InterviewHistorySummary(
                        round_id=r.round_id,
                        interview_id=r.interview_id,
                        round_type=r.round_type,
                        status=r.status,
                    )
                )

            memory = PersistentCandidateMemory(
                candidate_id=cid,
                name=candidate.name,
                email=candidate.email,
                filter_applied=filter_applied,
                evidence=retrieved_evidence,
                competencies=competency_summaries,
                projects=project_summaries,
                skills=skills,
                technologies=technologies,
                interview_rounds=round_summaries,
                total_evidence_count=len(retrieved_evidence),
                source_agents=sorted(list(source_agents)),
                source_rounds=sorted(list(source_rounds)),
            )

            logger.info(
                "candidate_memory_retrieved",
                candidate_id=cid,
                evidence_count=len(retrieved_evidence),
                competencies_count=len(competency_summaries),
                projects_count=len(project_summaries),
            )

            return memory

        except Exception as exc:
            logger.error("candidate_memory_retrieval_failed", error=str(exc), candidate_id=cid)
            raise KnowledgeGraphError(f"Failed to retrieve candidate memory: {exc}") from exc

    async def get_candidate_memory_async(
        self,
        candidate_id: str,
        competency: Optional[str] = None,
        round_id: Optional[str] = None,
        source_agent_id: Optional[str] = None,
        max_evidence: int = DEFAULT_MAX_EVIDENCE,
        max_projects: int = DEFAULT_MAX_PROJECTS,
        max_skills: int = DEFAULT_MAX_SKILLS,
        max_technologies: int = DEFAULT_MAX_TECHNOLOGIES,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> PersistentCandidateMemory:
        """Asynchronously retrieve candidate memory in a worker thread.

        Prevents blocking the asyncio event loop during graph queries.
        """
        return await asyncio.to_thread(
            self.get_candidate_memory,
            candidate_id=candidate_id,
            competency=competency,
            round_id=round_id,
            source_agent_id=source_agent_id,
            max_evidence=max_evidence,
            max_projects=max_projects,
            max_skills=max_skills,
            max_technologies=max_technologies,
            max_rounds=max_rounds,
        )
