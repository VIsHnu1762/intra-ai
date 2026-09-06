"""Apply voice lifecycle decisions only after Agora confirms outgoing speech.

Finishing an SSE response proves text delivery to Agora, not TTS playback.
Cloud history supplies speech-end timestamps for the exact agent generation
and response; no estimated sleep is used to stop a speaking interviewer.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import structlog

from app.agents.models import NextAction
from app.models.enums import ActionType
from app.sessions.models import SessionStatus

logger = structlog.stdlib.get_logger("intra_ai.sessions.response_lifecycle")


def _speech_key(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def completed_response(
    history: dict[str, Any], *, response_text: str, response_started_at_ms: int,
) -> dict[str, Any] | None:
    """Find this response's completed cloud audio, excluding earlier repeats."""
    expected = _speech_key(response_text)
    if not expected:
        return None
    for item in reversed(history.get("contents") or []):
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        if _speech_key(str(item.get("content") or "")) != expected:
            continue
        if (item.get("metadata") or {}).get("interrupted"):
            continue
        start = item.get("speech_start_ms")
        end = item.get("speech_end_ms")
        if (
            isinstance(start, (int, float)) and isinstance(end, (int, float))
            and start >= response_started_at_ms and end >= start and end > response_started_at_ms
        ):
            return item
    return None


