"""Evaluation routes — trigger and retrieve answer evaluations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.deps import get_supabase
from app.core.security import require_role
from app.repositories.interview_repo import InterviewRepo
from app.repositories.job_repo import JobRepo
from app.schemas.evaluation import EvaluationResponse
from app.services.evaluation_service import EvaluationService
from app.services.workspace_access import recruiter_actor
from app.voice.authorization import Actor, require_interview

router = APIRouter(prefix="/interviews", tags=["evaluation"])


def _eval_service(supabase: Client = Depends(get_supabase)) -> EvaluationService:
    return EvaluationService(
        interview_repo=InterviewRepo(supabase),
        job_repo=JobRepo(supabase),
    )


@router.post("/{interview_id}/evaluate", response_model=list[EvaluationResponse])
async def evaluate_interview(
    interview_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: EvaluationService = Depends(_eval_service),
    supabase: Client = Depends(get_supabase),
) -> list[EvaluationResponse]:
    """Trigger evaluation of all answers for an interview."""
    await require_interview(actor, interview_id, supabase)
    return await service.evaluate_interview(interview_id)


@router.get("/{interview_id}/evaluation", response_model=list[EvaluationResponse])
async def get_evaluations(
    interview_id: str,
    actor: Actor = Depends(recruiter_actor),
    service: EvaluationService = Depends(_eval_service),
    supabase: Client = Depends(get_supabase),
) -> list[EvaluationResponse]:
    """Get existing evaluation results for an interview."""
    await require_interview(actor, interview_id, supabase)
    repo = InterviewRepo(
        service._interview_repo._sb  # type: ignore[attr-defined]
    )
    evaluations = await repo.get_evaluations(interview_id)
    return [
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
        for e in evaluations
    ]
