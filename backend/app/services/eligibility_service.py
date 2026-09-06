"""Eligibility service — match resume against JD and auto-shortlist/reject."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.core.exceptions import NotFoundError
from app.models.enums import ApplicationStatus
from app.repositories.application_repo import ApplicationRepo
from app.repositories.job_repo import JobRepo

logger = structlog.stdlib.get_logger("intra_ai.service.eligibility")

# Score weights
_SKILLS_WEIGHT = 0.40
_EXPERIENCE_WEIGHT = 0.30
_EDUCATION_WEIGHT = 0.20
_OTHER_WEIGHT = 0.10


class EligibilityService:
    """Calculates eligibility score and auto-shortlists or rejects candidates."""

    def __init__(
        self,
        app_repo: ApplicationRepo,
        job_repo: JobRepo,
    ) -> None:
        self._app_repo = app_repo
        self._job_repo = job_repo

    async def check_eligibility(self, application_id: str) -> float:
        """Score the candidate against job requirements.

        Scoring breakdown:
          - skills_overlap  40%
          - experience_match 30%
          - education        20%
          - other            10%

        Auto-shortlists if score >= threshold, auto-rejects if below.
        Returns the overall score (0-100).
        """
        app = await self._app_repo.get_by_id(application_id)
        if not app:
            raise NotFoundError(f"Application {application_id} not found")

        parsed = await self._app_repo.get_parsed_resume(application_id)
        if not parsed:
            raise NotFoundError("Resume has not been parsed yet")

        job = await self._job_repo.get_by_id(app["job_id"])
        if not job:
            raise NotFoundError(f"Job {app['job_id']} not found")

        # Calculate sub-scores
        skills_score = self._calculate_skills_overlap(
            parsed.get("skills", []),
            job.get("required_skills", []),
        )
        experience_score = self._calculate_experience_match(
            parsed.get("experience", []),
            job.get("experience_min", 0),
            job.get("experience_max", 99),
            candidate_years=app.get("years_experience"),
        )
        education_score = self._calculate_education_score(
            parsed.get("education", []),
            job.get("education"),
        )
        other_score = self._calculate_other_score(parsed)

        # Weighted overall
        overall = (
            skills_score * _SKILLS_WEIGHT
            + experience_score * _EXPERIENCE_WEIGHT
            + education_score * _EDUCATION_WEIGHT
            + other_score * _OTHER_WEIGHT
        )
        overall = round(overall, 2)

        # Store eligibility score. Some deployed Supabase projects predate the
        # application_id unique index, so update an existing row or insert safely
        # instead of relying on ON CONFLICT(application_id).
        score_row = {
            "id": str(uuid.uuid4()),
            "application_id": application_id,
            "skills_overlap": skills_score,
            "experience_match": experience_score,
            "education_score": education_score,
            "other_score": other_score,
            "overall_score": overall,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        table = self._app_repo._sb.table("eligibility_scores")
        existing_score = table.select("id").eq("application_id", application_id).maybe_single().execute()
        if existing_score and existing_score.data:
            table.update({k: v for k, v in score_row.items() if k != "id"}).eq("id", existing_score.data["id"]).execute()
        else:
            table.insert(score_row).execute()

        # Update application with score
        threshold = job.get("eligibility_threshold", 60.0)
        if overall >= threshold:
            new_status = ApplicationStatus.SHORTLISTED.value
        else:
            new_status = ApplicationStatus.REJECTED.value

        await self._app_repo.update_status(
            application_id,
            new_status,
            extra={"eligibility_score": overall},
        )

        logger.info(
            "eligibility_checked",
            application_id=application_id,
            score=overall,
            threshold=threshold,
            result=new_status,
        )

        return overall

    # ── Scoring helpers ──────────────────────────────────────

    @staticmethod
    def _calculate_skills_overlap(
        candidate_skills: list[str],
        required_skills: list[str],
    ) -> float:
        """Return 0-100 based on how many required skills the candidate has."""
        if not required_skills:
            return 100.0

        candidate_lower = {s.lower().strip() for s in candidate_skills}
        required_lower = {s.lower().strip() for s in required_skills}

        if not required_lower:
            return 100.0

        overlap = candidate_lower & required_lower
        return round((len(overlap) / len(required_lower)) * 100, 2)

    @staticmethod
    def _calculate_experience_match(
        experience_entries: list[dict[str, Any]],
        min_years: int,
        max_years: int,
        candidate_years: int | float | None = None,
    ) -> float:
        """Estimate total years from entries and compare to requirements."""
        # The application form asks for years of experience explicitly. Use it
        # when a parser returns no structured entries; otherwise a valid
        # applicant is incorrectly scored as having zero experience.
        if experience_entries:
            total_years = len(experience_entries)  # rough approximation: 1 entry ~ 1+ year
        else:
            try:
                total_years = max(0.0, float(candidate_years or 0))
            except (TypeError, ValueError):
                total_years = 0.0

        if total_years >= min_years:
            return 100.0
        if min_years == 0:
            return 100.0
        return round((total_years / min_years) * 100, 2)

    @staticmethod
    def _calculate_education_score(
        education: list[dict[str, Any]],
        required_education: str | None,
    ) -> float:
        """Score based on education match."""
        if not required_education:
            return 100.0
        if not education:
            return 30.0

        # Simple check: if candidate has any degree, give partial credit
        req_lower = required_education.lower()
        for edu in education:
            degree = edu.get("degree", "").lower()
            if req_lower in degree or degree in req_lower:
                return 100.0

        return 60.0  # Has education but not exact match

    @staticmethod
    def _calculate_other_score(parsed: dict[str, Any]) -> float:
        """Bonus score for certifications, projects, etc."""
        score = 50.0  # base
        if parsed.get("certifications"):
            score += 25.0
        if parsed.get("projects"):
            score += 25.0
        return min(score, 100.0)
