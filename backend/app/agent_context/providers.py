"""Providers for CandidateProfileContext and JobContext.

Integrates with Intra AI repository abstractions (CandidateRepo, JobRepo)
while supporting in-memory storage, mock data, and offline operation for testing.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, Protocol
import structlog

from app.agent_context.models import (
    CandidateEducationItem,
    CandidateExperienceItem,
    CandidateProfileContext,
    CandidateProjectItem,
    JobContext,
)

logger = structlog.stdlib.get_logger("intra_ai.agent_context.providers")


class CandidateProfileProvider(Protocol):
    """Protocol for retrieving candidate CV/application profile context."""

    def get_candidate_profile(self, candidate_id: str) -> CandidateProfileContext: ...

    async def get_candidate_profile_async(self, candidate_id: str) -> CandidateProfileContext: ...


class JobContextProvider(Protocol):
    """Protocol for retrieving job description context."""

    def get_job_context(self, job_id: str) -> JobContext: ...

    async def get_job_context_async(self, job_id: str) -> JobContext: ...


class DefaultCandidateProfileProvider:
    """Default provider for candidate profiles.

    Supports:
    1. In-memory dictionary store for testing and session-scoped candidate data.
    2. Optional backing CandidateRepo for database lookup.
    3. Graceful fallback for unconfigured or missing candidates.
    """

    def __init__(self, candidate_repo: Any = None) -> None:
        self._repo = candidate_repo
        self._in_memory_profiles: dict[str, CandidateProfileContext] = {}

    def set_profile(self, candidate_id: str, profile: CandidateProfileContext) -> None:
        """Register a candidate profile in the in-memory cache."""
        self._in_memory_profiles[candidate_id.strip()] = profile

    def get_candidate_profile(self, candidate_id: str) -> CandidateProfileContext:
        """Synchronously retrieve candidate profile."""
        cid = candidate_id.strip()
        if cid in self._in_memory_profiles:
            return self._in_memory_profiles[cid]

        # If repo is available, run async query in thread/loop
        if self._repo:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If in a running event loop, return fallback or cached
                    logger.debug("async_loop_running_candidate_sync_skipped", candidate_id=cid)
                else:
                    data = loop.run_until_complete(self._repo.get_by_id(cid))
                    if data:
                        profile = self._parse_candidate_row(data)
                        self._in_memory_profiles[cid] = profile
                        return profile
            except Exception as exc:
                logger.warning("candidate_repo_sync_fetch_failed", error=str(exc), candidate_id=cid)

        # Fallback profile
        return CandidateProfileContext(candidate_id=cid)

    async def get_candidate_profile_async(self, candidate_id: str) -> CandidateProfileContext:
        """Asynchronously retrieve candidate profile."""
        cid = candidate_id.strip()
        if cid in self._in_memory_profiles:
            return self._in_memory_profiles[cid]

        if self._repo:
            try:
                data = await self._repo.get_by_id(cid)
                if data:
                    profile = self._parse_candidate_row(data)
                    self._in_memory_profiles[cid] = profile
                    return profile
            except Exception as exc:
                logger.warning("candidate_repo_async_fetch_failed", error=str(exc), candidate_id=cid)

        return CandidateProfileContext(candidate_id=cid)

    @staticmethod
    def _parse_candidate_row(data: dict[str, Any]) -> CandidateProfileContext:
        """Map Supabase candidate row with parsed_resumes into CandidateProfileContext."""
        parsed = data.get("parsed_resumes") or {}
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]

        skills = parsed.get("skills", [])
        experience = [
            CandidateExperienceItem(
                company=exp.get("company", ""),
                role=exp.get("role", ""),
                start_date=exp.get("start_date", ""),
                end_date=exp.get("end_date"),
                description=exp.get("description"),
            )
            for exp in parsed.get("experience", [])
            if isinstance(exp, dict) and exp.get("company") and exp.get("role")
        ]
        education = [
            CandidateEducationItem(
                institution=edu.get("institution", ""),
                degree=edu.get("degree", ""),
                field=edu.get("field", ""),
                year=edu.get("year"),
            )
            for edu in parsed.get("education", [])
            if isinstance(edu, dict) and edu.get("institution") and edu.get("degree")
        ]
        projects = [
            CandidateProjectItem(
                name=proj.get("name", ""),
                description=proj.get("description"),
                technologies=proj.get("technologies", []),
            )
            for proj in parsed.get("projects", [])
            if isinstance(proj, dict) and proj.get("name")
        ]

        technologies: set[str] = set()
        for p in projects:
            technologies.update(p.technologies)

        return CandidateProfileContext(
            candidate_id=str(data.get("id", "")),
            name=data.get("name"),
            email=data.get("email"),
            phone=data.get("phone"),
            skills=skills,
            experience=experience,
            education=education,
            projects=projects,
            technologies=sorted(list(technologies)),
            source="RESUME",
            metadata={"resume_url": data.get("resume_url")},
        )


class DefaultJobContextProvider:
    """Default provider for job description context.

    Supports:
    1. In-memory dictionary store for testing and session-scoped job data.
    2. Optional backing JobRepo for database lookup.
    3. Graceful fallback for unconfigured or missing jobs.
    """

    def __init__(self, job_repo: Any = None) -> None:
        self._repo = job_repo
        self._in_memory_jobs: dict[str, JobContext] = {}

    def set_job(self, job_id: str, job: JobContext) -> None:
        """Register a job context in the in-memory cache."""
        self._in_memory_jobs[job_id.strip()] = job

    def get_job_context(self, job_id: str) -> JobContext:
        """Synchronously retrieve job context."""
        jid = job_id.strip()
        if jid in self._in_memory_jobs:
            return self._in_memory_jobs[jid]

        if self._repo:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    logger.debug("async_loop_running_job_sync_skipped", job_id=jid)
                else:
                    data = loop.run_until_complete(self._repo.get_by_id(jid))
                    if data:
                        job = self._parse_job_row(data)
                        self._in_memory_jobs[jid] = job
                        return job
            except Exception as exc:
                logger.warning("job_repo_sync_fetch_failed", error=str(exc), job_id=jid)

        return JobContext(job_id=jid, title="Software Engineering Role")

    async def get_job_context_async(self, job_id: str) -> JobContext:
        """Asynchronously retrieve job context."""
        jid = job_id.strip()
        if jid in self._in_memory_jobs:
            return self._in_memory_jobs[jid]

        if self._repo:
            try:
                data = await self._repo.get_by_id(jid)
                if data:
                    job = self._parse_job_row(data)
                    self._in_memory_jobs[jid] = job
                    return job
            except Exception as exc:
                logger.warning("job_repo_async_fetch_failed", error=str(exc), job_id=jid)

        return JobContext(job_id=jid, title="Software Engineering Role")

    @staticmethod
    def _parse_job_row(data: dict[str, Any]) -> JobContext:
        """Map Supabase job row into JobContext."""
        job_rounds = [
            r.get("type", "")
            for r in data.get("job_rounds", [])
            if isinstance(r, dict) and r.get("type")
        ]

        return JobContext(
            job_id=str(data.get("id", "")),
            title=data.get("title", "Role"),
            company=data.get("company"),
            department=data.get("department"),
            location=data.get("location"),
            description=data.get("description"),
            required_skills=data.get("required_skills", []),
            required_competencies=data.get("required_competencies", []),
            experience_min=data.get("experience_min"),
            experience_max=data.get("experience_max"),
            interview_rounds=job_rounds,
            metadata={"status": data.get("status")},
        )
