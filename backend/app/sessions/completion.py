"""Persist a completed voice meeting and reuse evidence-backed reporting."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

logger = structlog.stdlib.get_logger("intra_ai.sessions.completion")


async def persist_completed_interview(interview_id: str, supabase: Any = None) -> dict[str, Any]:
    """Offload synchronous repository I/O after the outgoing audio is stopped.

    Synthetic sessions have no durable UUID and deliberately skip persistence.
    A real session remains completed even if its report needs a later retry.
    """
    try:
        UUID(interview_id)
    except ValueError:
        return {"persistence_status": "not_applicable", "report_status": "not_applicable"}

    def run() -> dict[str, Any]:
        return asyncio.run(_persist(interview_id, supabase))

    try:
        result = await asyncio.to_thread(run)
    except Exception as exc:
        logger.error("[INTERVIEW_COMPLETION_PERSIST_FAILED]", interview_id=interview_id, error_type=type(exc).__name__)
        return {"persistence_status": "pending", "report_status": "pending", "report_error": type(exc).__name__}
    if result.get("persistence_status") != "completed":
        return result
    # Queue post-interview work on the caller's live event loop. A task created
    # inside asyncio.run in the I/O thread would be cancelled when that loop ends.
    from app.integrations.supabase_client import get_client
    from app.repositories.interview_repo import InterviewRepo
    from app.repositories.job_repo import JobRepo
    from app.services.report_service import ReportService
    client = supabase if supabase is not None else get_client()
    try:
        state = await ReportService(InterviewRepo(client), JobRepo(client)).request_report(interview_id)
        return {**result, "report_status": state.status, **({"report_id": state.report_id} if state.report_id else {})}
    except Exception as exc:
        logger.warning("[COMPLETED_INTERVIEW_REPORT_FAILED]", interview_id=interview_id, error_type=type(exc).__name__)
        return {**result, "report_status": "failed", "report_error": type(exc).__name__}


async def _persist(interview_id: str, supabase: Any = None) -> dict[str, Any]:
    from app.integrations.supabase_client import get_client
    from app.repositories.interview_repo import InterviewRepo
    from app.repositories.application_repo import ApplicationRepo

    client = supabase if supabase is not None else get_client()
    interviews = InterviewRepo(client)
    interview = await interviews.get_by_id(interview_id)
    if not interview:
        return {"persistence_status": "not_applicable", "report_status": "not_applicable"}
    if interview.get("status") in {"cancelled", "no_show", "expired"}:
        return {"persistence_status": "skipped", "report_status": "not_applicable"}

    if interview.get("status") != "completed":
        await interviews.update(interview_id, {
            "status": "completed", "ended_at": datetime.now(timezone.utc).isoformat(),
        })
    if interview.get("application_id"):
        await ApplicationRepo(client).update_status(interview["application_id"], "completed")

    return {"persistence_status": "completed"}
