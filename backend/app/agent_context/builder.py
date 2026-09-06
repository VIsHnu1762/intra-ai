"""Builder for constructing unified AgentTurnContext snapshots before and during interviews."""

from __future__ import annotations

import asyncio
from typing import Any, Optional
import structlog

from app.agent_context.models import (
    AgentTurnContext,
    CandidateProfileContext,
    CandidateExperienceItem,
    CandidateEducationItem,
    CandidateProjectItem,
    JobContext,
)
from app.agent_context.providers import (
    CandidateProfileProvider,
    DefaultCandidateProfileProvider,
    DefaultJobContextProvider,
    JobContextProvider,
)
from app.agents.models import AgentProfile
from app.agents.registry import AgentRegistry, agent_registry
from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis
from app.knowledge_graph.memory_models import PersistentCandidateMemory
from app.knowledge_graph.memory_service import CandidateMemoryService
from app.models.enums import DifficultyLevel

logger = structlog.stdlib.get_logger("intra_ai.agent_context.builder")


class AgentTurnContextBuilder:
    """Constructs deterministic, typed AgentTurnContext snapshots.

    Responsibilities:
    - Load candidate CV profile context (source="RESUME")
    - Load job description context (evaluation benchmarks)
    - Retrieve bounded, relevant persistent memory from Knowledge Graph
    - Assemble current InterviewAIContext and active AgentProfile
    - Attach current turn question, candidate answer, and M1 AnswerAnalysis
    - Construct handoff context for receiving agent upon SWITCH_AGENT
    """

    def __init__(
        self,
        memory_service: Optional[CandidateMemoryService] = None,
        candidate_provider: Optional[CandidateProfileProvider] = None,
        job_provider: Optional[JobContextProvider] = None,
        registry: Optional[AgentRegistry] = None,
    ) -> None:
        self.memory_service = memory_service or CandidateMemoryService()
        self.candidate_provider = candidate_provider or DefaultCandidateProfileProvider()
        self.job_provider = job_provider or DefaultJobContextProvider()
        self.registry = registry or agent_registry

    def build_initial_context(
        self,
        candidate_id: str,
        job_id: str,
        interview_id: str,
        round_id: str,
        agent_id: str,
        difficulty: DifficultyLevel = DifficultyLevel.MEDIUM,
        missing_competencies: Optional[list[str]] = None,
        opening_question: Optional[str] = None,
    ) -> AgentTurnContext:
        """Construct initial pre-interview context before conversational turns begin."""
        cid = candidate_id.strip()
        jid = job_id.strip()
        aid = agent_id.strip().lower()

        # 1. Load Candidate Profile (CV facts)
        candidate = self.candidate_provider.get_candidate_profile(cid)

        # 2. Load Job Context (JD requirements)
        job = self.job_provider.get_job_context(jid)

        # 3. Retrieve Initial Persistent Candidate Memory (Knowledge Graph)
        persistent_memory = self.memory_service.get_candidate_memory(cid)

        # 4. Resolve Active Agent Profile
        profile = self.registry.get_profile(aid) if self.registry.has_agent(aid) else self.registry.get_profile("alex")

        # 5. Initialize Live Interview State
        effective_missing = list(missing_competencies) if missing_competencies is not None else (
            list(job.required_competencies) if job.required_competencies else list(profile.focal_competencies)
        )

        interview = InterviewAIContext(
            interview_id=interview_id.strip(),
            candidate_id=cid,
            current_round_id=round_id.strip(),
            current_agent_id=profile.agent_id,
            difficulty=difficulty,
            missing_competencies=effective_missing,
            metadata={"job_id": jid},
        )

        context = AgentTurnContext(
            candidate=candidate,
            job=job,
            persistent_memory=persistent_memory,
            interview=interview,
            agent=profile,
            current_question=opening_question,
            metadata={"phase": "initial_pre_interview"},
        )

        logger.info(
            "initial_agent_turn_context_built",
            candidate_id=cid,
            job_id=jid,
            agent=profile.agent_id,
            prior_evidence_count=len(persistent_memory.evidence),
        )
        return context

    def build_turn_context(
        self,
        context: InterviewAIContext,
        agent_profile: AgentProfile,
        current_question: Optional[str] = None,
        current_answer: Optional[str] = None,
        analysis: Optional[AnswerAnalysis] = None,
        job_id: Optional[str] = None,
    ) -> AgentTurnContext:
        """Synchronously construct an AgentTurnContext snapshot for a completed turn."""
        cid = context.candidate_id
        jid = job_id or context.metadata.get("job_id") or "default_job"

        # 1. Load Candidate and Job Context
        candidate = self.candidate_provider.get_candidate_profile(cid)
        job = self.job_provider.get_job_context(jid)

        # 2. Targeted Persistent Memory Retrieval
        target_competency = None
        if analysis and analysis.competency_findings:
            target_competency = analysis.competency_findings[0].competency_id
        elif agent_profile.focal_competencies:
            target_competency = agent_profile.focal_competencies[0]

        persistent_memory = self.memory_service.get_candidate_memory(
            candidate_id=cid,
            competency=target_competency,
        )

        # If specific competency returned no memory, fall back to general candidate memory
        # to ensure historical context from other rounds/agents is not erased.
        if not persistent_memory.evidence and target_competency:
            general_memory = self.memory_service.get_candidate_memory(candidate_id=cid)
            if general_memory.evidence:
                persistent_memory = general_memory

        # Snapshot isolation: deep copy the live context
        interview_snapshot = context.model_copy(deep=True)

        turn_context = AgentTurnContext(
            candidate=candidate,
            job=job,
            persistent_memory=persistent_memory,
            interview=interview_snapshot,
            agent=agent_profile,
            current_question=current_question,
            current_answer=current_answer,
            answer_analysis=analysis,
            metadata={"phase": "turn_evaluation"},
        )

        logger.debug(
            "agent_turn_context_built",
            candidate_id=cid,
            agent=agent_profile.agent_id,
            competency_targeted=target_competency,
            evidence_count=len(persistent_memory.evidence),
        )
        return turn_context

    async def build_turn_context_async(
        self,
        context: InterviewAIContext,
        agent_profile: AgentProfile,
        current_question: Optional[str] = None,
        current_answer: Optional[str] = None,
        analysis: Optional[AnswerAnalysis] = None,
        job_id: Optional[str] = None,
    ) -> AgentTurnContext:
        """Asynchronously construct an AgentTurnContext snapshot for a completed turn."""
        cid = context.candidate_id
        jid = job_id or context.metadata.get("job_id") or "default_job"

        # The session boundary hydrates immutable JD/CV snapshots before the
        # first voice turn. Prefer those snapshots for live calls so the
        # default provider cannot silently fall back to an empty profile when
        # the service is running without repository injection.
        async def candidate_snapshot():
            cached = self._candidate_from_metadata(context.metadata, cid)
            return cached if cached is not None else await self.candidate_provider.get_candidate_profile_async(cid)

        async def job_snapshot():
            cached = self._job_from_metadata(context.metadata, jid)
            return cached if cached is not None else await self.job_provider.get_job_context_async(jid)

        # One bounded candidate-scoped memory read preserves cross-agent evidence.
        # Previously an empty targeted read repeated the entire graph traversal.
        candidate, job, persistent_memory = await asyncio.gather(
            candidate_snapshot(), job_snapshot(),
            self.memory_service.get_candidate_memory_async(candidate_id=cid),
        )

        interview_snapshot = context.model_copy(deep=True)

        logger.info(
            "[CONTEXT_SNAPSHOT]",
            interview_id=context.interview_id,
            candidate_id=cid,
            candidate_source=candidate.source,
            candidate_skills_count=len(candidate.skills),
            candidate_experience_count=len(candidate.experience),
            job_id=job.job_id,
            job_title=job.title,
            job_required_skills_count=len(job.required_skills),
            job_description_loaded=bool(job.description),
            persistent_memory_count=len(persistent_memory.evidence),
        )

        return AgentTurnContext(
            candidate=candidate,
            job=job,
            persistent_memory=persistent_memory,
            interview=interview_snapshot,
            agent=agent_profile,
            current_question=current_question,
            current_answer=current_answer,
            answer_analysis=analysis,
            metadata={"phase": "turn_evaluation"},
        )

    @staticmethod
    def _candidate_from_metadata(metadata: dict[str, Any], candidate_id: str) -> CandidateProfileContext | None:
        raw = metadata.get("candidate_profile") or metadata.get("parsed_resume")
        if not isinstance(raw, dict):
            return None
        parsed = raw.get("parsed_resume") if isinstance(raw.get("parsed_resume"), dict) else raw
        experience = [
            CandidateExperienceItem(**item)
            for item in (parsed.get("experience") or [])
            if isinstance(item, dict) and item.get("company") and item.get("role")
        ]
        education = [
            CandidateEducationItem(**item)
            for item in (parsed.get("education") or [])
            if isinstance(item, dict) and item.get("institution") and item.get("degree")
        ]
        projects = [
            CandidateProjectItem(**item)
            for item in (parsed.get("projects") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        return CandidateProfileContext(
            candidate_id=candidate_id,
            name=metadata.get("candidate_name") or raw.get("name"),
            email=metadata.get("candidate_email") or raw.get("email"),
            phone=raw.get("phone"),
            skills=list(parsed.get("skills") or metadata.get("candidate_skills") or []),
            experience=experience,
            education=education,
            projects=projects,
            technologies=sorted({t for project in projects for t in project.technologies}),
            source="RESUME",
            metadata={"resume_url": metadata.get("resume_url"),
                      "resume_excerpt": (str(parsed.get("raw_text") or "")[:4000]
                                         if not (experience or projects) else "")},
        )

    @staticmethod
    def _job_from_metadata(metadata: dict[str, Any], job_id: str) -> JobContext | None:
        if not metadata.get("job_description") and not metadata.get("required_skills"):
            return None
        return JobContext(
            job_id=str(metadata.get("job_id") or job_id),
            title=str(metadata.get("job_title") or "Role"),
            company=metadata.get("company") or "Intra AI",
            description=metadata.get("job_description"),
            required_skills=list(metadata.get("required_skills") or []),
            required_competencies=list(metadata.get("required_competencies") or []),
            interview_rounds=list(metadata.get("interview_rounds") or []),
            metadata={"source": "JOB_DESCRIPTION"},
        )


    def build_handoff_context(
        self,
        turn_context: AgentTurnContext,
        target_agent_profile: AgentProfile,
    ) -> AgentTurnContext:
        """Construct context for the receiving agent upon SWITCH_AGENT.

        Guarantees that the target agent:
        1. Inherits the full candidate CV profile.
        2. Inherits the job description benchmark.
        3. Inherits all cumulative persistent candidate memory (including findings from the handing-off agent).
        4. Inherits the updated InterviewAIContext (with prior turn evidence, contradictions, question history).
        5. Sets the active agent to target_agent_profile.
        6. Never starts from an empty context.
        """
        # Clone context with new active agent
        handoff_interview = turn_context.interview.model_copy(deep=True)
        handoff_interview.current_agent_id = target_agent_profile.agent_id

        handoff_context = AgentTurnContext(
            candidate=turn_context.candidate,
            job=turn_context.job,
            persistent_memory=turn_context.persistent_memory,
            interview=handoff_interview,
            agent=target_agent_profile,
            current_question=turn_context.current_question,
            current_answer=turn_context.current_answer,
            answer_analysis=turn_context.answer_analysis,
            target_agent=None,
            metadata={
                "phase": "handoff",
                "handing_off_agent": turn_context.agent.agent_id,
                "receiving_agent": target_agent_profile.agent_id,
            },
        )

        logger.info(
            "handoff_context_built",
            from_agent=turn_context.agent.agent_id,
            to_agent=target_agent_profile.agent_id,
            candidate_id=turn_context.candidate.candidate_id,
            cumulative_evidence_count=len(turn_context.persistent_memory.evidence),
        )
        return handoff_context
