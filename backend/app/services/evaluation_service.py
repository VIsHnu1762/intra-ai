"""Evaluation service — score answers on 5 dimensions via LLM."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.core.exceptions import NotFoundError
from app.integrations import openai_client
from app.repositories.interview_repo import InterviewRepo
from app.repositories.job_repo import JobRepo
from app.schemas.evaluation import EvaluationResponse

logger = structlog.stdlib.get_logger("intra_ai.service.evaluation")


class EvaluationService:
    """Evaluates candidate answers using LLM-based scoring."""

    def __init__(
        self,
        interview_repo: InterviewRepo,
        job_repo: JobRepo,
    ) -> None:
        self._interview_repo = interview_repo
        self._job_repo = job_repo

    async def evaluate_answer(self, answer_id: str) -> EvaluationResponse:
        """Evaluate a single answer on 5 dimensions."""
        answer = await self._interview_repo.get_answer_by_id(answer_id)
        if not answer:
            raise NotFoundError(f"Answer {answer_id} not found")

        question = answer.get("interview_questions", {})
        question_text = question.get("text", "")
        topic = question.get("topic", "")

        # Get job context
        interview = await self._interview_repo.get_by_id(answer["interview_id"])
        job_context = ""
        if interview:
            job = await self._job_repo.get_by_id(interview["job_id"])
            if job:
                job_context = f"{job['title']} - {job['description'][:500]}"

        rubric = {"topic": topic, "job_context": job_context}

        result = await openai_client.evaluate_answer(
            question=question_text,
            answer=answer["transcript"],
            rubric=rubric,
        )

        # Store evaluation
        eval_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        stored = await self._interview_repo.create_evaluation(
            {
                "id": eval_id,
                "interview_id": answer["interview_id"],
                "answer_id": answer_id,
                "relevance": result.get("relevance", 0),
                "depth": result.get("depth", 0),
                "accuracy": result.get("accuracy", 0),
                "communication": result.get("communication", 0),
                "confidence": result.get("confidence", 0),
                "overall": result.get("overall", 0),
                "feedback": result.get("feedback", ""),
                "created_at": now,
            }
        )

        logger.info(
            "answer_evaluated",
            answer_id=answer_id,
            overall=result.get("overall"),
        )

        return EvaluationResponse(
            id=stored["id"],
            answer_id=answer_id,
            relevance=stored["relevance"],
            depth=stored["depth"],
            accuracy=stored["accuracy"],
            communication=stored["communication"],
            confidence=stored["confidence"],
            overall=stored["overall"],
            feedback=stored["feedback"],
        )

    async def evaluate_interview(self, interview_id: str) -> list[EvaluationResponse]:
        """Evaluate all unevaluated answers for an interview."""
        interview = await self._interview_repo.get_by_id(interview_id)
        if not interview:
            raise NotFoundError(f"Interview {interview_id} not found")

        answers = await self._interview_repo.get_answers(interview_id)
        if not answers:
            raise NotFoundError(f"No answers found for interview {interview_id}")

        # Get existing evaluations to skip already-evaluated answers
        existing = await self._interview_repo.get_evaluations(interview_id)
        evaluated_answer_ids = {e["answer_id"] for e in existing}

        results: list[EvaluationResponse] = []
        for answer in answers:
            if answer["id"] in evaluated_answer_ids:
                # Return existing evaluation
                for e in existing:
                    if e["answer_id"] == answer["id"]:
                        results.append(
                            EvaluationResponse(
                                id=e["id"],
                                answer_id=e["answer_id"],
                                relevance=e["relevance"],
                                depth=e["depth"],
                                accuracy=e["accuracy"],
                                communication=e["communication"],
                                confidence=e["confidence"],
                                overall=e["overall"],
                                feedback=e["feedback"],
                            )
                        )
                        break
                continue

            evaluation = await self.evaluate_answer(answer["id"])
            results.append(evaluation)

        logger.info(
            "interview_evaluated",
            interview_id=interview_id,
            total_answers=len(answers),
            newly_evaluated=len(answers) - len(evaluated_answer_ids),
        )

        return results
