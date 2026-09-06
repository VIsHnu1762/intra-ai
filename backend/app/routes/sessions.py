"""Sessions API router — platform integration contract + candidate session endpoints.

Routes:
  POST /api/v1/sessions                — platform posts InterviewConfiguration (creates session)
  GET  /api/v1/sessions/{id}           — get session info (public, for candidate lobby)
  POST /api/v1/sessions/{id}/start     — candidate starts the session (returns Agora credentials)
  POST /api/v1/sessions/{id}/stop      — candidate/platform stops the session
  GET  /api/v1/agents                  — list available AI interviewer agents
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.agents.registry import agent_registry
from app.schemas.sessions import (
    AgentInfoResponse,
    InterviewConfigurationRequest,
    SessionInfoResponse,
    SessionStartResponse,
    SessionStopResponse,
)
from app.sessions.models import InterviewConfiguration
from app.sessions.service import interview_session_service
from app.core.deps import get_supabase
from app.repositories.interview_repo import InterviewRepo

router = APIRouter(tags=["sessions"])


# ── Platform integration boundary ─────────────────────────────────────────────


@router.post("/sessions", response_model=SessionInfoResponse, status_code=201)
async def create_session(body: InterviewConfigurationRequest) -> SessionInfoResponse:
    """Create an interview session from the platform-supplied configuration.

    This is the platform integration boundary endpoint.
    The platform posts an InterviewConfiguration; we create the live meeting session.
    Idempotent: posting the same interview_id twice returns the existing session.

    The resulting interview_id is used as the candidate's interview link token:
        /interview/{interview_id}
    """
    # Validate agent IDs exist in registry
    unknown = [a for a in body.agent_ids if not agent_registry.has_agent(a)]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown agent IDs: {unknown}. Available: {agent_registry.list_agent_ids()}",
        )

    config = InterviewConfiguration(
        interview_id=body.interview_id,
        candidate_id=body.candidate_id,
        agent_ids=body.agent_ids,
        scheduled_start=body.scheduled_start,
        duration_minutes=body.duration_minutes,
        job_title=body.job_title,
        company=body.company,
        metadata=body.metadata,
    )
    session = interview_session_service.create_session(config)

    return _session_to_info(session)


@router.get("/sessions/{interview_id}", response_model=SessionInfoResponse)
async def get_session(
    interview_id: str,
    supabase: Client = Depends(get_supabase),
) -> SessionInfoResponse:
    """Return public session info for the candidate lobby.

    No authentication required — the interview_id itself acts as the opaque token.
    """
    session = interview_session_service.get_session(interview_id)
    if session is None:
        # Rehydrate sessions after a backend restart from the durable interview
        # record. This also makes recruiter-booked interviews immediately
        # usable without requiring a separate platform callback.
        from app.repositories.interview_repo import InterviewRepo
        from app.services.scheduling_service import SchedulingService

        interview = await InterviewRepo(supabase).get_by_id(interview_id)
        if interview and interview.get("status") in {"scheduled", "instant_active"}:
            app = dict(interview.get("applications") or {})
            app.setdefault("candidate_id", interview.get("candidate_id"))
            app.setdefault("job_id", interview.get("job_id"))
            app["candidates"] = interview.get("candidates") or {}
            app["jobs"] = interview.get("jobs") or {}
            SchedulingService._ensure_live_session(
                app,
                interview,
                scheduled_start=(interview.get("scheduled_at") if interview.get("status") == "scheduled" else ""),
            )
            session = interview_session_service.get_session(interview_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"Interview session '{interview_id}' not found.",
        )
    return _session_to_info(session)


@router.post("/sessions/{interview_id}/start", response_model=SessionStartResponse)
async def start_session(interview_id: str) -> SessionStartResponse:
    """Candidate enters the interview — validate time, start the active agent, return Agora credentials.

    Steps performed:
    1. Validate scheduled time window (candidate can enter up to 10 min early).
    2. Generate candidate Agora RTC token for the session channel (intra-{interview_id}).
    3. Start the active AI agent in the shared Agora channel.
    4. Return credentials: channel_name, agora_token, agent info.
    """
    from app.core.exceptions import NotFoundError, ValidationError

    try:
        result = await interview_session_service.start_session(interview_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Map to response model
    return SessionStartResponse(
        interview_id=result["interview_id"],
        channel_name=result["channel_name"],
        agora_app_id=result.get("agora_app_id", ""),
        agora_token=result.get("agora_token", ""),
        agora_uid=result.get("agora_uid", 0),
        rtm_user_id=result.get("rtm_user_id", ""),
        selected_agents=[
            AgentInfoResponse(**a) for a in result.get("selected_agents", [])
        ],
        current_agent_id=result["current_agent_id"],
        agent_ids=result["agent_ids"],
        session_status=result["session_status"],
        duration_minutes=result["duration_minutes"],
        job_title=result.get("job_title"),
        company=result.get("company"),
        scheduled_start=result.get("scheduled_start"),
        expires_in=result.get("expires_in", 3600),
        agent_start_warnings=result.get("agent_start_warnings", []),
    )


@router.post("/sessions/{interview_id}/stop", response_model=SessionStopResponse)
async def stop_session(
    interview_id: str,
    supabase: Client = Depends(get_supabase),
) -> SessionStopResponse:
    """Stop all active agents and mark the session as completed."""
    from app.core.exceptions import NotFoundError

    try:
        result = await interview_session_service.stop_session(interview_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # The service shares durable completion/reporting with spoken COMPLETE.
    return SessionStopResponse(**result)


# ── Agent listing ─────────────────────────────────────────────────────────────


@router.get("/agents", response_model=list[AgentInfoResponse])
async def list_agents() -> list[AgentInfoResponse]:
    """Return all registered AI interviewer agent profiles.

    Used by the frontend to display interviewer information in the lobby.
    """
    profiles = agent_registry.list_agents()
    return [
        AgentInfoResponse(
            agent_id=p.agent_id,
            name=p.display_name,
            role=p.role,
            description=p.description,
            focal_competencies=p.focal_competencies,
        )
        for p in profiles
    ]


# ── Helper ────────────────────────────────────────────────────────────────────


def _session_to_info(session: Any) -> SessionInfoResponse:
    """Convert an InterviewSession to the public SessionInfoResponse."""
    from app.interview_context.store import interview_session_store
    context = interview_session_store.get(session.channel_name)
    live_metadata = context.metadata if context else {}
    selected_agents = []
    for aid in session.agent_ids:
        try:
            profile, mapping = agent_registry.get_agent(aid)
            selected_agents.append(
                AgentInfoResponse(
                    agent_id=profile.agent_id,
                    name=profile.display_name,
                    role=profile.role,
                    description=profile.description,
                    focal_competencies=profile.focal_competencies,
                    agora_rtc_uid=int(mapping.agent_rtc_uid) if mapping.agent_rtc_uid else None,
                )
            )
        except Exception:
            selected_agents.append(
                AgentInfoResponse(agent_id=aid, name=aid.title(), role="Interviewer")
            )

    return SessionInfoResponse(
        interview_id=session.interview_id,
        channel_name=session.channel_name,
        status=session.status,
        agent_ids=session.agent_ids,
        current_agent_id=session.current_agent_id,
        selected_agents=selected_agents,
        scheduled_start=session.scheduled_start,
        duration_minutes=session.duration_minutes,
        job_title=session.job_title,
        company=session.company,
        completed=bool(live_metadata.get("completed")) or session.status == "COMPLETED",
        pending_voice_action=live_metadata.get("pending_voice_action"),
        voice_lifecycle_status=("service_paused" if live_metadata.get("service_pause")
                                else (live_metadata.get("voice_lifecycle") or {}).get("status")),
        report_status=session.metadata.get("report_status"),
    )
