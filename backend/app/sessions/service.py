"""Interview Session Service — creates sessions, starts agents, returns candidate credentials."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import structlog

from app.sessions.models import InterviewSession, InterviewConfiguration, SessionStatus
from app.sessions.store import SessionStore, session_store as _default_store
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError

logger = structlog.stdlib.get_logger("intra_ai.sessions.service")

# Default start window: candidate may enter 10 minutes before scheduled time
_DEFAULT_START_WINDOW_MINUTES = 10


class InterviewSessionService:
    """Orchestrates interview session lifecycle from configuration to candidate entry."""

    def __init__(
        self,
        store: Optional[SessionStore] = None,
    ) -> None:
        self._store = store or _default_store

    # ── Session creation ──────────────────────────────────────────────────────

    def create_session(self, config: InterviewConfiguration) -> InterviewSession:
        """Create (or idempotently return) an InterviewSession from the platform config."""
        return self._store.create(config)

    def get_session(self, interview_id: str) -> Optional[InterviewSession]:
        """Return session or None."""
        return self._store.get(interview_id)

    def require_session(self, interview_id: str) -> InterviewSession:
        """Return session or raise NotFoundError."""
        session = self._store.get(interview_id)
        if session is None:
            raise NotFoundError(
                f"No interview session found for interview_id='{interview_id}'. "
                "Create one first via POST /api/v1/sessions."
            )
        return session

    # ── Session start ─────────────────────────────────────────────────────────

    async def start_session(
        self,
        interview_id: str,
        start_window_minutes: int = _DEFAULT_START_WINDOW_MINUTES,
    ) -> dict[str, Any]:
        async with self._store.get_lock(interview_id):
            return await self._start_session_locked(interview_id, start_window_minutes)

    async def _start_session_locked(
        self,
        interview_id: str,
        start_window_minutes: int,
    ) -> dict[str, Any]:
        """Validate time window, start all required agents, return candidate Agora credentials.

        Steps:
        1. Resolve session (raises NotFoundError if missing).
        2. Validate scheduled time window.
        3. If already IN_PROGRESS, return existing credentials (idempotent).
        4. Mark session as STARTING.
        5. Generate candidate Agora RTC token for the session channel.
        6. Start or revalidate the active agent via AgoraAgentService.
        7. Mark session IN_PROGRESS.
        8. Return SessionStartResponse data.
        """
        from app.services.agora_agent_service import agora_agent_service
        session = self.require_session(interview_id)
        previous_status = session.status
        previous_agents = dict(session.started_agents)

        # ── Already running — revalidate the cloud agent ────────────────────
        # Agora can stop an agent independently after its idle timeout while
        # this in-memory session still says IN_PROGRESS. Re-dispatching the
        # active agent is safe: Agora returns 409 with the existing agent when
        # it is alive, and starts a replacement when it has stopped. This makes
        # refresh/retry recover a lobby instead of returning stale credentials.
        if session.status == SessionStatus.IN_PROGRESS:
            logger.info(
                "[SESSION_REVALIDATING_AGENT]",
                interview_id=interview_id,
                channel=session.channel_name,
            )

        if session.status == SessionStatus.CANCELLED:
            raise ValidationError(f"Interview session '{interview_id}' has been cancelled.")

        if session.status == SessionStatus.COMPLETED:
            raise ValidationError(f"Interview session '{interview_id}' is already completed.")

        # ── Time window validation ────────────────────────────────────────────
        can_start, reason = session.is_startable(start_window_minutes)
        if not can_start:
            raise ValidationError(f"Interview is not yet open: {reason}")

        # ── Generate candidate Agora token ───────────────────────────────────
        app_id = (settings.AGORA_APP_ID or "").strip()
        app_certificate = (settings.AGORA_APP_CERTIFICATE or "").strip()
        if not app_id or not app_certificate:
            raise ValidationError("Agora App ID and App Certificate must be configured to start an interview")
        channel_name = session.channel_name
        candidate_uid = 0
        token_expire_duration = 3600  # 1 hour in seconds (duration, not timestamp)
        rtm_user_id = f"cand_{session.candidate_id}"

        candidate_token = self._build_candidate_token(
            session=session,
            app_id=app_id,
            app_certificate=app_certificate,
            candidate_uid=candidate_uid,
            token_expire_duration=token_expire_duration,
        )

        # ── Mark STARTING ─────────────────────────────────────────────────────
        session.status = SessionStatus.STARTING
        self._store.set(session)

        logger.info(
            "[SESSION_STARTING]",
            interview_id=interview_id,
            channel=channel_name,
            selected_agents=session.agent_ids,
        )

        # Hydrate identity and JD/CV state before cloud startup can trigger a
        # callback. Retries reuse this context, preserving all prior evidence.
        from app.interview_context.store import interview_session_store as ctx_store
        self._prepare_context_metadata(session)
        initial_context = ctx_store.get_or_create(
            interview_id=channel_name,
            candidate_id=session.candidate_id,
            agent_id=session.current_agent_id,
            round_id=session.metadata["current_round_id"],
            missing_competencies=list(session.metadata["required_competencies"]),
            metadata=session.metadata,
        )
        ctx_store.register_alias(session.interview_id, channel_name)
        cv = initial_context.metadata.get("candidate_profile") or {}
        logger.info(
            "[SESSION_CONTEXT_READY]", interview_id=interview_id, channel=channel_name,
            candidate_id=session.candidate_id, configured_agents=session.agent_ids,
            resume_id=initial_context.metadata.get("resume_id"), job_id=initial_context.metadata.get("job_id"),
            candidate_name_available=bool(cv.get("name") or cv.get("first_name")
                                          or initial_context.metadata.get("candidate_name")),
            candidate_skills_count=len(cv.get("skills") or []),
            candidate_projects_count=len(cv.get("projects") or []),
            candidate_experience_count=len(cv.get("experience") or []),
            job_description_loaded=bool(initial_context.metadata.get("job_description")),
            job_required_skills_count=len(initial_context.metadata.get("required_skills") or []),
        )

        # ── Start the INITIAL active agent ONLY ───────────────────────────────
        # DO NOT start all agents in session.agent_ids concurrently, as this causes
        # identity mismatch and overlapping static greetings in the Agora channel.
        started_agents: dict[str, str] = {}
        errors: list[str] = []
        agent_id = session.current_agent_id

        try:
            from app.custom_llm.adapter import generate_opening_question
            from app.agents.registry import agent_registry
            greeting = generate_opening_question(agent_registry.get_profile(agent_id), initial_context)
            # Agora can call the adapter before /join returns. Its native TTS
            # owns this opening, so a concurrent blank handshake must stay silent.
            initial_context.metadata["native_greeting_pending"] = True
            result = await agora_agent_service.start_interview_agent(
                interview_id=channel_name,  # use channel as the Agora channel
                agent_id=agent_id,
                user_uid=candidate_uid,
                greeting_text=greeting,
            )
            if result.get("status") != "started":
                errors.append(result.get("error") or f"Agora agent '{agent_id}' did not start")
            else:
                agora_id = result.get("agora_agent_id", "")
                started_agents[agent_id] = agora_id
                from app.orchestrator.service import MetaOrchestrator
                from app.agents.models import NextAction
                from app.models.enums import ActionType
                if agora_id != previous_agents.get(agent_id):
                    profile = agent_registry.get_profile(agent_id)
                    opening_competency = next(
                        (c for c in initial_context.missing_competencies if c in profile.focal_competencies),
                        next(iter(profile.focal_competencies), "general"),
                    )
                    initial_context.metadata["active_interviewer_question"] = greeting
                    MetaOrchestrator.record_question(initial_context, NextAction(
                        action=ActionType.ASK_QUESTION, target_agent_id=agent_id,
                        competency=opening_competency,
                        difficulty=initial_context.difficulty, question_text=greeting))

                logger.info(
                    "[AGENT_START]",
                    interview_id=interview_id,
                    agent_id=agent_id,
                    channel=channel_name,
                    agora_agent_id=agora_id,
                )
        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "[AGENT_START_FAILED]",
                interview_id=interview_id,
                agent_id=agent_id,
                error=error_msg,
            )
            errors.append(f"{agent_id}: {error_msg}")
        finally:
            initial_context.metadata.pop("native_greeting_pending", None)

        # A session without its initial interviewer cannot provide a usable
        # candidate experience. Keep it retryable and surface a real failure
        # instead of returning a false-positive IN_PROGRESS response.
        if errors or not started_agents:
            session.status = previous_status if previous_agents else SessionStatus.READY
            session.started_agents = previous_agents
            self._store.set(session)
            raise ValidationError("Unable to start the interview agent: " + "; ".join(errors))

        # ── Mark IN_PROGRESS ──────────────────────────────────────────────────
        session.status = SessionStatus.IN_PROGRESS
        session.started_agents = started_agents
        session.started_at = session.started_at or datetime.now(timezone.utc)
        self._store.set(session)

        logger.info(
            "[SESSION_STARTED]",
            interview_id=interview_id,
            channel=channel_name,
            agents_started=list(started_agents.keys()),
            agent_errors=errors,
        )

        response = self._build_start_response(session)
        response["agora_token"] = candidate_token
        response["agora_app_id"] = app_id
        response["agora_uid"] = candidate_uid
        response["rtm_user_id"] = rtm_user_id
        if errors:
            response["agent_start_warnings"] = errors
        return response

    # ── Session stop ──────────────────────────────────────────────────────────

    async def stop_session(
        self, interview_id: str, *, expected_agora_agent_id: str | None = None,
        expected_voice_request_id: str | None = None,
    ) -> dict[str, Any]:
        """Stop all active agents and mark session as COMPLETED."""
        async with self._store.get_lock(interview_id):
            session = self.require_session(interview_id)
            if expected_agora_agent_id and session.started_agents.get(session.current_agent_id) != expected_agora_agent_id:
                if session.started_agents or expected_agora_agent_id not in session.metadata.get("confirmed_stopped_agora_agents", []):
                    return {"status": "stale", "interview_id": session.interview_id}
            if not self._owns_voice_action(session, "COMPLETE", expected_voice_request_id):
                return {"status": "stale", "interview_id": session.interview_id}
            result = await self._stop_session_locked(session)
        from app.sessions.completion import persist_completed_interview
        completion = await persist_completed_interview(session.interview_id)
        session.metadata.update(completion)
        result.update(completion)
        return result

    async def _stop_session_locked(self, session: InterviewSession) -> dict[str, Any]:
        from app.services.agora_agent_service import agora_agent_service

        stopped_agents: list[str] = []
        errors: list[str] = []
        for agent_id, agora_agent_id in list(session.started_agents.items()):
            try:
                result = await agora_agent_service.stop_interview_agent(
                    interview_id=session.channel_name,
                    agent_id=agent_id,
                    agora_agent_id=agora_agent_id or None,
                )
                if result.get("status") != "stopped":
                    raise ValidationError(result.get("error") or f"Stop not confirmed for '{agent_id}'")
                stopped_agents.append(agent_id)
                session.started_agents.pop(agent_id, None)
                self._remember_stopped_agent(session, agora_agent_id)
                logger.info(
                    "[AGENT_STOP]",
                    interview_id=session.interview_id,
                    agent_id=agent_id,
                    channel=session.channel_name,
                )
            except Exception as exc:
                errors.append(f"{agent_id}: {exc}")
                logger.warning("[AGENT_STOP_FAILED]", agent_id=agent_id, error=str(exc))

        if errors:
            session.metadata["agent_stop_error"] = "; ".join(errors)
            self._store.set(session)
            raise ValidationError("Unable to stop interview audio: " + "; ".join(errors))

        session.status = SessionStatus.COMPLETED
        session.metadata.pop("agent_stop_error", None)
        self._store.set(session)
        from app.interview_context.store import interview_session_store as ctx_store
        context = ctx_store.get(session.channel_name)
        if context:
            context.metadata["completed"] = True
            context.metadata.pop("pending_voice_action", None)
            if context.metadata.get("completion_reason"):
                session.metadata["completion_reason"] = context.metadata["completion_reason"]

        return {
            "interview_id": session.interview_id,
            "channel_name": session.channel_name,
            "status": session.status,
            "stopped_agents": stopped_agents,
        }

    async def handoff_agent(
        self, interview_id: str, target_agent_id: str, *,
        greeting_text: str | None = None,
        expected_agora_agent_id: str | None = None,
        expected_voice_request_id: str | None = None,
    ) -> dict[str, Any]:
        """Stop the old voice before starting the next in the same channel."""
        async with self._store.get_lock(interview_id):
            session = self.require_session(interview_id)
            if session.status != SessionStatus.IN_PROGRESS:
                raise ValidationError("An agent handoff requires an active interview")
            if expected_agora_agent_id and session.started_agents.get(session.current_agent_id) != expected_agora_agent_id:
                return {"status": "stale", "interview_id": session.interview_id}
            if not self._owns_voice_action(session, "SWITCH_AGENT", expected_voice_request_id):
                return {"status": "stale", "interview_id": session.interview_id}
            result = await self._handoff_agent_locked(session, target_agent_id, greeting_text, expected_voice_request_id)
        # A candidate END can supersede the handoff while its leave/join HTTP
        # request is in flight. Persist that completion through the same path
        # as the normal COMPLETE lifecycle, outside the meeting lock.
        if result.get("session_status") == SessionStatus.COMPLETED:
            from app.sessions.completion import persist_completed_interview
            completion = await persist_completed_interview(session.interview_id)
            session.metadata.update(completion)
            result.update(completion)
        return result

    async def _handoff_agent_locked(
        self, session: InterviewSession, target_agent_id: str, greeting_text: str | None,
        expected_voice_request_id: str | None,
    ) -> dict[str, Any]:
        from app.services.agora_agent_service import agora_agent_service
        from app.agents.registry import agent_registry

        if session.status != SessionStatus.IN_PROGRESS:
            raise ValidationError("An agent handoff requires an active interview")
        target = target_agent_id.strip().lower()
        if target not in session.agent_ids:
            raise ValidationError(f"Agent '{target}' is not configured for this session")
        if not agent_registry.has_agent(target):
            raise ValidationError(f"Agent '{target}' is not registered")
        current = session.current_agent_id
        if current == target:
            return {"status": "unchanged", "current_agent_id": current}

        # This method is called after outgoing speech is drained. A cloud
        # leave must succeed before dispatching the next voice. Never allow a
        # failed leave or retry to create two active interviewers.
        for old_agent, old_agora_id in list(session.started_agents.items()):
            stopped = await agora_agent_service.stop_interview_agent(
                interview_id=session.channel_name,
                agent_id=old_agent,
                agora_agent_id=old_agora_id,
            )
            if stopped.get("status") != "stopped":
                raise ValidationError(stopped.get("error") or f"Stop not confirmed for '{old_agent}'")
            session.started_agents.pop(old_agent, None)
            self._remember_stopped_agent(session, old_agora_id)
            if not self._owns_voice_action(session, "SWITCH_AGENT", expected_voice_request_id):
                return await self._finish_superseded_handoff_locked(session)

        try:
            started = await agora_agent_service.start_interview_agent(
                interview_id=session.channel_name,
                agent_id=target,
                user_uid=0,
                greeting_text=greeting_text if greeting_text is not None else "",
            )
            if started.get("status") != "started" or not started.get("agora_agent_id"):
                raise ValidationError(started.get("error") or f"Unable to start agent '{target}'")
        except Exception:
            # The old voice is stopped; retain its logical context and expose
            # a retryable meeting instead of claiming the handoff succeeded.
            if self._completion_requested(session):
                return await self._finish_superseded_handoff_locked(session)
            session.status = SessionStatus.READY
            self._store.set(session)
            raise

        # Record the returned physical generation before the ownership check.
        # If END won during join, cleanup must stop this voice even though the
        # logical interviewer must remain unchanged.
        session.started_agents[target] = started.get("agora_agent_id", "")
        if not self._owns_voice_action(session, "SWITCH_AGENT", expected_voice_request_id):
            return await self._finish_superseded_handoff_locked(session)
        session.current_agent_id = target
        self._store.set(session)
        from app.interview_context.store import interview_session_store as ctx_store
        context = ctx_store.get(session.channel_name)
        if context:
            context.switch_agent(target, validate_registry=True)
            from app.models.enums import DifficultyLevel
            levels = list(DifficultyLevel)
            profile = agent_registry.get_profile(target)
            bounded_index = min(
                max(levels.index(context.difficulty), levels.index(profile.min_difficulty)),
                levels.index(profile.max_difficulty),
            )
            context.set_difficulty(levels[bounded_index])
            context.metadata.pop("pending_voice_action", None)
        # Record only a confirmed physical handoff whose action still owns the
        # session. Failed, stale, unchanged and superseded paths return above.
        handoff = {
            "from_agent_id": current, "to_agent_id": target, "status": "completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "round_id": context.current_round_id if context else session.metadata.get("current_round_id"),
        }
        for metadata in (session.metadata, context.metadata if context else None):
            if metadata is not None:
                previous = metadata.get("handoff_history")
                # Copy the list because session/context metadata may share a
                # pre-existing list; one commit must append exactly one event.
                metadata["handoff_history"] = [*(previous if isinstance(previous, list) else []), dict(handoff)]
        logger.info(
            "[AGENT_HANDOFF_COMPLETED]",
            interview_id=session.interview_id,
            channel=session.channel_name,
            agora_agent_id=started.get("agora_agent_id"),
            from_agent=current,
            to_agent=target,
        )
        return {
            "status": "switched",
            "interview_id": session.interview_id,
            "channel_name": session.channel_name,
            "from_agent_id": current,
            "current_agent_id": target,
            "agora_agent_id": started.get("agora_agent_id"),
        }

    async def _finish_superseded_handoff_locked(self, session: InterviewSession) -> dict[str, Any]:
        """Reconcile physical agents after the candidate supersedes a switch."""
        if self._completion_requested(session):
            result = await self._stop_session_locked(session)
            session.metadata["completion_audio_note"] = "handoff_voice_already_stopped"
            logger.info("[HANDOFF_SUPERSEDED_BY_COMPLETE]", interview_id=session.interview_id, channel=session.channel_name)
            return {
                "status": "superseded", "reason": "completion_requested_during_handoff",
                "interview_id": session.interview_id, "session_status": session.status,
                "completion_result": result,
            }
        # A newer non-completion owner must keep its pending metadata. Any
        # newly dispatched obsolete voice is stopped without committing it.
        from app.services.agora_agent_service import agora_agent_service
        for agent_id, cloud_id in list(session.started_agents.items()):
            stopped = await agora_agent_service.stop_interview_agent(
                interview_id=session.channel_name, agent_id=agent_id, agora_agent_id=cloud_id,
            )
            if stopped.get("status") != "stopped":
                raise ValidationError(stopped.get("error") or "Unable to stop superseded interviewer")
            session.started_agents.pop(agent_id, None)
            self._remember_stopped_agent(session, cloud_id)
            if self._completion_requested(session):
                return await self._finish_superseded_handoff_locked(session)
        session.status = SessionStatus.READY
        self._store.set(session)
        return {"status": "superseded", "interview_id": session.interview_id}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _owns_voice_action(session: InterviewSession, action: str, request_id: str | None) -> bool:
        from app.interview_context.store import interview_session_store as contexts
        context = contexts.get(session.channel_name)
        if not context:
            return True
        pending = context.metadata.get("pending_voice_action")
        owner = context.metadata.get("pending_voice_request_id")
        if action != "COMPLETE" and context.metadata.get("completed"):
            return False
        return (not pending or pending == action) and (not request_id or not owner or owner == request_id)

    @staticmethod
    def _completion_requested(session: InterviewSession) -> bool:
        from app.interview_context.store import interview_session_store as contexts
        context = contexts.get(session.channel_name)
        return bool(context and (context.metadata.get("completed") or context.metadata.get("pending_voice_action") == "COMPLETE"))

    @staticmethod
    def _remember_stopped_agent(session: InterviewSession, cloud_id: str) -> None:
        confirmed = session.metadata.setdefault("confirmed_stopped_agora_agents", [])
        if cloud_id and cloud_id not in confirmed:
            confirmed.append(cloud_id)
            del confirmed[:-16]

    @staticmethod
    def _prepare_context_metadata(session: InterviewSession) -> None:
        """Carry JD/CV identity and configured interview objectives into M1.

        Required technologies (Python, React, etc.) stay in the JD; they are
        not competency IDs used by the registry's routing policy.
        """
        from app.agents.registry import agent_registry
        from app.services.round_agents import decode_round_agents
        import re

        metadata = session.metadata
        # Recruiter scheduling supplies parsed_resume; platform integrations may
        # supply candidate_profile. Give the opening, M1 and Agent Context the
        # same CV snapshot before the cloud agent can issue its first callback.
        raw_profile = metadata.get("candidate_profile") or metadata.get("parsed_resume") or {}
        if isinstance(raw_profile, list):
            raw_profile = raw_profile[0] if raw_profile else {}
        if isinstance(raw_profile, dict):
            nested = raw_profile.get("parsed_resume")
            profile = dict(nested if isinstance(nested, dict) else raw_profile)
            for field in ("name", "first_name", "email"):
                value = metadata.get(f"candidate_{field}") or raw_profile.get(field) or profile.get(field)
                if value:
                    profile[field] = value
            for field in ("skills", "experience", "education", "projects"):
                if not isinstance(profile.get(field), list):
                    profile[field] = list(metadata.get(f"candidate_{field}") or [])
            metadata["candidate_profile"] = profile
        metadata["job_title"] = metadata.get("job_title") or session.job_title
        metadata["company"] = metadata.get("company") or session.company
        metadata["configured_agent_ids"] = list(session.agent_ids)
        metadata["allowed_agent_ids"] = list(session.agent_ids)
        rounds = metadata.get("round_configs") or metadata.get("interview_rounds") or []
        active_rounds = sorted(
            [r for r in rounds if isinstance(r, dict) and r.get("is_active", r.get("enabled", True))],
            key=lambda r: r.get("order_index", 0),
        )
        first_round = active_rounds[0] if active_rounds else None
        first_type = (first_round or {}).get("type") or next((r for r in rounds if isinstance(r, str) and r), None)
        metadata["current_round_id"] = metadata.get("current_round_id") or first_type or "technical"

        profile_competencies = list(dict.fromkeys(
            competency
            for agent_id in session.agent_ids
            for competency in agent_registry.get_profile(agent_id).focal_competencies
        ))
        normalize = lambda value: re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
        explicit = metadata.get("required_competencies") or []
        round_focus = [focus for r in active_rounds for focus in decode_round_agents(r)[1]]
        objectives = explicit or round_focus or profile_competencies
        aliases = {
            normalize(alias): normalize(target)
            for agent_id in session.agent_ids
            for alias, target in agent_registry.get_profile(agent_id).metadata.get("competency_aliases", {}).items()
            if normalize(target) in agent_registry.get_profile(agent_id).focal_competencies
        }
        normalized = list(dict.fromkeys(normalize(value) for value in objectives if normalize(value)))
        metadata["required_competencies"] = list(dict.fromkeys(aliases.get(value, value) for value in normalized))
        mapped = {value: aliases[value] for value in normalized if value in aliases}
        if mapped:
            metadata["competency_aliases_applied"] = mapped
        metadata["unassigned_competencies"] = [value for value in metadata["required_competencies"] if value not in profile_competencies]

    @staticmethod
    def _build_candidate_token(
        session: InterviewSession,
        app_id: str,
        app_certificate: str,
        candidate_uid: int,
        token_expire_duration: int,
    ) -> str:
        from app.core.agora_token2 import RtcTokenBuilder2

        try:
            return RtcTokenBuilder2.build_token_with_uid(
                app_id=app_id,
                app_certificate=app_certificate,
                channel_name=session.channel_name,
                uid=candidate_uid,
                role=1,
                expire_seconds=token_expire_duration,
                rtm_user_id=f"cand_{session.candidate_id}",
            )
        except Exception as exc:
            raise ValidationError(f"Failed to generate Agora token: {exc}") from exc

    def _build_start_response(
        self,
        session: InterviewSession,
        include_credentials: bool = False,
    ) -> dict[str, Any]:
        """Build the SessionStartResponse dict, regenerating credentials on retries."""
        from app.agents.registry import agent_registry

        selected_agents = []
        for aid in session.agent_ids:
            try:
                profile, mapping = agent_registry.get_agent(aid)
                selected_agents.append({
                    "agent_id": profile.agent_id,
                    "name": profile.display_name,
                    "role": profile.role,
                    "description": profile.description,
                    "focal_competencies": profile.focal_competencies,
                    "agora_rtc_uid": int(mapping.agent_rtc_uid) if mapping.agent_rtc_uid else None,
                })
            except Exception:
                selected_agents.append({"agent_id": aid, "name": aid.title(), "role": "Interviewer"})

        response = {
            "interview_id": session.interview_id,
            "channel_name": session.channel_name,
            "candidate_id": session.candidate_id,
            "selected_agents": selected_agents,
            "current_agent_id": session.current_agent_id,
            "agent_ids": session.agent_ids,
            "session_status": session.status,
            "duration_minutes": session.duration_minutes,
            "job_title": session.job_title,
            "company": session.company,
            "scheduled_start": session.scheduled_start.isoformat() if session.scheduled_start else None,
            "expires_in": 3600,
        }
        if include_credentials:
            app_id = (settings.AGORA_APP_ID or "").strip()
            app_certificate = (settings.AGORA_APP_CERTIFICATE or "").strip()
            if not app_id or not app_certificate:
                raise ValidationError("Agora App ID and App Certificate must be configured to start an interview")
            response.update(
                {
                    "agora_app_id": app_id,
                    "agora_uid": 0,
                    "rtm_user_id": f"cand_{session.candidate_id}",
                    "agora_token": self._build_candidate_token(
                        session, app_id, app_certificate, 0, 3600
                    ),
                }
            )
        return response


# Global singleton
interview_session_service = InterviewSessionService()