async def finish_response(
    interview_id: str,
    next_action: NextAction,
    response_text: str,
    *,
    response_started_at_ms: int,
    expected_agent_id: str,
    expected_agora_agent_id: str,
    greeting_text: str | None = None,
    request_id: str | None = None,
    timeout_seconds: float = 45.0,
    poll_interval_seconds: float = 1.0,
    session_service: Any = None,
    agora_service: Any = None,
    context_store: Any = None,
) -> dict[str, Any]:
    """Run as a retained background task after the final SSE chunk is sent.

    The adapter captures expected IDs before starting the response. A browser
    retry or another transition invalidates this task rather than stopping a
    replacement agent. Tests may inject services; live calls use the existing
    session, context and Agora singletons.
    """
    from app.sessions.service import interview_session_service
    from app.services.agora_agent_service import agora_agent_service
    from app.interview_context.store import interview_session_store

    sessions = session_service or interview_session_service
    agora = agora_service or agora_agent_service
    contexts = context_store or interview_session_store
    if next_action.action not in {ActionType.SWITCH_AGENT, ActionType.COMPLETE}:
        return {"status": "not_required"}
    if not expected_agora_agent_id:
        return {"status": "missing_agent_generation"}

    context = contexts.get(interview_id)
    bound_log = logger.bind(
        interview_id=interview_id, request_id=request_id,
        agent_id=expected_agent_id, agora_agent_id=expected_agora_agent_id,
        action=next_action.action.value,
    )

    def owns_pending_action() -> bool:
        if not context:
            return True
        pending_action = context.metadata.get("pending_voice_action")
        pending_request = context.metadata.get("pending_voice_request_id")
        return (
            (not pending_action or pending_action == next_action.action.value)
            and (not pending_request or pending_request == request_id)
        )

    def record(status: str, **details: Any) -> dict[str, Any]:
        result = {"status": status, "action": next_action.action.value, **details}
        if context and owns_pending_action():
            context.metadata["voice_lifecycle"] = result
            if status not in {"waiting_for_audio", "audio_drained"}:
                context.metadata.pop("pending_voice_action", None)
                context.metadata.pop("pending_voice_request_id", None)
        return result

    def current_session() -> Any:
        session = sessions.get_session(interview_id)
        confirmed_stopped = bool(
            session and next_action.action == ActionType.COMPLETE and not session.started_agents
            and expected_agora_agent_id in session.metadata.get("confirmed_stopped_agora_agents", [])
        )
        if (
            not owns_pending_action() or session is None or session.status != SessionStatus.IN_PROGRESS
            or session.current_agent_id != expected_agent_id
            or (session.started_agents.get(expected_agent_id) != expected_agora_agent_id and not confirmed_stopped)
        ):
            return None
        return session

    async def complete_without_audio_confirmation(note: str) -> dict[str, Any]:
        # Candidate autonomy does not depend on TTS succeeding. Preserve
        # strict generation/owner checks, but stop a completed interview after
        # the bounded farewell wait even when cloud history is unavailable.
        if current_session() is None:
            return record("stale")
        try:
            result = await sessions.stop_session(
                interview_id, expected_agora_agent_id=expected_agora_agent_id,
                expected_voice_request_id=request_id,
            )
            bound_log.warning("[COMPLETE_WITHOUT_AUDIO_CONFIRMATION]", audio_note=note, result_status=result.get("status"))
            return record("stale" if result.get("status") == "stale" else "applied", result=result, audio_note=note)
        except Exception as exc:
            bound_log.error("[VOICE_LIFECYCLE_FAILED]", error_type=type(exc).__name__, audio_note=note)
            return record("transition_failed", error_type=type(exc).__name__, audio_note=note)

    record("waiting_for_audio")
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    while time.monotonic() < deadline:
        session = current_session()
        if session is None:
            return record("stale")
        transition_started = False
        try:
            if next_action.action == ActionType.COMPLETE and not session.started_agents:
                # The superseded handoff already confirmed this exact voice's
                # leave. There is no remaining audio to drain; do not wait for
                # a farewell that the stopped cloud generation cannot speak.
                transition_started = True
                result = await sessions.stop_session(
                    interview_id, expected_agora_agent_id=expected_agora_agent_id,
                    expected_voice_request_id=request_id,
                )
                bound_log.info("[COMPLETE_AFTER_CONFIRMED_AGENT_STOP]", result_status=result.get("status"))
                return record("stale" if result.get("status") == "stale" else "applied", result=result,
                              audio_note="agent_already_stopped")
            remaining = max(0.001, deadline - time.monotonic())
            async with asyncio.timeout(remaining):
                history = await agora.get_agent_history(expected_agora_agent_id)
            # The response belongs to this exact cloud generation AND room.
            if history.get("agent_id") != expected_agora_agent_id or history.get("channel") != session.channel_name:
                if next_action.action == ActionType.COMPLETE:
                    return await complete_without_audio_confirmation("history_identity_unconfirmed")
                return record("history_identity_mismatch")
            if next_action.action == ActionType.COMPLETE:
                interrupted = any(
                    isinstance(item, dict) and item.get("role") == "assistant"
                    and _speech_key(str(item.get("content") or "")) == _speech_key(response_text)
                    and isinstance(item.get("speech_start_ms"), (int, float))
                    and item["speech_start_ms"] >= response_started_at_ms
                    and (item.get("metadata") or {}).get("interrupted")
                    for item in history.get("contents") or []
                )
                if interrupted:
                    return await complete_without_audio_confirmation("farewell_interrupted")
            spoken = completed_response(
                history, response_text=response_text,
                response_started_at_ms=response_started_at_ms,
            )
            if spoken:
                if current_session() is None:
                    return record("stale")
                bound_log.info(
                    "[AGORA_RESPONSE_AUDIO_DRAINED]", channel=session.channel_name,
                    turn_id=spoken.get("turn_id"), speech_start_ms=spoken.get("speech_start_ms"),
                    speech_end_ms=spoken.get("speech_end_ms"),
                )
                record("audio_drained", turn_id=spoken.get("turn_id"))
                transition_started = True
                if next_action.action == ActionType.COMPLETE:
                    result = await sessions.stop_session(
                        interview_id, expected_agora_agent_id=expected_agora_agent_id,
                        expected_voice_request_id=request_id,
                    )
                else:
                    result = await sessions.handoff_agent(
                        interview_id, next_action.target_agent_id or "",
                        greeting_text=greeting_text,
                        expected_agora_agent_id=expected_agora_agent_id,
                        expected_voice_request_id=request_id,
                    )
                bound_log.info("[VOICE_LIFECYCLE_APPLIED]", result_status=result.get("status"))
                return record("stale" if result.get("status") in {"stale", "superseded"} else "applied", result=result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = type(exc).__name__
            # Lifecycle failures after confirmed speech should be surfaced;
            # do not repeatedly stop/start an agent from an obsolete decision.
            if transition_started:
                bound_log.error("[VOICE_LIFECYCLE_FAILED]", error_type=last_error)
                return record("transition_failed", error_type=last_error)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(min(poll_interval_seconds, remaining))

    bound_log.error("[VOICE_AUDIO_CONFIRMATION_TIMEOUT]", error_type=last_error)
    if next_action.action == ActionType.COMPLETE:
        return await complete_without_audio_confirmation("farewell_audio_unconfirmed")
    return record("audio_confirmation_timeout", error_type=last_error)
