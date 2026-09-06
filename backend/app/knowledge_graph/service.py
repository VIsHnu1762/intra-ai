"""Service layer for persisting M1 Interview Intelligence evaluations into the Knowledge Graph."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Optional
from pydantic import BaseModel, Field
import structlog

from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis
from app.knowledge_graph.exceptions import KnowledgeGraphError
from app.knowledge_graph.models import (
    Answer,
    Candidate,
    Competency,
    Evidence,
    GraphRelationship,
    GraphRelationshipType,
    InterviewRound,
    Question,
)
from app.knowledge_graph.repository import KnowledgeGraphRepository
from app.models.enums import DifficultyLevel

logger = structlog.stdlib.get_logger("intra_ai.knowledge_graph.service")

_REPOSITORY_UNSET = object()


# ── Canonical Normalization & Identity Helpers ───────────────────────────────


def normalize_competency_id(competency: str) -> str:
    """Normalize competency name to stable lower_snake_case identifier.

    Examples:
        'System Design' -> 'system_design'
        'SYSTEM_DESIGN' -> 'system_design'
        'distributed-caching' -> 'distributed_caching'
    """
    if not competency or not competency.strip():
        return "general"
    norm = competency.strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in norm:
        norm = norm.replace("__", "_")
    return norm.strip("_") or "general"


def derive_round_id(interview_id: str, round_id_or_name: str) -> str:
    """Deterministically derive a unique round_id scoped to the interview session."""
    clean_round = (round_id_or_name or "technical").strip()
    clean_interview = interview_id.strip()
    if clean_round.startswith(clean_interview):
        return clean_round
    return f"{clean_interview}_{clean_round}"


def derive_question_id(round_id: str, question_text: str, question_id: Optional[str] = None) -> str:
    """Deterministically derive a stable question_id from round and question content."""
    if question_id and question_id.strip():
        return question_id.strip()
    clean_text = question_text.strip().lower()
    text_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:12]
    return f"{round_id}_q_{text_hash}"


# ── Persistence Result Model ─────────────────────────────────────────────────


class KnowledgeGraphPersistenceResult(BaseModel):
    """Result summary of a Knowledge Graph turn evaluation persistence."""

    success: bool
    candidate_id: str
    round_id: str
    question_id: str
    answer_id: str
    evidence_count: int = 0
    competencies_persisted: list[str] = Field(default_factory=list)
    relationships_created: int = 0
    error: Optional[str] = None


# ── Knowledge Graph Persistence Service ──────────────────────────────────────


class KnowledgeGraphPersistenceService:
    """Persists evaluated M1 interview turns into the Knowledge Graph.

    Responsibilities:
    - Map M1 AnswerAnalysis + InterviewAIContext into typed Knowledge Graph domain entities.
    - Guarantee idempotent writes for Candidate, InterviewRound, Question, Answer, Evidence, and Competencies.
    - Connect entities with canonical relationships preserving strict provenance.
    - Decouple M1 and Meta-Orchestrator from direct Neo4j dependencies.
    """

    def __init__(
        self,
        repository: Optional[KnowledgeGraphRepository] | object = _REPOSITORY_UNSET,
    ) -> None:
        # Omitted repository means "use configured Neo4j". Passing None is an
        # explicit opt-out used by offline callers and keeps disabled mode from
        # accidentally writing to a live graph.
        if repository is None:
            self._repository = None
        elif repository is not _REPOSITORY_UNSET:
            self._repository = repository  # type: ignore[assignment]
        else:
            try:
                from app.knowledge_graph.neo4j_repository import Neo4jKnowledgeGraphRepository
                self._repository = Neo4jKnowledgeGraphRepository.from_settings()
                logger.info("kg_persistence_service_initialized_with_neo4j")
            except Exception as exc:
                logger.info("kg_persistence_disabled_no_config", reason=str(exc))
                self._repository = None

    @property
    def repository(self) -> Optional[KnowledgeGraphRepository]:
        return self._repository

    def persist_turn_evaluation(
        self,
        analysis: AnswerAnalysis,
        context: InterviewAIContext,
        question_text: str,
        answer_text: str,
        agent_id: str,
        difficulty: Optional[DifficultyLevel | str] = None,
        question_id: Optional[str] = None,
    ) -> KnowledgeGraphPersistenceResult:
        """Synchronously persist a complete evaluated turn into the Knowledge Graph.

        Args:
            analysis: Authoritative M1 AnswerAnalysis result.
            context: Current short-term InterviewAIContext.
            question_text: Text of the question that prompted the answer.
            answer_text: Transcribed candidate answer text.
            agent_id: Active interviewer agent ID (e.g. 'alex', 'jordan').
            difficulty: Optional difficulty level of the question.
            question_id: Optional explicit question ID.

        Returns:
            KnowledgeGraphPersistenceResult summarizing the created/upserted graph elements.
        """
        if not self._repository:
            logger.debug("kg_persistence_skipped_no_repository")
            return KnowledgeGraphPersistenceResult(
                success=False,
                candidate_id=context.candidate_id,
                round_id=context.current_round_id,
                question_id=question_id or "unknown",
                answer_id=analysis.answer_id,
                error="repository_not_configured",
            )

        try:
            relationships_created = 0

            # 1. Upsert Candidate Node
            candidate = Candidate(
                candidate_id=context.candidate_id,
                name=context.metadata.get("candidate_name") or context.metadata.get("name"),
                email=context.metadata.get("candidate_email") or context.metadata.get("email"),
            )
            self._repository.upsert_candidate(candidate)

            # 2. Upsert InterviewRound Node
            round_id = derive_round_id(context.interview_id, context.current_round_id)
            round_data = InterviewRound(
                round_id=round_id,
                interview_id=context.interview_id,
                candidate_id=context.candidate_id,
                round_type=context.current_round_id or "technical",
                status="active",
            )
            self._repository.upsert_interview_round(round_data)

            # Rel: Candidate -[:PARTICIPATED_IN]-> InterviewRound
            self._repository.create_relationship(
                GraphRelationship(
                    source_id=candidate.candidate_id,
                    source_label="Candidate",
                    target_id=round_id,
                    target_label="InterviewRound",
                    relationship_type=GraphRelationshipType.PARTICIPATED_IN,
                )
            )
            relationships_created += 1

            # 3. Upsert Question Node
            q_id = derive_question_id(round_id, question_text, question_id=question_id)
            q_comp = normalize_competency_id(
                context.metadata.get("active_competency")
                or (analysis.competency_findings[0].competency_id if analysis.competency_findings else "general")
            )
            q_diff = str(
                difficulty.value if hasattr(difficulty, "value")
                else (difficulty or (context.difficulty.value if hasattr(context.difficulty, "value") else "medium"))
            )

            question = Question(
                question_id=q_id,
                round_id=round_id,
                agent_id=agent_id.strip().lower(),
                competency=q_comp,
                question_text=question_text.strip(),
                difficulty=q_diff,
            )
            self._repository.upsert_question(question)

            # Rel: InterviewRound -[:HAS_QUESTION]-> Question
            self._repository.create_relationship(
                GraphRelationship(
                    source_id=round_id,
                    source_label="InterviewRound",
                    target_id=q_id,
                    target_label="Question",
                    relationship_type=GraphRelationshipType.HAS_QUESTION,
                )
            )
            relationships_created += 1

            # 4. Upsert Answer Node
            answer = Answer(
                answer_id=analysis.answer_id,
                question_id=q_id,
                candidate_id=context.candidate_id,
                round_id=round_id,
                answer_text=answer_text.strip(),
                duration_seconds=int(context.metadata.get("turn_duration_seconds", 0)),
                metadata={
                    "agent_id": agent_id.strip().lower(),
                    "overall_performance": analysis.overall_performance,
                    "confidence": analysis.confidence,
                    "vague": analysis.vague,
                    "contradiction_detected": analysis.contradiction_detected,
                },
            )
            self._repository.upsert_answer(answer)

            # Rel: InterviewRound -[:HAS_ANSWER]-> Answer
            self._repository.create_relationship(
                GraphRelationship(
                    source_id=round_id,
                    source_label="InterviewRound",
                    target_id=analysis.answer_id,
                    target_label="Answer",
                    relationship_type=GraphRelationshipType.HAS_ANSWER,
                )
            )
            relationships_created += 1

            # Rel: Question -[:HAS_ANSWER]-> Answer
            self._repository.create_relationship(
                GraphRelationship(
                    source_id=q_id,
                    source_label="Question",
                    target_id=analysis.answer_id,
                    target_label="Answer",
                    relationship_type=GraphRelationshipType.HAS_ANSWER,
                )
            )
            relationships_created += 1

            # 5. Persist Competencies & Relationships
            persisted_competencies: set[str] = set()

            if q_comp:
                persisted_competencies.add(q_comp)
                self._repository.upsert_competency(
                    Competency(
                        competency_id=q_comp,
                        name=q_comp.replace("_", " ").title(),
                    )
                )
                self._repository.create_relationship(
                    GraphRelationship(
                        source_id=q_id,
                        source_label="Question",
                        target_id=q_comp,
                        target_label="Competency",
                        relationship_type=GraphRelationshipType.TARGETS_COMPETENCY,
                    )
                )
                relationships_created += 1

            for finding in analysis.competency_findings:
                f_comp = normalize_competency_id(finding.competency_id)
                persisted_competencies.add(f_comp)
                self._repository.upsert_competency(
                    Competency(
                        competency_id=f_comp,
                        name=f_comp.replace("_", " ").title(),
                        metadata={"assessment": finding.assessment, "confidence": finding.confidence},
                    )
                )

            # 6. Persist Evidence Nodes with Strict Provenance
            persisted_evidence_count = 0
            for ev in analysis.evidence:
                ev_comp = normalize_competency_id(ev.competency or "general")
                persisted_competencies.add(ev_comp)
                self._repository.upsert_competency(
                    Competency(
                        competency_id=ev_comp,
                        name=ev_comp.replace("_", " ").title(),
                    )
                )

                evidence_node = Evidence(
                    evidence_id=ev.id,
                    answer_id=analysis.answer_id,
                    candidate_id=context.candidate_id,
                    round_id=round_id,
                    source_agent_id=(ev.source_agent_id or agent_id).strip().lower(),
                    competency=ev_comp,
                    signal=ev.signal.strip(),
                    score=ev.score,
                    timestamp=ev.timestamp,
                    metadata=ev.metadata or {},
                )
                self._repository.upsert_evidence(evidence_node)
                persisted_evidence_count += 1

                # Rel: Answer -[:SUPPORTED_BY]-> Evidence
                self._repository.create_relationship(
                    GraphRelationship(
                        source_id=analysis.answer_id,
                        source_label="Answer",
                        target_id=ev.id,
                        target_label="Evidence",
                        relationship_type=GraphRelationshipType.SUPPORTED_BY,
                    )
                )
                relationships_created += 1

                # Rel: Evidence -[:SUPPORTS_COMPETENCY]-> Competency
                self._repository.create_relationship(
                    GraphRelationship(
                        source_id=ev.id,
                        source_label="Evidence",
                        target_id=ev_comp,
                        target_label="Competency",
                        relationship_type=GraphRelationshipType.SUPPORTS_COMPETENCY,
                    )
                )
                relationships_created += 1

                # Rel: Candidate -[:HAS_EVIDENCE]-> Evidence
                self._repository.create_relationship(
                    GraphRelationship(
                        source_id=context.candidate_id,
                        source_label="Candidate",
                        target_id=ev.id,
                        target_label="Evidence",
                        relationship_type=GraphRelationshipType.HAS_EVIDENCE,
                    )
                )
                relationships_created += 1

            logger.info(
                "kg_turn_persisted_successfully",
                candidate_id=context.candidate_id,
                round_id=round_id,
                question_id=q_id,
                answer_id=analysis.answer_id,
                evidence_count=persisted_evidence_count,
                relationships_created=relationships_created,
            )

            return KnowledgeGraphPersistenceResult(
                success=True,
                candidate_id=context.candidate_id,
                round_id=round_id,
                question_id=q_id,
                answer_id=analysis.answer_id,
                evidence_count=persisted_evidence_count,
                competencies_persisted=sorted(list(persisted_competencies)),
                relationships_created=relationships_created,
            )

        except Exception as exc:
            logger.error(
                "kg_turn_persistence_failed",
                error=str(exc),
                interview_id=context.interview_id,
                candidate_id=context.candidate_id,
                answer_id=analysis.answer_id,
            )
            raise KnowledgeGraphError(
                f"Failed to persist turn evaluation to Knowledge Graph: {exc}"
            ) from exc

    async def persist_turn_evaluation_async(
        self,
        analysis: AnswerAnalysis,
        context: InterviewAIContext,
        question_text: str,
        answer_text: str,
        agent_id: str,
        difficulty: Optional[DifficultyLevel | str] = None,
        question_id: Optional[str] = None,
    ) -> KnowledgeGraphPersistenceResult:
        """Asynchronously persist a turn evaluation in a worker thread.

        Prevents blocking the asyncio event loop during graph database I/O.
        """
        return await asyncio.to_thread(
            self.persist_turn_evaluation,
            analysis=analysis,
            context=context,
            question_text=question_text,
            answer_text=answer_text,
            agent_id=agent_id,
            difficulty=difficulty,
            question_id=question_id,
        )
