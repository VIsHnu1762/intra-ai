"""Interview session routes — start, end, questions, answers, proctoring."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.agora_token2 import RtcTokenBuilder2
from app.core.deps import get_current_user, get_supabase
from app.repositories.application_repo import ApplicationRepo
from app.repositories.interview_repo import InterviewRepo
from app.repositories.job_repo import JobRepo
from app.schemas.common import MessageResponse
from app.schemas.evaluation import AnswerCreate
from app.schemas.interviews import (
    GenerateQuestionsRequest,
    InterviewQuestionResponse,
    ScheduledInterviewResponse,
)
from app.schemas.reports import ProctoringEventSchema
from app.services.interview_service import InterviewService
from app.services.question_service import QuestionService
from app.services.workspace_access import current_actor
from app.voice.authorization import Actor, require_interview

router = APIRouter(prefix="/interviews", tags=["interviews"])


def _interview_service(supabase: Client = Depends(get_supabase)) -> InterviewService:
    return InterviewService(interview_repo=InterviewRepo(supabase))


def _question_service(supabase: Client = Depends(get_supabase)) -> QuestionService:
    return QuestionService(
        interview_repo=InterviewRepo(supabase),
        app_repo=ApplicationRepo(supabase),
        job_repo=JobRepo(supabase),
    )


def _interview_repo(supabase: Client = Depends(get_supabase)) -> InterviewRepo:
    return InterviewRepo(supabase)


# ── Session lifecycle ────────────────────────────────────────


@router.post("/{interview_id}/start")
async def start_interview(
    interview_id: str,
    actor: Actor = Depends(current_actor),
    service: InterviewService = Depends(_interview_service),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    """Start an interview session."""
    await require_interview(actor, interview_id, supabase)
    return await service.start_interview(interview_id)


@router.post("/{interview_id}/end")
async def end_interview(
    interview_id: str,
    actor: Actor = Depends(current_actor),
    service: InterviewService = Depends(_interview_service),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    """End an interview session."""
    await require_interview(actor, interview_id, supabase)
    return await service.end_interview(interview_id)


# ── Questions ────────────────────────────────────────────────


@router.post(
    "/{interview_id}/questions/generate",
    response_model=list[InterviewQuestionResponse],
)
async def generate_questions(
    interview_id: str,
    data: GenerateQuestionsRequest,
    actor: Actor = Depends(current_actor),
    service: QuestionService = Depends(_question_service),
    supabase: Client = Depends(get_supabase),
) -> list[InterviewQuestionResponse]:
    """Generate questions for a specific interview round."""
    await require_interview(actor, interview_id, supabase)
    return await service.generate_questions(interview_id, data.round_type)


@router.get(
    "/{interview_id}/questions",
    response_model=list[InterviewQuestionResponse],
)
async def get_questions(
    interview_id: str,
    round_type: str | None = None,
    actor: Actor = Depends(current_actor),
    service: QuestionService = Depends(_question_service),
    supabase: Client = Depends(get_supabase),
) -> list[InterviewQuestionResponse]:
    """Get questions for an interview, optionally filtered by round type."""
    await require_interview(actor, interview_id, supabase)
    return await service.get_questions(interview_id, round_type=round_type)


# ── Answers ──────────────────────────────────────────────────


@router.post("/{interview_id}/answers", status_code=201)
async def submit_answer(
    interview_id: str,
    data: AnswerCreate,
    actor: Actor = Depends(current_actor),
    repo: InterviewRepo = Depends(_interview_repo),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    """Submit a candidate's answer transcript."""
    await require_interview(actor, interview_id, supabase)
    question = await repo.get_question_by_id(data.question_id)
    if not question or question.get("interview_id") != interview_id:
        from app.core.exceptions import ValidationError
        raise ValidationError("The question does not belong to this interview")
    now = datetime.now(timezone.utc).isoformat()
    answer = await repo.create_answer(
        {
            "id": str(uuid.uuid4()),
            "interview_id": interview_id,
            "question_id": data.question_id,
            "transcript": data.transcript,
            "duration_seconds": data.duration_seconds,
            "created_at": now,
        }
    )
    return answer


# ── Proctoring ───────────────────────────────────────────────


