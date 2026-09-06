"""Authenticated lifecycle and controlled tools for Taylor and Morgan only."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import secrets
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import structlog

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.voice import authorization as auth
from app.voice.agora import AgoraProjectConfig, TrainingHRAgoraService, AuxiliaryAgoraError
from app.voice.context import authorized_context, system_prompt, taylor_prompt, taylor_greeting
from app.voice.models import DashboardContext, PracticeOptions, VoiceSession, utc_now
from app.voice.security import issue_mcp_token
from app.voice.store import VoiceSessionStore, RedisPendingStore
from app.voice.tools import VoiceToolService, tool_schemas, WRITE_TOOLS

logger = structlog.stdlib.get_logger("intra_ai.voice")


class VoiceServiceUnavailable(AppError):
    status_code = 503
    code = "VOICE_UNAVAILABLE"
    message = "The voice assistant is temporarily unavailable. Please retry."


class VoiceAssistantService:
    def __init__(self, supabase, redis, *, agora=None, store=None, tools=None):
        self.sb = supabase
        self.store = store or VoiceSessionStore(redis)
        self.agora = agora or TrainingHRAgoraService(AgoraProjectConfig.from_settings(settings))
        self.tools = tools or VoiceToolService(supabase, pending_store=RedisPendingStore(redis))
        self._reaper: asyncio.Task | None = None
        self._last_cloud_check: dict[str, float] = {}
        self._confirmation_tasks: dict[str, asyncio.Task] = {}

    @staticmethod
    def allowed_tools(persona: str) -> list[str]:
        if persona == "taylor":
            return []
        return ["get_dashboard_context", "get_action_status"] + [t["name"] for t in tool_schemas()]

    @staticmethod
    def _mcp_endpoint() -> str:
        value = settings.VOICE_ASSISTANT_PUBLIC_URL.rstrip("/")
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in {"", "/"}):
            raise VoiceServiceUnavailable("Configure the public HTTPS backend URL for assistant tools.")
        return value + "/api/v1/voice/mcp"

    async def start(self, persona: str, claims: dict, ids: DashboardContext,
                    practice: PracticeOptions | None = None) -> dict:
        if persona not in {"taylor", "morgan"}:
            raise NotFoundError("Voice assistant not found")
        actor = await auth.identity(claims, self.sb)
        if persona != "taylor" and practice is not None:
            raise ValidationError("Practice options are available to Taylor only")
        context = await authorized_context(actor, ids, self.sb, persona)
        endpoint = self._mcp_endpoint() if persona == "morgan" else None
        first_name = actor.name.split()[0] if actor.name.split() else ""
        practice = (practice or PracticeOptions()) if persona == "taylor" else None
        prompt = taylor_prompt(first_name, context, practice) if persona == "taylor" else system_prompt(persona, first_name, context)
        async with self.store.lock("start:" + actor.user_id + ":" + persona):
            for sid in await self.store.active_ids():
                existing = await self.store.get(sid)
                if existing and existing.user_id == actor.user_id and existing.persona == persona:
                    if existing.expires_at <= utc_now() or existing.status == "ERROR":
                        await self._end(existing, "expired")
                    elif existing.status in {"CONNECTING", "CONNECTED", "EXECUTING"}:
                        raise ConflictError("This assistant already has an active session. End it before starting another.")
            sid = str(uuid4())
            agent = self.agora.project.agent(persona)
            uid = secrets.randbelow(0x7FFFFFFF) + 1
            while str(uid) in {self.agora.project.taylor.agent_rtc_uid, self.agora.project.morgan.agent_rtc_uid}:
                uid = secrets.randbelow(0x7FFFFFFF) + 1
            ttl = min(1800, max(120, settings.VOICE_ASSISTANT_SESSION_SECONDS))
            session = VoiceSession(session_id=sid, user_id=actor.user_id, role=actor.role,
                tenant_id=actor.tenant_id, persona=persona,
                agent_type="TAYLOR_TRAINING" if persona == "taylor" else "MORGAN_HR",
                channel_name=f"{persona}_{uuid4().hex}", rtc_uid=uid,
                agent_rtc_uid=agent.agent_rtc_uid, expires_at=utc_now() + timedelta(seconds=ttl),
                dashboard_context=ids, practice=practice)
            await self.store.put(session)
            logger.info(f"{persona}_session_created", session_id=sid, user_id=actor.user_id,
                        tenant_id=actor.tenant_id, project="training_hr")
            try:
                logger.info(f"{persona}_agora_join_requested", session_id=sid, channel=session.channel_name)
                options = {"system_prompt": prompt, "expires_in": ttl}
                if persona == "morgan":
                    options.update(mcp_endpoint=endpoint, mcp_authorization="Bearer " + issue_mcp_token(session),
                                   allowed_tools=self.allowed_tools(persona))
                    logger.info("morgan_context_preloaded", session_id=sid,
                                selected_resources=[kind for kind in ("candidate", "application", "job", "interview") if kind in context],
                                prompt_characters=len(prompt))
                else:
                    options["greeting_message"] = taylor_greeting(first_name, context, practice)
                    logger.info("taylor_context_preloaded", session_id=sid, has_cv=bool(context.get("cv_claims_not_verified_evidence")),
                                has_job="job" in context, prompt_characters=len(prompt))
                result = await self.agora.start_agent(persona, session.channel_name, uid, f"{persona}-{sid}", **options)
                session.cloud_agent_id = result["agent_id"]
                if result["status"] in {"FAILED", "STOPPED"}:
                    raise VoiceServiceUnavailable("The voice agent did not start. Please retry.")
                credentials = self.agora.candidate_credentials(session.channel_name, uid, expires_in=ttl)
                session.status = "CONNECTED"
                await self.store.put(session)
            except BaseException as exc:
                # A cancelled request must not orphan a billable cloud agent.
                if session.cloud_agent_id:
                    try:
                        await asyncio.shield(self.agora.stop_agent(persona, session.channel_name, session.cloud_agent_id))
                        session.cloud_agent_id = None
                    except Exception:
                        logger.error(f"{persona}_cleanup_pending", session_id=sid)
                session.status = "ERROR"
                session.error_code = "VOICE_START_FAILED"
                logger.warning(f"{persona}_session_failed", session_id=sid, phase="start",
                               error_type=type(exc).__name__,
                               provider_status=getattr(exc, "provider_status", None))
                try:
                    await asyncio.shield(self.store.put(session))
                except Exception:
                    logger.error(f"{persona}_state_write_failed", session_id=sid)
                raise
            logger.info(f"{persona}_agora_joined", session_id=sid, agent_id=session.cloud_agent_id,
                        channel=session.channel_name)
            return {**session.public(), "app_id": credentials["app_id"],
                    "channel_name": session.channel_name, "rtc_uid": uid,
                    "rtc_token": credentials["rtc_token"], "rtm_token": credentials["rtm_token"],
                    "rtm_user_id": str(uid), "agent_rtc_uid": session.agent_rtc_uid}

    async def owned(self, sid: str, claims: dict, *, active: bool = False) -> tuple[VoiceSession, auth.Actor]:
        session = await self.store.get(sid)
        if session is None:
            raise NotFoundError("Voice session not found")
        actor = await auth.identity(claims, self.sb)
        if (session.user_id, session.role, session.tenant_id) != (actor.user_id, actor.role, actor.tenant_id):
            raise ForbiddenError("This voice session belongs to another user or workspace")
        if active and (session.status in {"ERROR", "DISCONNECTED"} or session.expires_at <= utc_now()):
            raise ConflictError("The voice session has ended. Start a new session.")
        return session, actor

    async def get(self, sid: str, claims: dict, *, heartbeat: bool = False) -> dict:
        async with self.store.lock(sid):
            session, _ = await self.owned(sid, claims)
            now = utc_now()
            if session.status != "DISCONNECTED" and session.expires_at <= now:
                await self._end(session, "expired")
            elif session.status != "DISCONNECTED" and session.cloud_agent_id:
                if now.timestamp() - self._last_cloud_check.get(sid, 0) >= 15:
                    try:
                        state = await self.agora.query_agent(session.persona, session.channel_name, session.cloud_agent_id)
                        if state["status"] in {"STOPPED", "FAILED"}:
                            session.status = "DISCONNECTED"
                            session.ended_at = now
                    except AuxiliaryAgoraError as exc:
                        if exc.provider_status == 404:
                            session.status = "DISCONNECTED"
                            session.ended_at = now
                        else:
                            raise
                    self._last_cloud_check[sid] = now.timestamp()
            if session.status == "DISCONNECTED":
                session.pending_action = None
                self.tools.discard_session(sid)
                self._last_cloud_check.pop(sid, None)
            if heartbeat and session.status not in {"DISCONNECTED", "ERROR"}:
                session.heartbeat_at = now
            await self._authorize_action_view(session, claims)
            await self.store.put(session)
            return session.public()

    async def _authorize_action_view(self, session: VoiceSession, claims: dict) -> None:
        """Saved proposals can target resources outside the current dashboard."""
        await self._sync_execution(session, claims)
        for field, reader in (("pending_action", self.tools.read_pending),
                              ("last_tool_result", self.tools.read_result)):
            value = getattr(session, field)
            if value and value.get("confirmation_id"):
                try:
                    if field == "last_tool_result" and value.get("status") == "executing":
                        # _sync_execution already checked either the durable
                        # running receipt or the authorized pre-dispatch review.
                        continue
                    await reader(value["confirmation_id"], user_claims=claims,
                                 session_id=session.session_id, persona=session.persona)
                except NotFoundError:
                    # An expired proposal is no longer actionable or displayable.
                    setattr(session, field, None)
                except ConflictError:
                    if field != "pending_action":
                        raise
                    # An invalidated or otherwise consumed proposal may still
                    # occupy the session view after a worker/restart boundary.
                    # Only its authorized durable receipt can replace it.
                    try:
                        session.last_tool_result = await self.tools.read_result(value["confirmation_id"],
                            user_claims=claims, session_id=session.session_id, persona=session.persona)
                    except NotFoundError:
                        pass
                    session.pending_action = None

    async def update_context(self, sid: str, claims: dict, ids: DashboardContext) -> dict:
        async with self.store.lock(sid):
            session, actor = await self.owned(sid, claims, active=True)
            if session.persona == "taylor":
                raise ConflictError("Start a new practice session to change its CV or target role")
            await authorized_context(actor, ids, self.sb, session.persona)
            session.dashboard_context = ids
            # An existing confirmation keeps its immutable resource; clear it
            # from the view on navigation so it cannot be mistaken for this page.
            session.pending_action = None
            if not session.last_tool_result or session.last_tool_result.get("status") != "executing":
                session.last_tool_result = None
            await self.store.put(session)
            return session.public()

    async def end(self, sid: str, claims: dict) -> dict:
        async with self.store.lock(sid):
            session, _ = await self.owned(sid, claims)
            await self._end(session, "user_ended")
            # Ending remains possible after resource access changes. Preserve
            # saved execution/results but do not return unreauthorized data.
            visible = session.public()
            visible["last_tool_result"] = None
            return visible

    @staticmethod
    def _feedback_pending(session: VoiceSession) -> bool:
        return bool(session.persona == "taylor" and session.practice_feedback
                    and session.practice_feedback.get("status") == "requesting_feedback")

    async def _read_native_feedback(self, session: VoiceSession) -> dict | None:
        """One bounded history read; no model request and no session mutation."""
        from app.voice.feedback import feedback_from_history
        checkpoint = session.feedback_checkpoint
        if (not self._feedback_pending(session) or not session.cloud_agent_id
                or not checkpoint or checkpoint.get("request_id") != session.feedback_attempt_id):
            return None
        try:
            history = await asyncio.wait_for(self.agora.get_history(
                "taylor", session.channel_name, session.cloud_agent_id), timeout=4)
            return feedback_from_history(history, checkpoint)
        except Exception as exc:
            logger.info("taylor_feedback_recovery_pending", session_id=session.session_id,
                        error_type=type(exc).__name__)
            return None

    async def practice_feedback(self, sid: str, claims: dict) -> dict:
        from app.voice.feedback import outcome
        session, actor = await self.owned(sid, claims)
        if session.persona != "taylor" or actor.role != "candidate":
            raise ForbiddenError("Practice feedback is available to this candidate's Taylor session only")
        recovered = await self._read_native_feedback(session)
        if recovered is not None:
            # Recheck ownership and attempt identity after the provider await.
            return await self._finish_feedback(sid, session.feedback_attempt_id, recovered,
                                               "practice_feedback_recovered", claims=claims,
                                               agent_id=session.cloud_agent_id)
        if self._feedback_overdue(session):
            async with self.store.lock(sid):
                session, _ = await self.owned(sid, claims)
                if self._feedback_overdue(session):
                    await self._expire_feedback(session, read_history=False)
        return session.practice_feedback or outcome("unavailable", "Finish practice to request your feedback.")

    @staticmethod
    def _feedback_overdue(session: VoiceSession) -> bool:
        return bool(VoiceAssistantService._feedback_pending(session)
            # Legacy interrupted records have no trustworthy request deadline.
            and (session.feedback_deadline_at is None or session.feedback_deadline_at <= utc_now()))

    async def _save_feedback_outcome(self, session: VoiceSession, result: dict, reason: str) -> None:
        """Caller holds the session lock. Persist output before provider cleanup."""
        session.practice_feedback = result
        session.feedback_checkpoint = None
        session.feedback_deadline_at = None
        await self.store.put(session)
        try:
            await self._end(session, reason)
        except Exception:
            session.status = "ERROR"
            session.error_code = "VOICE_CLEANUP_PENDING"
            logger.warning("taylor_cleanup_pending", session_id=session.session_id)
        await self.store.put(session)

    async def _finish_feedback(self, sid: str, attempt_id: str | None, result: dict,
                               reason: str, *, claims: dict | None = None,
                               agent_id: str | None = None) -> dict:
        from app.voice.feedback import outcome
        if claims is not None:
            saved, actor = await self.owned(sid, claims)
            if actor.role != "candidate" or saved.persona != "taylor":
                raise ForbiddenError("Practice feedback is available to this candidate's Taylor session only")
        else:
            saved = await self.store.get(sid)
        if saved and saved.practice_feedback and not self._feedback_pending(saved):
            # A concurrent reader already committed the result and may still
            # hold the lock during slow provider cleanup. Reading it needs no
            # lock and must not wait for, or repeat, that cleanup.
            return saved.practice_feedback
        async with self.store.lock(sid):
            if claims is not None:
                session, actor = await self.owned(sid, claims)
                if actor.role != "candidate" or session.persona != "taylor":
                    raise ForbiddenError("Practice feedback is available to this candidate's Taylor session only")
            else:
                session = await self.store.get(sid)
            if session is None:
                return outcome("unavailable", "This practice session is no longer available.")
            if (session.feedback_attempt_id != attempt_id
                    or session.cloud_agent_id != agent_id
                    or not self._feedback_pending(session)):
                # A simultaneous poll, end, or newer attempt owns the result.
                # A late worker must never replace it or clean up another agent.
                return session.practice_feedback or outcome("unavailable", "This practice request is no longer current.")
            await self._save_feedback_outcome(session, result, reason)
            return session.practice_feedback

    async def _expire_feedback(self, session: VoiceSession, *, read_history: bool = True) -> None:
        from app.voice.feedback import outcome
        recovered = await self._read_native_feedback(session) if read_history else None
        result = recovered or outcome("unavailable", "Feedback was interrupted before a complete result was saved. No practice score was generated. Start a new practice session, answer at least two questions, then choose Finish & Get Feedback.")
        await self._save_feedback_outcome(session, result, "practice_feedback_deadline")

    async def finish_practice(self, sid: str, claims: dict) -> dict:
        from app.voice.feedback import generate_feedback, outcome
        session, actor = await self.owned(sid, claims)
        if session.persona != "taylor" or actor.role != "candidate":
            raise ForbiddenError("Practice feedback is available to this candidate's Taylor session only")
        if session.practice_feedback:
            return await self.practice_feedback(sid, claims)
        async with self.store.lock(sid):
            session, actor = await self.owned(sid, claims)
            if session.persona != "taylor" or actor.role != "candidate":
                raise ForbiddenError("Practice feedback is available to this candidate's Taylor session only")
            if session.practice_feedback:
                return session.practice_feedback
            if session.status in {"ERROR", "DISCONNECTED"} or not session.cloud_agent_id or session.expires_at <= utc_now():
                session.practice_feedback = outcome("unavailable", "This practice session has already ended. Use Finish & Get Feedback before leaving your next session.")
                if session.status != "DISCONNECTED":
                    await self._end(session, "practice_already_ended")
                await self.store.put(session)
                return session.practice_feedback
            session.practice_feedback = outcome("requesting_feedback", "Preparing feedback from your practice answers. If the connection is interrupted, this page will check the saved result without requesting another assessment.")
            session.feedback_attempt_id = str(uuid4())
            session.feedback_checkpoint = None
            session.feedback_deadline_at = utc_now() + timedelta(seconds=65)
            session.status = "EXECUTING"
            session.heartbeat_at = utc_now()
            await self.store.put(session)
        # Do not hold Redis's 60-second lock over native generation. A restarted
        # worker can read output before the cloud agent's idle timeout instead
        # of waiting for an orphaned lock to expire. The attempt UUID is a fence.
        attempt_id = session.feedback_attempt_id

        async def persist_checkpoint(checkpoint: dict) -> None:
            async with self.store.lock(sid):
                current, actor = await self.owned(sid, claims)
                if (actor.role != "candidate" or current.persona != "taylor"
                        or current.feedback_attempt_id != attempt_id
                        or current.cloud_agent_id != session.cloud_agent_id
                        or not self._feedback_pending(current)):
                    raise ConflictError("This practice request is no longer current")
                current.feedback_checkpoint = checkpoint
                await self.store.put(current)

        started = utc_now()
        logger.info("taylor_feedback_requested", session_id=sid)
        try:
            result = await asyncio.wait_for(generate_feedback(self.agora, session,
                request_id=attempt_id, persist_checkpoint=persist_checkpoint), timeout=35)
            logger.info("taylor_feedback_completed", session_id=sid,
                        status=result["status"],
                        elapsed_ms=round((utc_now() - started).total_seconds() * 1000))
        except asyncio.CancelledError:
            # A shutdown or lost HTTP worker must not stop the cloud agent or
            # destroy its already-generated output. GET/reaper recover this
            # single saved request; they never replay /think. The deadline
            # still guarantees cleanup if no complete response is available.
            logger.info("taylor_feedback_interrupted", session_id=sid,
                        recovery="native_history_only")
            raise
        except Exception as exc:
            logger.warning("taylor_feedback_unavailable", session_id=sid, error_type=type(exc).__name__)
            result = outcome("unavailable", "Taylor could not complete your feedback this time. No practice score was generated. Start a new practice session, answer at least two questions, then choose Finish & Get Feedback.")
        return await asyncio.shield(self._finish_feedback(sid, attempt_id, result, "practice_finished",
                                                          agent_id=session.cloud_agent_id))

    async def _end(self, session: VoiceSession, reason: str) -> None:
        if session.status == "DISCONNECTED":
            return
        if session.cloud_agent_id:
            await self.agora.stop_agent(session.persona, session.channel_name, session.cloud_agent_id)
        session.status = "DISCONNECTED"
        session.ended_at = utc_now()
        session.pending_action = None
        if session.practice_feedback and session.practice_feedback.get("status") == "requesting_feedback":
            from app.voice.feedback import outcome
            session.practice_feedback = outcome("unavailable", "The session ended before practice feedback was completed.")
        session.feedback_deadline_at = None
        session.feedback_checkpoint = None
        await self.store.put(session)
        self.tools.discard_session(session.session_id)
        self._last_cloud_check.pop(session.session_id, None)
        logger.info(f"{session.persona}_session_ended", session_id=session.session_id, reason=reason,
                    duration_seconds=round((session.ended_at - session.started_at).total_seconds(), 1))

    async def context_for(self, sid: str, claims: dict, persona: str) -> dict:
        session, actor = await self.owned(sid, claims, active=True)
        if session.persona != persona:
            raise ForbiddenError("This tool is not available to this assistant")
        context = await authorized_context(actor, session.dashboard_context, self.sb, persona)
        logger.info(f"{persona}_context_loaded", session_id=sid,
                    has_cv=bool(context.get("cv_claims_not_verified_evidence")), has_job="job" in context)
        return context

    async def call_tool(self, sid: str, claims: dict, name: str, args: dict) -> dict:
        session, _ = await self.owned(sid, claims, active=True)
        if name not in self.allowed_tools(session.persona):
            raise ForbiddenError("This tool is not available to this assistant")
        if name in {"get_training_context", "get_dashboard_context", "get_action_status"} and args:
            raise ValidationError("This context tool does not accept resource identifiers")
        if name in {"get_training_context", "get_dashboard_context"}:
            context = await self.context_for(sid, claims,
                    "taylor" if name == "get_training_context" else "morgan")
            return {"status": "ok", "data": context,
                    "message": "Current authorized page loaded. An empty selection is valid. Use search_candidates to list candidates; do not repeat this context request."}
        if name == "get_action_status":
            async with self.store.lock(sid):
                session, _ = await self.owned(sid, claims, active=True)
                await self._authorize_action_view(session, claims)
                await self.store.put(session)
                return {"pending_action": session.pending_action, "last_tool_result": session.last_tool_result,
                        "message": "No action has completed." if session.last_tool_result is None else session.last_tool_result.get("message")}
        async with self.store.lock(sid):
            session, _ = await self.owned(sid, claims, active=True)
            if name in WRITE_TOOLS:
                await self._authorize_action_view(session, claims)
                await self.store.put(session)
                if session.last_tool_result and session.last_tool_result.get("status") == "executing":
                    raise ConflictError("A confirmed action is still running. Check its result before proposing another change.")
                if session.pending_action:
                    raise ConflictError("A proposed action is awaiting review. Confirm or decline it in the panel before requesting another change.")
            logger.info("morgan_tool_requested", session_id=sid, tool=name)
            result = await self.tools.call(name, args, user_claims=claims, session_id=sid, persona=session.persona)
            session.pending_action = result.get("pending_action") or session.pending_action
            await self.store.put(session)
            return result

    async def confirm(self, sid: str, claims: dict, confirmation_id: str, approved: bool) -> dict:
        async with self.store.lock(sid):
            session, _ = await self.owned(sid, claims)
            await self._sync_execution(session, claims)
            if session.last_tool_result and session.last_tool_result.get("confirmation_id") == confirmation_id:
                if not approved and session.last_tool_result.get("status") == "executing":
                    raise ConflictError("This action was already confirmed and is running")
                await self._authorize_action_view(session, claims)
                await self.store.put(session)
                return session.last_tool_result
            session, _ = await self.owned(sid, claims, active=True)
            if not session.pending_action or session.pending_action.get("confirmation_id") != confirmation_id:
                raise ConflictError("This confirmation is not the current proposed action")
            if not approved:
                result = await self.tools.decline(confirmation_id, user_claims=claims, session_id=sid, persona=session.persona)
                session.last_tool_result = result
                session.pending_action = None
                await self.store.put(session)
                return result
            await self.tools.read_pending(confirmation_id, user_claims=claims, session_id=sid, persona=session.persona)
            owner = uuid4().hex
            if not await self.store.begin_execution(sid, confirmation_id, owner):
                raise ConflictError("This confirmation was already dispatched. Check its saved result.")
            result = {"status": "executing", "tool": session.pending_action["tool"], "confirmation_id": confirmation_id,
                      "message": "The confirmed action is running. Its result will appear here."}
            session.status = "EXECUTING"
            session.last_tool_result = result
            session.pending_action = None
            await self.store.put(session)
            task = asyncio.create_task(self._execute_confirmation(sid, dict(claims), confirmation_id, owner))
            self._confirmation_tasks[confirmation_id] = task
            task.add_done_callback(lambda done: self._confirmation_tasks.pop(confirmation_id, None))
            return result

    async def _sync_execution(self, session: VoiceSession, claims: dict) -> None:
        """Called under session lock; read/recover, never execute a mutation."""
        value = session.last_tool_result
        if not value or value.get("status") != "executing":
            return
        cid = value["confirmation_id"]
        try:
            result = await self.tools.read_result(cid, user_claims=claims, session_id=session.session_id, persona=session.persona)
        except ConflictError:
            # The background worker may not have acquired its durable tool
            # claim yet. Reauthorize the original proposal during that gap.
            await self.tools.read_pending(cid, user_claims=claims, session_id=session.session_id, persona=session.persona)
            result = value
        async with self.store.lock("execution:" + cid):
            if result.get("status") == "executing" and await self.store.execution_owner(cid) in {None, "finished"}:
                result = await self.tools.mark_interrupted(cid, user_claims=claims,
                    session_id=session.session_id, persona=session.persona)
            if result.get("status") != "executing":
                session.last_tool_result = result
                if session.status == "EXECUTING":
                    session.status = "CONNECTED"
                await self.store.finish_execution(session.session_id, cid)

    async def _execute_confirmation(self, sid: str, claims: dict, cid: str, owner: str) -> None:
        async def renew():
            while True:
                await asyncio.sleep(15)
                if not await self.store.renew_execution(cid, owner):
                    raise RuntimeError("Execution lease lost")
        renewer = asyncio.create_task(renew())
        execution = asyncio.create_task(self.tools.confirm(cid, user_claims=claims, session_id=sid, persona="morgan"))
        try:
            done, _ = await asyncio.wait({execution, renewer}, return_when=asyncio.FIRST_COMPLETED)
            if renewer in done:
                execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
                raise RuntimeError("Execution lease lost")
            result = await execution
            async with self.store.lock(sid):
                session = await self.store.get(sid)
                if session:
                    session.last_tool_result = result
                    if session.status == "EXECUTING":
                        session.status = "CONNECTED"
                    session.transcript.append({"id": "tool:" + cid, "role": "system",
                        "text": str(result.get("message") or "Action result available."), "at": utc_now().isoformat()})
                    session.transcript = session.transcript[-80:]
                    await self.store.put(session)
                    async with self.store.lock("execution:" + cid):
                        await self.store.finish_execution(sid, cid)
            logger.info("morgan_tool_executed", session_id=sid, confirmation_id=cid, status=result.get("status"))
            if session and session.status == "CONNECTED" and session.cloud_agent_id and result.get("message"):
                try:
                    await self.agora.announce_result("morgan", session.channel_name, session.cloud_agent_id, result["message"][:300])
                except Exception:
                    logger.warning("morgan_result_announcement_unavailable", session_id=sid, confirmation_id=cid)
        except BaseException as exc:
            # Cancellation/process loss is never retried. A durable result, if
            # present, is recovered by GET; otherwise lease loss marks unknown.
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
            logger.warning("morgan_execution_interrupted", session_id=sid, confirmation_id=cid, error_type=type(exc).__name__)
        finally:
            renewer.cancel()
            await asyncio.gather(renewer, return_exceptions=True)

    async def transcript(self, sid: str, claims: dict, events: list[dict]) -> dict:
        async with self.store.lock(sid):
            session, _ = await self.owned(sid, claims, active=True)
            existing = {item.get("id") for item in session.transcript}
            for event in events:
                if event["id"] not in existing:
                    session.transcript.append(event)
                    existing.add(event["id"])
            session.transcript = session.transcript[-80:]
            await self.store.put(session)
            return {"status": "saved"}

    async def expire_sessions(self) -> None:
        for sid in set(await self.store.active_ids()) | set(await self.store.executing_ids()):
            snapshot = await self.store.get(sid)
            # Recover before the native idle limit even if the browser closed.
            # The network read holds no session lock; recheck both identities
            # before using it so a late response cannot end another attempt.
            recovered = await self._read_native_feedback(snapshot) if snapshot else None
            async with self.store.lock(sid):
                session = await self.store.get(sid)
                if session:
                    try:
                        await self._sync_execution(session, {"sub": session.user_id})
                        await self.store.put(session)
                        if (recovered is not None and self._feedback_pending(session)
                                and session.feedback_attempt_id == snapshot.feedback_attempt_id
                                and session.cloud_agent_id == snapshot.cloud_agent_id):
                            await self._save_feedback_outcome(session, recovered, "practice_feedback_recovered")
                            continue
                        if self._feedback_overdue(session):
                            await self._expire_feedback(session, read_history=False)
                        elif (session.expires_at <= utc_now() or session.status == "ERROR" or
                              (utc_now() - session.heartbeat_at).total_seconds() > settings.VOICE_ASSISTANT_IDLE_SECONDS):
                            await self._end(session, "expired_or_disconnected")
                    except Exception:
                        logger.warning("voice_cleanup_retry", session_id=sid)

    def start_reaper(self) -> None:
        async def run():
            while True:
                try:
                    await self.expire_sessions()
                except Exception:
                    logger.warning("voice_cleanup_unavailable")
                await asyncio.sleep(15)
        self._reaper = asyncio.create_task(run())

    async def shutdown(self) -> None:
        if self._reaper:
            self._reaper.cancel()
            await asyncio.gather(self._reaper, return_exceptions=True)
        tasks = list(self._confirmation_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
