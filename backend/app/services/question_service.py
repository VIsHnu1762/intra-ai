"""Question generation service — adaptive question creation via OpenAI."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.core.exceptions import NotFoundError
from app.integrations import openai_client
from app.models.enums import InterviewRoundType
from app.repositories.application_repo import ApplicationRepo
from app.repositories.interview_repo import InterviewRepo
from app.repositories.job_repo import JobRepo
from app.schemas.interviews import InterviewQuestionResponse

logger = structlog.stdlib.get_logger("intra_ai.service.question")

_ROUND_QUESTION_COUNTS = {
    InterviewRoundType.INTRODUCTION: 3,
    InterviewRoundType.TECHNICAL: 6,
    InterviewRoundType.BEHAVIORAL: 4,
    InterviewRoundType.HR_CULTURE: 3,
}


class QuestionService:
    """Generates and manages interview questions with adaptive difficulty."""

    def __init__(
        self,
        interview_repo: InterviewRepo,
        app_repo: ApplicationRepo,
        job_repo: JobRepo,
    ) -> None:
        self._interview_repo = interview_repo
        self._app_repo = app_repo
        self._job_repo = job_repo

    async def generate_questions(
        self,
        interview_id: str,
        round_type: InterviewRoundType,
    ) -> list[InterviewQuestionResponse]:
        """Generate questions for a specific round using the candidate's resume and JD."""
        interview = await self._interview_repo.get_by_id(interview_id)
        if not interview:
            raise NotFoundError(f"Interview {interview_id} not found")

        # Get job details
        job = await self._job_repo.get_by_id(interview["job_id"])

        # Get parsed resume
        parsed_resume = await self._app_repo.get_parsed_resume(interview["application_id"])

        # Get previous evaluations for adaptive difficulty
        existing_evals = await self._interview_repo.get_evaluations(interview_id)
        previous_scores = [
            e.get("overall", 5.0)
            for e in existing_evals
            if isinstance(e.get("overall"), (int, float))
        ]

        avg_score = sum(previous_scores) / len(previous_scores) if previous_scores else 5.0

        if avg_score >= 8.0:
            difficulty_note = "Candidate is performing exceptionally well. Generate HARD/EXPERT level questions."
        elif avg_score >= 6.0:
            difficulty_note = "Candidate is performing well. Generate MEDIUM/HARD level questions."
        elif avg_score >= 4.0:
            difficulty_note = "Candidate is performing at an average level. Generate EASY/MEDIUM questions."
        else:
            difficulty_note = "Candidate is struggling. Generate EASY questions with simpler scope."

        count = _ROUND_QUESTION_COUNTS.get(round_type, 4)

        context = {
            "round_type": round_type.value,
            "count": count,
            "difficulty_note": difficulty_note,
            "job_title": job["title"] if job else "",
            "job_description": job["description"] if job else "",
            "required_skills": job.get("required_skills", []) if job else [],
            "candidate_skills": parsed_resume.get("skills", []) if parsed_resume else [],
            "candidate_experience": parsed_resume.get("experience", []) if parsed_resume else [],
            "previous_scores": previous_scores,
        }

        raw_questions = await openai_client.generate_questions(context)

        # Store questions in DB
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "id": str(uuid.uuid4()),
                "interview_id": interview_id,
                "round_type": round_type.value,
                "question_type": q.get("question_type", round_type.value),
                "text": q["text"],
                "topic": q.get("topic", ""),
                "difficulty": q.get("difficulty", "medium"),
                "order": idx + 1,
                "created_at": now,
            }
            for idx, q in enumerate(raw_questions)
        ]

        created = await self._interview_repo.create_questions(rows)

        logger.info(
            "questions_generated",
            interview_id=interview_id,
            round_type=round_type.value,
            count=len(created),
            avg_previous_score=avg_score,
        )

        return [
            InterviewQuestionResponse(
                id=q["id"],
                interview_id=q["interview_id"],
                round_type=q["round_type"],
                text=q["text"],
                topic=q.get("topic", ""),
                difficulty=q["difficulty"],
                order=q["order"],
            )
            for q in created
        ]

    async def get_questions(
        self,
        interview_id: str,
        round_type: str | None = None,
    ) -> list[InterviewQuestionResponse]:
        """Get existing questions for an interview, optionally filtered by round."""
        rows = await self._interview_repo.get_questions(interview_id, round_type=round_type)
        return [
            InterviewQuestionResponse(
                id=q["id"],
                interview_id=q["interview_id"],
                round_type=q["round_type"],
                text=q["text"],
                topic=q.get("topic", ""),
                difficulty=q["difficulty"],
                order=q["order"],
            )
            for q in rows
        ]