@router.post("/{interview_id}/proctoring/events", status_code=201)
async def log_proctoring_event(
    interview_id: str,
    data: ProctoringEventSchema,
    actor: Actor = Depends(current_actor),
    repo: InterviewRepo = Depends(_interview_repo),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    """Log a proctoring event (face detection, tab switch, etc.)."""
    await require_interview(actor, interview_id, supabase)
    event = await repo.create_proctoring_event(
        {
            "id": str(uuid.uuid4()),
            "interview_id": interview_id,
            "event_type": data.type.value,
            "timestamp": data.timestamp.isoformat(),
            "details": data.details,
        }
    )
    return event


# ── Agora RTC Token ──────────────────────────────────────────


@router.get("/{interview_id}/agora-token")
async def get_agora_rtc_token(
    interview_id: str,
    uid: int = 0,
    role: int = 1,
) -> dict[str, Any]:
    """Generate a scoped Agora RTC token for candidate or client joining an interview channel.

    Guarantees:
    - Never exposes AGORA_APP_CERTIFICATE.
    - Generates a short-lived token (1 hour / 3600s).
    - If AGORA_APP_ID or AGORA_APP_CERTIFICATE is missing, raises AgoraConfigurationError.
    """
    import time
    from app.core.config import settings
    from app.core.exceptions import AgoraConfigurationError

    app_id = (settings.AGORA_APP_ID or "").strip()
    app_certificate = (settings.AGORA_APP_CERTIFICATE or "").strip()

    if not app_id or not app_certificate:
        raise AgoraConfigurationError(
            "Agora App ID or App Certificate is not configured on the server."
        )

    channel_name = interview_id.strip()
    expire_timestamp = int(time.time()) + 3600
    rtm_user_id = f"cand_{channel_name}" if not uid or str(uid) == "0" else str(uid)

    try:
        token = RtcTokenBuilder2.build_token_with_uid(
            app_id=app_id,
            app_certificate=app_certificate,
            channel_name=channel_name,
            uid=uid,
            role=role,
            expire_seconds=expire_timestamp,
            rtm_user_id=rtm_user_id,
        )
    except Exception as exc:
        raise AgoraConfigurationError(f"Failed to generate Agora RTC token: {exc}") from exc

    return {
        "app_id": app_id,
        "channel_name": channel_name,
        "token": token,
        "uid": uid,
        "rtm_user_id": rtm_user_id,
        "role": role,
        "expires_in": 3600,
    }



@router.get("/{interview_id}/agora-agent-config")
async def get_agora_agent_config(
    interview_id: str,
    agent_id: str = "alex",
    agent_rtc_uid: int = 1001,
    user_uid: int = 0,
) -> dict[str, Any]:
    """Generate the complete Agora Agent Studio / Conversational AI start/join payload.

    Provides:
    - Agora agent RTC token.
    - Full properties overriding LLM url to the Intra AI Custom LLM endpoint.
    - LLM vendor = openai, model = intra-ai.
    - Preserved Deepgram ASR, OpenAI TTS, VAD, filler words, persona instructions, and greeting.
    """
    import time

    from app.agents import agent_registry
    from app.core.config import settings
    from app.core.exceptions import AgoraConfigurationError

    app_id = (settings.AGORA_APP_ID or "").strip()
    app_certificate = (settings.AGORA_APP_CERTIFICATE or "").strip()

    if not app_id or not app_certificate:
        raise AgoraConfigurationError(
            "Agora App ID or App Certificate is not configured on the server."
        )

    channel_name = interview_id.strip()
    expire_timestamp = int(time.time()) + 3600

    try:
        agent_token = RtcTokenBuilder2.build_token_with_uid(
            app_id=app_id,
            app_certificate=app_certificate,
            channel_name=channel_name,
            uid=agent_rtc_uid,
            role=1,  # publisher role
            expire_seconds=expire_timestamp,
        )
    except Exception as exc:
        raise AgoraConfigurationError(f"Failed to generate Agora Agent RTC token: {exc}") from exc

    profile, mapping = agent_registry.get_agent(agent_id)
    # The CustomLLMAdapter's first-turn logic will generate the contextual opening question.
    # We suppress the Agora static greeting here to prevent duplicate speech.
    greeting = " "

    payload = mapping.to_agora_join_payload(
        channel_name=channel_name,
        user_uid=user_uid,
        agent_rtc_uid=agent_rtc_uid,
        agent_token=agent_token,
        system_prompt=profile.instructions,
        greeting=greeting,
    )

    return {
        "app_id": app_id,
        "channel_name": channel_name,
        "agent_rtc_uid": agent_rtc_uid,
        "agent_token": agent_token,
        "expires_in": 3600,
        "agora_payload": payload,
    }


@router.post("/{interview_id}/start-agent")
async def start_agora_agent(
    interview_id: str,
    agent_id: str = "alex",
    agent_rtc_uid: int = 1001,
    user_uid: int = 0,
) -> dict[str, Any]:
    """Start or dispatch the configured Agora Conversational AI agent into the candidate's interview channel."""
    from app.services.agora_agent_service import agora_agent_service

    return await agora_agent_service.start_interview_agent(
        interview_id=interview_id,
        agent_id=agent_id,
        agent_rtc_uid=agent_rtc_uid,
        user_uid=user_uid,
    )


@router.post("/{interview_id}/stop-agent")
async def stop_agora_agent(
    interview_id: str,
    agent_id: str = "alex",
    agent_rtc_uid: int = 1001,
) -> dict[str, Any]:
    """Stop an active Agora Conversational AI agent."""
    from app.services.agora_agent_service import agora_agent_service

    return await agora_agent_service.stop_interview_agent(
        interview_id=interview_id,
        agent_id=agent_id,
        agent_rtc_uid=agent_rtc_uid,
    )


# ── Transcript Ingestion & Retrieval Endpoints ───────────────────────────────


@router.post("/agora-webhook")
async def agora_webhook_global(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Global Agora Notification Webhook receiver (e.g. Event 103 Agent History or Event 112 Turns Finished)."""
    from app.transcript.service import transcript_service

    return await transcript_service.ingest_agora_webhook(payload)


@router.post("/{interview_id}/agora-webhook")
async def agora_webhook_interview(
    interview_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Interview-scoped Agora Notification Webhook receiver."""
    from app.transcript.service import transcript_service

    if "channel" not in payload and "payload" not in payload:
        payload["channel"] = interview_id
    return await transcript_service.ingest_agora_webhook(payload)


@router.post("/{interview_id}/transcript-events")
async def ingest_transcript_event(
    interview_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Ingest a normalized transcript turn or RTM event."""
    from app.transcript.service import transcript_service

    return await transcript_service.ingest_event(event, interview_id_param=interview_id)


@router.get("/{interview_id}/transcript")
async def get_interview_transcript(
    interview_id: str,
    is_final_only: bool = True,
) -> dict[str, Any]:
    """Retrieve ordered normalized transcript events for an interview session."""
    from app.transcript.service import transcript_service

    result = transcript_service.get_interview_transcript(
        interview_id=interview_id,
        is_final_only=is_final_only,
    )
    return result.model_dump()

