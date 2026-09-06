"""Allowlisted HR tools with persisted authorization and explicit confirmation.

Pending proposals expire after five minutes; claimed results remain for one hour.
Production injects the isolated Redis
pending store; the process-local fallback is for unit tests and fails closed on
restart. The application binds every call to its authenticated voice session.
No model-generated string can execute arbitrary code, SQL, or an external URL.
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import html
import json
from typing import Annotated, Any, Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field, NameEmail, TypeAdapter, ValidationError as PydanticError, field_validator
import structlog

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.integrations import email_client
from app.repositories.application_repo import ApplicationRepo
from app.repositories.candidate_repo import CandidateRepo
from app.repositories.interview_repo import InterviewRepo
from app.repositories.job_repo import JobRepo
from app.services.application_service import ApplicationService
from app.services.scheduling_service import SchedulingService
from app.voice import authorization as auth

logger = structlog.stdlib.get_logger("intra_ai.voice.tools")
ResourceId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class SearchCandidates(ToolInput):
    job_id: ResourceId | None = None
    search: str = Field(default="", max_length=100)
    status: Literal["applied", "parsing", "shortlisted", "rejected", "invited", "scheduled", "in_progress", "completed", "no_show"] | None = None
    limit: int = Field(default=20, ge=1, le=50, strict=True)
    offset: int = Field(default=0, ge=0, le=5000, strict=True)


class ListJobs(ToolInput):
    search: str = Field(default="", max_length=100)


class OverviewInput(ToolInput):
    pass


class CalendarListInput(ToolInput):
    page_token: str | None = Field(default=None, max_length=2048)


class SlackListInput(ToolInput):
    cursor: str | None = Field(default=None, max_length=2048)


class TemplateInput(ToolInput):
    template_id: ResourceId


class BulkShortlistInput(ToolInput):
    application_ids: list[ResourceId] = Field(min_length=1, max_length=50,
        description="The complete selected application IDs from authorized search results; not candidate IDs or names.")

    @field_validator("application_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Select each application once")
        return value


class BulkScheduleInput(BulkShortlistInput):
    application_ids: list[ResourceId] = Field(min_length=1, max_length=25)
    job_id: ResourceId
    template_id: ResourceId
    start_at: datetime
    timezone: str = Field(min_length=1, max_length=80)
    gap_minutes: int = Field(default=5, ge=0, le=120, strict=True)
    shortlist_first: bool = Field(default=True, strict=True)


class CandidateInput(ToolInput):
    candidate_id: ResourceId


class ApplicationInput(ToolInput):
    application_id: ResourceId


class InterviewInput(ToolInput):
    interview_id: ResourceId


class ReportInput(ToolInput):
    report_id: ResourceId


class SlotsInput(ToolInput):
    job_id: ResourceId


class ScheduleInput(ApplicationInput):
    slot_id: ResourceId


class RescheduleInput(InterviewInput):
    slot_id: ResourceId


class StatusInput(ApplicationInput):
    status: Literal["shortlisted", "rejected", "invited"]


class EmailInput(ApplicationInput):
    subject: str = Field(min_length=1, max_length=200, pattern=r"^[^\r\n]+$")
    body: str = Field(min_length=1, max_length=5000)


class CalendarExportInput(InterviewInput):
    calendar_id: str = Field(default="primary", min_length=1, max_length=256)
    notify_candidate: bool = Field(default=False, strict=True)


class SlackUpdateInput(ToolInput):
    job_id: ResourceId
    channel_id: str = Field(pattern=r"^[CG][A-Z0-9]{2,31}$")
    message: str = Field(min_length=1, max_length=3500)


class ConfirmInput(ToolInput):
    confirmation_id: ResourceId


TOOL_INPUTS: dict[str, type[ToolInput]] = {
    "list_jobs": ListJobs,
    "get_recruiting_overview": OverviewInput,
    "list_interview_templates": OverviewInput,
    "get_interview_template": TemplateInput,
    "bulk_shortlist_candidates": BulkShortlistInput,
    "bulk_schedule_interviews": BulkScheduleInput,
    "get_connected_services": OverviewInput,
    "list_connected_calendars": CalendarListInput,
    "list_slack_channels": SlackListInput,
    "create_candidate_email_draft": EmailInput,
    "add_interview_to_calendar": CalendarExportInput,
    "post_recruiting_update_to_slack": SlackUpdateInput,
    "search_candidates": SearchCandidates,
    "get_candidate": CandidateInput,
    "get_application": ApplicationInput,
    "get_interview": InterviewInput,
    "get_report": ReportInput,
    "find_available_slots": SlotsInput,
    "schedule_interview": ScheduleInput,
    "reschedule_interview": RescheduleInput,
    "cancel_interview": InterviewInput,
    "update_application_status": StatusInput,
    "send_candidate_email": EmailInput,
    "send_reminder_email": InterviewInput,
}
WRITE_TOOLS = frozenset({"schedule_interview", "reschedule_interview", "cancel_interview", "update_application_status", "send_candidate_email", "send_reminder_email", "bulk_shortlist_candidates", "bulk_schedule_interviews", "create_candidate_email_draft", "add_interview_to_calendar", "post_recruiting_update_to_slack"})
TOOL_DESCRIPTIONS = {
    "get_connected_services": "Check Morgan's configured Composio Gmail, Google Calendar and Slack connections. Connection configuration is not proof a particular service is authorized.",
    "list_connected_calendars": "List calendars from this recruiter's connected Google Calendar account, to choose an actual calendar before exporting an interview.",
    "list_slack_channels": "List the connected Slack account's public channels; resolve a real channel before preparing a recruiting update.",
    "create_candidate_email_draft": "Propose saving an email draft in connected Gmail for the application's actual candidate. Recruiter reviews exact recipient and text; does not send email.",
    "add_interview_to_calendar": "Propose adding an already scheduled Intra AI interview to a connected Google Calendar. Review calendar, saved time and candidate. notify_candidate=false avoids invitation emails; true must be explicitly requested and confirmed.",
    "post_recruiting_update_to_slack": "Propose a job-scoped recruiting update to a real Slack channel. Recruiter reviews exact channel and message before posting. Include only requested candidate information; don't invent hiring results.",
    "list_jobs": "List jobs in your recruiter workspace; resolve a job name to a real ID before filtering candidates.",
    "get_recruiting_overview": "Read your recruiting counts and next steps: applications awaiting review, shortlisted candidates, and upcoming saved interviews.",
    "list_interview_templates": "List reusable interview templates available in your recruiter workspace, with rounds and duration.",
    "get_interview_template": "Read one authorized interview template and its interviewer panel, rounds and duration.",
    "bulk_shortlist_candidates": "Use for shortlisting two or more explicitly selected candidates, including both, these candidates, or all selected. Call once with the complete application_ids from search_candidates, up to 50. Do not split this request into individual update_application_status calls. Returns one review containing all selected candidates and skipped states; requires one recruiter confirmation. For all candidates, finish pagination first; if more than 50 match, ask for batches rather than silently omit anyone. Does not send messages.",
    "bulk_schedule_interviews": "Propose scheduling up to 25 candidates for one job using a saved interview template and consecutive times. Requires real application IDs, template ID, future start time with offset, and IANA timezone. Ask for missing time/template details. Can shortlist first. Requires one reviewed confirmation; creates Intra AI interviews only, without sending email or external calendar events.",
    "search_candidates": "Find candidates in your authorized recruiter workspace; optionally filter by job, name/email, or application status.",
    "get_candidate": "Read an authorized candidate profile and resume facts for your workspace.",
    "get_application": "Read an authorized application and its actual status.",
    "get_interview": "Read an authorized scheduled interview, time, and status.",
    "get_report": "Read an existing authorized official report; never generate or alter evaluation.",
    "find_available_slots": "Find saved unbooked Intra AI slots for an authorized job; not external-calendar free/busy.",
    "schedule_interview": "Propose booking an existing slot; returns a reviewable confirmation and does not yet book.",
    "reschedule_interview": "Propose moving an existing interview to a saved slot; requires confirmation.",
    "cancel_interview": "Propose cancelling a not-yet-started interview; requires confirmation.",
    "update_application_status": "Propose a status change for exactly one application: shortlist, rejection, or invitation, using existing business rules and recruiter confirmation. For shortlisting two or more selected candidates, use bulk_shortlist_candidates once instead; never issue separate or parallel single-application proposals for a batch request.",
    "send_candidate_email": "Propose an email to the application's saved candidate address; requires explicit confirmation.",
    "send_reminder_email": "Propose a reminder with the saved interview time; requires explicit confirmation.",
}


def tool_schemas() -> list[dict[str, Any]]:
    return [{"name": name, "description": TOOL_DESCRIPTIONS[name], "inputSchema": model.model_json_schema()} for name, model in TOOL_INPUTS.items()]


def _pick(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: copy.deepcopy(row[key]) for key in keys if key in row}


def _candidate(row: dict[str, Any]) -> dict[str, Any]:
    result = _pick(row, "id", "name", "email", "phone", "authorized_application_ids")
    resumes = row.get("parsed_resumes") or []
    if isinstance(resumes, dict):
        resumes = [resumes]
    result["resumes"] = [_pick(item, "id", "application_id", "skills", "experience", "education", "projects", "certifications") for item in resumes]
    return result


def _application(row: dict[str, Any]) -> dict[str, Any]:
    return _pick(row, "id", "job_id", "candidate_id", "status", "eligibility_score", "created_at")


def _interview(row: dict[str, Any]) -> dict[str, Any]:
    return _pick(row, "id", "application_id", "job_id", "candidate_id", "status", "scheduled_at", "duration_minutes", "slot_id")


def _serialize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    # Never return room credentials from a scheduling service response.
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items() if key not in {"room_token", "rtc_token", "token", "password_hash"}}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


def _bounded(value: Any, depth: int = 0, budget: list[int] | None = None) -> tuple[Any, bool]:
    """Keep model-visible reads bounded, with an explicit truncation indicator."""
    if budget is None:
        budget = [20000, 1000]  # characters and structural nodes across the result
    budget[1] -= 1
    if depth > 8 or budget[0] <= 0 or budget[1] <= 0:
        return None, True
    if isinstance(value, str):
        limit = min(3000, budget[0])
        budget[0] -= min(len(value), limit)
        return value[:limit], len(value) > limit
    if isinstance(value, list):
        items = [_bounded(item, depth + 1, budget) for item in value[:50]]
        return [item for item, _ in items], len(value) > 50 or any(cut for _, cut in items)
    if isinstance(value, dict):
        items = [(key, _bounded(item, depth + 1, budget)) for key, item in list(value.items())[:50]]
        return {key: item for key, (item, _) in items}, len(value) > 50 or any(cut for _, (_, cut) in items)
    return value, False


@dataclass
class _Pending:
    owner_id: str
    owner_role: str
    tenant_id: str | None
    session_id: str
    action: str
    arguments_json: str
    review_json: str
    expires_at: datetime
    status: str = "pending"
    result: dict[str, Any] | None = None


class VoiceToolService:
    def __init__(self, supabase: Any, *, pending_store: Any = None) -> None:
        self.sb = supabase
        self.app_repo = ApplicationRepo(supabase)
        self.interview_repo = InterviewRepo(supabase)
        self.candidate_repo = CandidateRepo(supabase)
        self.job_repo = JobRepo(supabase)
        self.applications = ApplicationService(self.app_repo, self.candidate_repo, self.job_repo)
        self.scheduling = SchedulingService(self.interview_repo, self.app_repo)
        self._pending: dict[str, _Pending] = {}
        self._action_locks: dict[str, asyncio.Lock] = {}
        self.pending_store = pending_store

    async def call(self, name: str, arguments: dict[str, Any], *, user_claims: dict[str, Any], session_id: str, persona: str = "morgan") -> dict[str, Any]:
        if persona != "morgan":
            raise ForbiddenError("HR tools are not available in training")
        actor = await auth.identity(user_claims, self.sb)
        auth.require_recruiter(actor)
        if not session_id or len(session_id) > 128:
            raise ValidationError("A valid voice session is required")
        model = TOOL_INPUTS.get(name)
        if model is None:
            raise ValidationError("Unknown voice tool")
        try:
            inputs = model.model_validate(arguments)
        except PydanticError as exc:
            # Validation details may include arbitrary input. Do not echo them.
            raise ValidationError("Invalid tool arguments") from exc
        if name in WRITE_TOOLS:
            try:
                review = await self._review(name, inputs, actor)
            except AppError:
                self._audit(actor, session_id, name, "proposal_rejected")
                raise
            except Exception as exc:
                self._audit(actor, session_id, name, "proposal_unavailable")
                raise AppError("The requested action is temporarily unavailable") from exc
            confirmation_id = str(uuid.uuid4())
            pending = _Pending(actor.user_id, actor.role, actor.tenant_id, session_id, name, inputs.model_dump_json(), json.dumps(review, sort_keys=True), datetime.now(timezone.utc) + timedelta(minutes=5))
            self._pending[confirmation_id] = pending
            self._prune()
            await self._save_pending(confirmation_id, pending)
            self._audit(actor, session_id, name, "confirmation_required", confirmation_id)
            return self._pending_response(confirmation_id, pending)
        try:
            result = await self._read(name, inputs, actor)
        except AppError:
            self._audit(actor, session_id, name, "read_rejected")
            raise
        except Exception as exc:
            self._audit(actor, session_id, name, "read_unavailable")
            raise AppError("The requested data is temporarily unavailable") from exc
        self._audit(actor, session_id, name, "read_completed")
        data, truncated = _bounded(_serialize(result))
        return {"status": "ok", "tool": name, "data": data, "truncated": truncated}

    async def confirm(self, confirmation_id: str, *, user_claims: dict[str, Any], session_id: str, persona: str = "morgan") -> dict[str, Any]:
        if persona != "morgan":
            raise ForbiddenError("HR tools are not available in training")
        try:
            ConfirmInput(confirmation_id=confirmation_id)
        except PydanticError as exc:
            raise ValidationError("Invalid confirmation identifier") from exc
        actor = await auth.identity(user_claims, self.sb)
        auth.require_recruiter(actor)
        async with self._action_locks.setdefault(confirmation_id, asyncio.Lock()):
            pending = await self._load_pending(confirmation_id)
            if not pending:
                raise NotFoundError("Confirmation not found or expired")
            if (pending.owner_id, pending.owner_role, pending.tenant_id, pending.session_id) != (actor.user_id, actor.role, actor.tenant_id, session_id):
                raise ForbiddenError("Confirmation belongs to another session or workspace")
            if pending.expires_at <= datetime.now(timezone.utc):
                raise ConflictError("Confirmation expired; request a new action")
            inputs = await self._authorize_action_resources(pending, actor)
            if pending.status != "pending":
                if pending.result:
                    return {**copy.deepcopy(pending.result), "replayed": True}
                raise ConflictError("Action is already executing or unavailable")
            # Re-authorize every resource and compare the recipient/time/status
            # actually reviewed. A concurrent edit requires a new confirmation.
            current = await self._review(pending.action, inputs, actor)
            if json.dumps(current, sort_keys=True) != pending.review_json:
                pending.status = "invalidated"
                pending.result = {"status": "failed", "outcome_unknown": False, "code": "details_changed", "tool": pending.action, "confirmation_id": confirmation_id, "message": "Details changed after review. No action was taken; request a fresh proposal."}
                await self._save_pending(confirmation_id, pending)
                raise ConflictError("Details changed; review a new confirmation before proceeding")
            if self.pending_store is not None and not await self.pending_store.claim(confirmation_id):
                raise ConflictError("Action was already claimed; check its status before retrying")
            pending.status = "executing"
            pending.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            pending.result = {"status": "executing", "tool": pending.action, "confirmation_id": confirmation_id, "message": "The confirmed action is running. Its result will appear here."}
            await self._save_pending(confirmation_id, pending)
            try:
                # Claiming/persisting yields to other requests. Recheck access,
                # but execute the exact approved payload rather than rebuilding
                # recipients, calendar times or template snapshots from new data.
                execution_actor = await auth.identity(user_claims, self.sb)
                if (execution_actor.user_id, execution_actor.role, execution_actor.tenant_id) != (pending.owner_id, pending.owner_role, pending.tenant_id):
                    raise ForbiddenError("Confirmation ownership changed before execution")
                await self._authorize_action_resources(pending, execution_actor)
                data = await self._execute(pending.action, inputs, execution_actor,
                    confirmation_id=confirmation_id, review=json.loads(pending.review_json))
                partial = isinstance(data, dict) and bool(data.get("failed"))
                message = "The confirmed action completed."
                if isinstance(data, dict) and "items" in data and "succeeded" in data:
                    message = f"{data['succeeded']} completed, {data.get('skipped', 0)} skipped, {data.get('failed', 0)} need review."
                result = {"status": "partial" if partial else "succeeded", "tool": pending.action, "confirmation_id": confirmation_id, "message": message, "result": _serialize(data)}
                pending.status = "completed"
            except Exception:
                # A timeout can occur after a provider accepted the action.
                # Never blindly replay a mutation; tell the user to inspect it.
                pending.status = "failed"
                result = {"status": "failed", "tool": pending.action, "confirmation_id": confirmation_id, "message": "The action could not be verified. Check its current status before submitting another request."}
            pending.result = copy.deepcopy(result)
            await self._save_pending(confirmation_id, pending)
            self._audit(actor, session_id, pending.action, pending.status, confirmation_id)
            return result

    async def read_result(self, confirmation_id: str, *, user_claims: dict[str, Any], session_id: str, persona: str = "morgan") -> dict[str, Any]:
        """Read a running or terminal result after fresh authorization, without executing.

        Business state has legitimately changed after success, so this checks
        immutable resource identities and access rather than proposal rules.
        Expired confirmation records are not an alternate result-access path.
        """
        if persona != "morgan":
            raise ForbiddenError("HR tools are not available in training")
        try:
            ConfirmInput(confirmation_id=confirmation_id)
        except PydanticError as exc:
            raise ValidationError("Invalid confirmation identifier") from exc
        actor = await auth.identity(user_claims, self.sb)
        auth.require_recruiter(actor)
        pending = await self._load_pending(confirmation_id)
        if not pending or pending.expires_at <= datetime.now(timezone.utc):
            raise NotFoundError("Confirmation not found or expired")
        if (pending.owner_id, pending.owner_role, pending.tenant_id, pending.session_id) != (actor.user_id, actor.role, actor.tenant_id, session_id):
            raise ForbiddenError("Confirmation belongs to another session or workspace")
        await self._authorize_action_resources(pending, actor)
        if pending.status not in {"executing", "completed", "failed", "declined", "invalidated"} or pending.result is None:
            raise ConflictError("This action has no execution result")
        self._audit(actor, session_id, pending.action, "result_read", confirmation_id)
        return copy.deepcopy(pending.result)

    async def read_pending(self, confirmation_id: str, *, user_claims: dict[str, Any], session_id: str, persona: str = "morgan") -> dict[str, Any]:
        """Read the original pending review only while access remains valid."""
        if persona != "morgan":
            raise ForbiddenError("HR tools are not available in training")
        try:
            ConfirmInput(confirmation_id=confirmation_id)
        except PydanticError as exc:
            raise ValidationError("Invalid confirmation identifier") from exc
        actor = await auth.identity(user_claims, self.sb)
        auth.require_recruiter(actor)
        pending = await self._load_pending(confirmation_id)
        if not pending or pending.expires_at <= datetime.now(timezone.utc):
            raise NotFoundError("Confirmation not found or expired")
        if (pending.owner_id, pending.owner_role, pending.tenant_id, pending.session_id) != (actor.user_id, actor.role, actor.tenant_id, session_id):
            raise ForbiddenError("Confirmation belongs to another session or workspace")
        await self._authorize_action_resources(pending, actor)
        if pending.status != "pending":
            raise ConflictError("This action is no longer pending")
        self._audit(actor, session_id, pending.action, "pending_read", confirmation_id)
        return self._pending_response(confirmation_id, pending)

    async def mark_interrupted(self, confirmation_id: str, *, user_claims: dict[str, Any], session_id: str, persona: str = "morgan") -> dict[str, Any]:
        """Record an expired worker lease; caller must prove lease loss first.

        This never retries an action: a provider may have accepted it before
        the worker disappeared. An already recorded result is preserved.
        """
        if persona != "morgan":
            raise ForbiddenError("HR tools are not available in training")
        try:
            ConfirmInput(confirmation_id=confirmation_id)
        except PydanticError as exc:
            raise ValidationError("Invalid confirmation identifier") from exc
        actor = await auth.identity(user_claims, self.sb)
        auth.require_recruiter(actor)
        # Do not await the execution lock: its holder may be the lost worker.
        pending = await self._load_pending(confirmation_id)
        if not pending or pending.expires_at <= datetime.now(timezone.utc):
            raise NotFoundError("Confirmation not found or expired")
        if (pending.owner_id, pending.owner_role, pending.tenant_id, pending.session_id) != (actor.user_id, actor.role, actor.tenant_id, session_id):
            raise ForbiddenError("Confirmation belongs to another session or workspace")
        await self._authorize_action_resources(pending, actor)
        if pending.status in {"completed", "failed", "declined", "invalidated"} and pending.result:
            return copy.deepcopy(pending.result)
        if pending.status not in {"pending", "executing"}:
            raise ConflictError("This action is no longer executable")
        pending.status = "failed"
        pending.result = {"status": "failed", "outcome_unknown": True, "tool": pending.action,
            "confirmation_id": confirmation_id,
            "message": "Execution was interrupted. Check each application's current status before requesting any action again."}
        await self._save_pending(confirmation_id, pending)
        self._audit(actor, session_id, pending.action, "execution_interrupted", confirmation_id)
        return copy.deepcopy(pending.result)

    async def _authorize_action_resources(self, pending: _Pending, actor: auth.Actor) -> ToolInput:
        """Reauthorize every original resource without checking mutable status."""
        inputs = TOOL_INPUTS[pending.action].model_validate_json(pending.arguments_json)
        original = json.loads(pending.review_json)
        if pending.action == "post_recruiting_update_to_slack":
            self._connector(actor)
            await auth.require_job(actor, inputs.job_id, self.sb)
            return inputs
        if original.get("connected_service"):
            self._connector(actor)
        from app.voice import bulk
        if pending.action in bulk.BULK_TOOLS:
            await bulk.authorize_existing(self, inputs, actor, original, pending.result)
            return inputs
        if hasattr(inputs, "interview_id"):
            interview = await auth.require_interview(actor, inputs.interview_id, self.sb)
            application = await auth.require_application(actor, interview["application_id"], self.sb)
        else:
            application = await auth.require_application(actor, inputs.application_id, self.sb)
        original_app = original["application"]
        if any(application.get(key) != original_app.get(key) for key in ("id", "job_id", "candidate_id")):
            raise ForbiddenError("The action's resource relationships changed")
        await auth.require_job(actor, original["job"]["id"], self.sb)
        await auth.require_candidate(actor, original["candidate"]["id"], self.sb)
        slot_ids = {value for value in (getattr(inputs, "slot_id", None), original.get("slot", {}).get("id"), original.get("interview", {}).get("slot_id")) if value}
        for slot_id in slot_ids:
            slot = await self.interview_repo.get_slot_by_id(slot_id)
            if not slot:
                raise NotFoundError("Interview slot not found")
            if slot.get("job_id") != original["job"]["id"]:
                raise ForbiddenError("Slot belongs to another job")
            auth._tenant_match(actor.tenant_id, slot)
        # Successful bookings create a new record; a cached result must not
        # expose it after that record's ownership/relationships are changed.
        if pending.status == "completed" and pending.action in {"schedule_interview", "reschedule_interview"}:
            result_interview = (pending.result or {}).get("result", {}).get("id")
            if result_interview:
                await auth.require_interview(actor, result_interview, self.sb)
        return inputs

    async def decline(self, confirmation_id: str, *, user_claims: dict[str, Any], session_id: str, persona: str = "morgan") -> dict[str, Any]:
        if persona != "morgan":
            raise ForbiddenError("HR tools are not available in training")
        try:
            ConfirmInput(confirmation_id=confirmation_id)
        except PydanticError as exc:
            raise ValidationError("Invalid confirmation identifier") from exc
        actor = await auth.identity(user_claims, self.sb)
        auth.require_recruiter(actor)
        async with self._action_locks.setdefault(confirmation_id, asyncio.Lock()):
            pending = await self._load_pending(confirmation_id)
            if not pending:
                raise NotFoundError("Confirmation not found or expired")
            if (pending.owner_id, pending.owner_role, pending.tenant_id, pending.session_id) != (actor.user_id, actor.role, actor.tenant_id, session_id):
                raise ForbiddenError("Confirmation belongs to another session or workspace")
            if pending.status != "pending":
                raise ConflictError("This action is no longer pending")
            pending.status = "declined"
            pending.result = {"status": "declined", "confirmation_id": confirmation_id, "message": "The proposed action was declined. No action was taken."}
            await self._save_pending(confirmation_id, pending)
            self._audit(actor, session_id, pending.action, "declined", confirmation_id)
            return dict(pending.result)

    async def _save_pending(self, key: str, value: _Pending) -> None:
        if self.pending_store is not None:
            data = asdict(value)
            data["expires_at"] = value.expires_at.isoformat()
            ttl = max(1, int((value.expires_at - datetime.now(timezone.utc)).total_seconds()))
            await self.pending_store.put(key, data, ttl)

    async def _load_pending(self, key: str) -> _Pending | None:
        if self.pending_store is None:
            return self._pending.get(key)
        data = await self.pending_store.get(key)
        if not data:
            return None
        data = dict(data)
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return _Pending(**data)

    def discard_session(self, session_id: str) -> None:
        self._pending = {key: value for key, value in self._pending.items() if value.session_id != session_id}

    def _prune(self) -> None:
        now = datetime.now(timezone.utc)
        self._pending = {key: value for key, value in self._pending.items() if value.expires_at > now}
        self._action_locks = {key: lock for key, lock in self._action_locks.items() if key in self._pending or lock.locked()}

    @staticmethod
    def _pending_response(key: str, value: _Pending) -> dict[str, Any]:
        action = {"confirmation_id": key, "tool": value.action, "summary": value.action.replace("_", " ").capitalize(), "details": json.loads(value.review_json), "expires_at": value.expires_at.isoformat(), "status": "pending"}
        return {"status": "confirmation_required", "pending_action": action, "message": "Review these details and explicitly confirm to execute. No action has been taken."}

    @staticmethod
    def _audit(actor: auth.Actor, session_id: str, tool: str, outcome: str, confirmation_id: str | None = None) -> None:
        logger.info("voice_tool_audit", user_id=actor.user_id, session_id=session_id, tool=tool, outcome=outcome, confirmation_id=confirmation_id)

    async def _read(self, name: str, inputs: ToolInput, actor: auth.Actor) -> Any:
        if name in {"get_connected_services", "list_connected_calendars", "list_slack_channels"}:
            client = self._connector(actor)
            if name == "list_connected_calendars":
                return await client.call_tool("GOOGLECALENDAR_LIST_CALENDARS", inputs.model_dump(exclude_none=True))
            if name == "list_slack_channels":
                return await client.call_tool("SLACK_LIST_CONVERSATIONS", inputs.model_dump(exclude_none=True))
            async def check(tool: str) -> dict:
                try:
                    result = await client.call_tool(tool, {})
                    return {"status": "connected" if result.get("verified") else "unverified"}
                except AppError:
                    return {"status": "unavailable", "message": "Could not verify this service. Check the Composio connection assigned to Morgan."}
            values = await asyncio.gather(check("GMAIL_GET_PROFILE"), check("GOOGLECALENDAR_LIST_CALENDARS"), check("SLACK_TEST_AUTH"))
            return {"gmail": values[0], "google_calendar": values[1], "slack": values[2], "database": {"status": "scoped_to_your_recruiter_workspace"}}
        if name in {"list_interview_templates", "get_interview_template"}:
            from app.services.interview_template_service import InterviewTemplateService
            service = InterviewTemplateService(self.sb)
            if name == "get_interview_template":
                return await service.get(actor, inputs.template_id)
            return {"templates": await service.list(actor)}
        if name == "list_jobs":
            jobs, limited = self._jobs(actor)
            return {"jobs": [_pick(row, "id", "title", "status") for row in jobs if inputs.search.casefold() in str(row.get("title", "")).casefold()], "limited": limited}
        if name == "get_recruiting_overview":
            return await self._overview(actor)
        if name == "get_candidate":
            return _candidate(await auth.require_candidate(actor, inputs.candidate_id, self.sb))
        if name == "get_application":
            return _application(await auth.require_application(actor, inputs.application_id, self.sb))
        if name == "get_interview":
            return _interview(await auth.require_interview(actor, inputs.interview_id, self.sb))
        if name == "get_report":
            row = await auth.require_report(actor, inputs.report_id, self.sb)
            return _pick(row, "id", "interview_id", "round_assessments", "overall_score", "recommendation", "strengths", "improvements", "created_at")
        if name == "find_available_slots":
            await auth.require_job(actor, inputs.job_id, self.sb)
            slots = await self.scheduling.get_available_slots(inputs.job_id)
            return {"source": "Intra AI saved interview slots", "external_calendar_verified": False, "slots": [_serialize(slot) for slot in slots]}
        if name == "search_candidates":
            return await self._search(inputs, actor)
        raise ValidationError("Unknown read tool")

    async def _search(self, inputs: SearchCandidates, actor: auth.Actor) -> dict[str, Any]:
        if inputs.job_id:
            jobs = [await auth.require_job(actor, inputs.job_id, self.sb)]
            limited = False
        else:
            jobs, limited = self._jobs(actor)
        found = []
        matched = 0
        for job in jobs:
            page = 1
            while True:
                rows, total = await self.app_repo.list_by_job(job["id"], {"status": inputs.status} if inputs.status else None, page=page, per_page=200)
                for row in rows:
                    person = row.get("candidates") or await self.candidate_repo.get_by_id(row["candidate_id"])
                    if not person or row.get("job_id") != job["id"] or person.get("id") != row.get("candidate_id"):
                        continue
                    try:
                        auth._tenant_match(actor.tenant_id, row)
                        auth._tenant_match(actor.tenant_id, person)
                    except ForbiddenError:
                        continue
                    searchable = f"{person.get('name', '')} {person.get('email', '')}".casefold()
                    if inputs.search.casefold() not in searchable:
                        continue
                    matched += 1
                    if matched <= inputs.offset:
                        continue
                    if len(found) == inputs.limit:
                        return {"matches": found, "limited": True, "next_offset": inputs.offset + inputs.limit}
                    found.append({"candidate": _pick(person, "id", "name", "email"), "application": _application(row), "job": _pick(job, "id", "title")})
                if not rows or page * 200 >= total:
                    break
                page += 1
        return {"matches": found, "limited": limited, "next_offset": None,
                "message": "No matching applications in your recruiter workspace." if not found else ""}

    def _jobs(self, actor: auth.Actor) -> tuple[list[dict], bool]:
        # Legacy hosted tables may have no tenant column. Query private job
        # ownership first, then enforce any tenant tags returned by the DB.
        found, offset = [], 0
        while True:
            rows = self.sb.table("jobs").select("*").eq("created_by", actor.user_id).order("id").range(offset, offset + 99).execute().data or []
            for job in rows:
                if auth._job_owned(actor, job):
                    found.append(job)
                    if len(found) > 100:
                        return found[:100], True
            if len(rows) < 100:
                return found, False
            offset += 100

    async def _overview(self, actor: auth.Actor) -> dict:
        jobs, limited = self._jobs(actor)
        counts: dict[str, int] = {}
        upcoming = []
        now = datetime.now(timezone.utc)
        for job in jobs:
            page = 1
            while True:
                rows, total = await self.app_repo.list_by_job(job["id"], page=page, per_page=200)
                for row in rows:
                    try:
                        auth._tenant_match(actor.tenant_id, row)
                    except ForbiddenError:
                        continue
                    status = str(row.get("status") or "unknown")
                    counts[status] = counts.get(status, 0) + 1
                if not rows or page * 200 >= total:
                    break
                page += 1
            interviews, interview_total = await self.interview_repo.list({"job_id": job["id"], "status": "scheduled"}, per_page=100)
            limited = limited or interview_total > len(interviews)
            for row in interviews:
                try:
                    start = datetime.fromisoformat(str(row.get("scheduled_at", "")).replace("Z", "+00:00"))
                    if start.tzinfo is None or start < now:
                        continue
                    auth._tenant_match(actor.tenant_id, row)
                except (ValueError, ForbiddenError):
                    continue
                upcoming.append({**_interview(row), "job_title": job.get("title"), "candidate_name": (row.get("candidates") or {}).get("name")})
        upcoming.sort(key=lambda item: item.get("scheduled_at") or "")
        return {"job_count": len(jobs), "application_counts": counts, "awaiting_review": counts.get("applied", 0) + counts.get("parsing", 0),
                "ready_to_schedule": counts.get("shortlisted", 0) + counts.get("invited", 0) + counts.get("completed", 0),
                "upcoming_interviews": upcoming[:10], "limited": limited}

    async def _slot(self, actor: auth.Actor, slot_id: str, job_id: str, *, current_slot: str | None = None) -> dict[str, Any]:
        slot = await self.interview_repo.get_slot_by_id(slot_id)
        if not slot:
            raise NotFoundError("Interview slot not found")
        if slot.get("job_id") != job_id:
            raise ForbiddenError("Slot belongs to another job")
        auth._tenant_match(actor.tenant_id, slot)
        if slot.get("is_booked") and slot_id != current_slot:
            raise ConflictError("This slot is already booked")
        try:
            start = datetime.fromisoformat(f"{slot['date']}T{slot['start_time']}").replace(tzinfo=timezone.utc)
        except (ValueError, KeyError) as exc:
            raise ValidationError("This slot has an invalid saved date or time") from exc
        if start <= datetime.now(timezone.utc):
            raise ValidationError("Choose a future interview slot")
        return _pick(slot, "id", "job_id", "date", "start_time", "end_time") | {"timezone": "UTC"}

    @staticmethod
    def _email_available() -> None:
        if not settings.RESEND_API_KEY.strip():
            raise ValidationError("Email delivery is not configured. Add a Resend credential before sending email.")
        sender = settings.RESEND_FROM_EMAIL.strip()
        try:
            if not sender or len(sender) > 320 or "\r" in sender or "\n" in sender:
                raise ValueError("Invalid sender")
            TypeAdapter(NameEmail).validate_python(sender)
        except (ValueError, PydanticError) as exc:
            raise ValidationError("Email delivery needs a valid RESEND_FROM_EMAIL address from a verified Resend domain before sending email.") from exc

    @staticmethod
    def _connector(actor: auth.Actor):
        from app.voice.composio import MorganComposioClient
        owner = str(getattr(settings, "MORGAN_COMPOSIO_OWNER_USER_ID", "") or "")
        if not owner or actor.user_id != owner:
            raise ForbiddenError("No Morgan messaging connection is assigned to this recruiter account")
        client = MorganComposioClient.from_settings(settings)
        if not client.configured:
            raise ValidationError("Morgan's Composio connection is not configured")
        return client

    @staticmethod
    async def _connected_resource(client, kind: str, identifier: str) -> dict | None:
        tool, collection, cursor_key, input_key = (
            ("SLACK_LIST_CONVERSATIONS", "channels", "next_cursor", "cursor") if kind == "slack" else
            ("GOOGLECALENDAR_LIST_CALENDARS", "calendars", "next_page_token", "page_token"))
        args, seen = {}, set()
        for _ in range(10):
            page = await client.call_tool(tool, args)
            for row in page.get(collection, []):
                if (row.get("id") == identifier or (kind == "calendar" and identifier == "primary" and row.get("primary"))) and not row.get("is_archived"):
                    return row
            cursor = page.get(cursor_key)
            if not cursor or cursor in seen:
                return None
            seen.add(cursor)
            args = {input_key: cursor}
        raise ValidationError("This connected-service list is too large to verify now; choose an item from an earlier page")

    async def _review(self, name: str, inputs: ToolInput, actor: auth.Actor) -> dict[str, Any]:
        from app.voice import bulk
        if name in bulk.BULK_TOOLS:
            return await bulk.review(self, name, inputs, actor)
        if name == "post_recruiting_update_to_slack":
            client = self._connector(actor)
            job = await auth.require_job(actor, inputs.job_id, self.sb)
            match = await self._connected_resource(client, "slack", inputs.channel_id)
            if not match:
                raise ValidationError("Choose a public Slack channel returned by list_slack_channels")
            return {"job": _pick(job, "id", "title"), "connected_service": "slack", "channel": _pick(match, "id", "name"), "message": inputs.message}
        interview = None
        if hasattr(inputs, "interview_id"):
            interview = await auth.require_interview(actor, inputs.interview_id, self.sb)
            application = await auth.require_application(actor, interview["application_id"], self.sb)
        else:
            application = await auth.require_application(actor, inputs.application_id, self.sb)
        person = await auth.require_candidate(actor, application["candidate_id"], self.sb)
        job = await auth.require_job(actor, application["job_id"], self.sb)
        review = {"candidate": _pick(person, "id", "name", "email"), "job": _pick(job, "id", "title"), "application": _application(application)}
        if interview:
            review["interview"] = _interview(interview)
        if name == "schedule_interview":
            if application.get("status") not in {"shortlisted", "invited", "completed"}:
                raise ValidationError("The application must be shortlisted, invited, or completed before scheduling")
            latest = await self.interview_repo.get_latest_by_application_id(application["id"])
            if latest and latest.get("status") in {"scheduled", "instant_pending", "instant_active", "in_progress"}:
                raise ConflictError("An active interview already exists; reschedule it instead")
            review["slot"] = await self._slot(actor, inputs.slot_id, application["job_id"])
        elif name == "reschedule_interview":
            if application.get("status") != "scheduled" or interview.get("status") not in {"scheduled", "instant_active"}:
                raise ValidationError("Only a scheduled interview can be rescheduled")
            latest = await self.interview_repo.get_latest_by_application_id(application["id"])
            if not latest or latest["id"] != interview["id"]:
                raise ConflictError("Only the latest interview can be rescheduled")
            self._require_not_started(interview["id"])
            review["slot"] = await self._slot(actor, inputs.slot_id, application["job_id"], current_slot=interview.get("slot_id"))
        elif name == "cancel_interview":
            if interview.get("status") not in {"scheduled", "instant_pending", "instant_active"}:
                raise ValidationError("Only an interview that has not started can be cancelled")
            latest = await self.interview_repo.get_latest_by_application_id(application["id"])
            if not latest or latest["id"] != interview["id"]:
                raise ConflictError("Only the latest interview can be cancelled")
            self._require_not_started(interview["id"])
            review["new_interview_status"] = "cancelled"
            review["new_application_status"] = "shortlisted"
        elif name == "update_application_status":
            status = application.get("status")
            allowed = {"shortlisted": {"applied", "parsing", "rejected", "shortlisted"}, "invited": {"shortlisted", "invited"}, "rejected": {"applied", "parsing", "shortlisted", "invited"}}
            if status not in allowed[inputs.status]:
                raise ValidationError("This application status transition is not available")
            review["new_status"] = inputs.status
        elif name == "add_interview_to_calendar":
            client = self._connector(actor)
            if interview.get("status") != "scheduled":
                raise ValidationError("Only a scheduled interview can be added to a calendar")
            calendar = await self._connected_resource(client, "calendar", inputs.calendar_id)
            if not calendar or calendar.get("accessRole") not in {"owner", "writer"}:
                raise ValidationError("Choose a connected calendar with write access")
            start = datetime.fromisoformat(str(interview.get("scheduled_at", "")).replace("Z", "+00:00"))
            if start.tzinfo is None or start <= datetime.now(timezone.utc):
                raise ValidationError("The saved interview must have a future timezone-aware start")
            duration = (interview.get("template_snapshot") or {}).get("duration_minutes") or interview.get("duration_minutes") or 60
            review.update(connected_service="google_calendar", calendar=_pick(calendar, "id", "summary"),
                          event={"summary": f"Interview: {job.get('title') or 'Role'} — {person.get('name') or 'Candidate'}",
                                 "start_datetime": start.isoformat(), "end_datetime": (start + timedelta(minutes=duration)).isoformat(),
                                 "attendees": [person["email"]], "send_updates": "all" if inputs.notify_candidate else "none"})
        elif name in {"send_candidate_email", "send_reminder_email", "create_candidate_email_draft"}:
            composio = name == "create_candidate_email_draft" or (getattr(settings, "MORGAN_COMPOSIO_OWNER_USER_ID", "") == actor.user_id and bool(getattr(settings, "MORGAN_COMPOSIO_API_KEY", "")))
            if composio:
                client = self._connector(actor)
                await client.call_tool("GMAIL_GET_PROFILE", {})
                review["connected_service"] = "gmail"
            else:
                self._email_available()
            if not person.get("email") or "@" not in person["email"]:
                raise ValidationError("The candidate has no valid saved email")
            if name == "send_reminder_email":
                if interview.get("status") not in {"scheduled", "instant_active"}:
                    raise ValidationError("Reminders require an active scheduled interview")
                subject = f"Interview reminder: {job.get('title') or 'Your interview'}"
                body = f"Hi {person.get('name') or 'there'},\n\nYour interview for {job.get('title') or 'the role'} is scheduled for {interview.get('scheduled_at')}. Please sign in to Intra AI to view your interview details."
            else:
                subject, body = inputs.subject, inputs.body
            review["email"] = {"to": person["email"], "subject": subject, "body": body}
            review["email"]["mode"] = "draft_only" if name == "create_candidate_email_draft" else "send"
        return review

    async def _require_review_unchanged(self, name: str, inputs: ToolInput, actor: auth.Actor, review: dict) -> None:
        """Legacy business services resolve saved slots/state internally.

        Reject a changed target immediately before calling them; never accept a
        newly constructed payload just because an earlier review was approved.
        """
        current = await self._review(name, inputs, actor)
        if json.dumps(current, sort_keys=True) != json.dumps(review, sort_keys=True):
            raise ConflictError("Details changed after confirmation; request a fresh proposal")

    async def _execute(self, name: str, inputs: ToolInput, actor: auth.Actor, confirmation_id: str | None = None, *, review: dict) -> Any:
        from app.voice import bulk
        if name in bulk.BULK_TOOLS:
            return await bulk.execute(self, name, inputs, actor, review=review)
        if name in {"post_recruiting_update_to_slack", "add_interview_to_calendar", "create_candidate_email_draft"}:
            return await self._execute_connected(name, inputs, actor, confirmation_id, review=review)
        if name == "schedule_interview":
            await self._require_review_unchanged(name, inputs, actor, review)
            return await self.scheduling.book_slot(inputs.application_id, inputs.slot_id)
        if name == "reschedule_interview":
            from app.sessions.store import session_store
            async with session_store.get_lock(inputs.interview_id):
                await self._require_review_unchanged(name, inputs, actor, review)
                self._require_not_started(inputs.interview_id)
                interview = await auth.require_interview(actor, inputs.interview_id, self.sb)
                return await self.scheduling.reschedule(interview["application_id"], inputs.slot_id)
        if name == "cancel_interview":
            from app.sessions.store import session_store
            async with session_store.get_lock(inputs.interview_id):
                await self._require_review_unchanged(name, inputs, actor, review)
                self._require_not_started(inputs.interview_id)
                interview = await auth.require_interview(actor, inputs.interview_id, self.sb)
                await self.interview_repo.update(interview["id"], {"status": "cancelled"})
                # Block live entry as soon as the durable cancellation succeeds.
                from app.sessions.models import SessionStatus
                live = session_store.get(interview["id"])
                if live:
                    live.status = SessionStatus.CANCELLED
                    session_store.set(live)
                if interview.get("slot_id"):
                    await self.interview_repo.release_slot(interview["slot_id"])
                await self.app_repo.update_status(interview["application_id"], "shortlisted")
                return {"interview_id": interview["id"], "status": "cancelled", "application_status": "shortlisted", "email_sent": False}
        if name == "update_application_status":
            await self._require_review_unchanged(name, inputs, actor, review)
            method = {"shortlisted": self.applications.shortlist, "rejected": self.applications.reject, "invited": self.applications.invite}[inputs.status]
            return await method(inputs.application_id)
        if name in {"send_candidate_email", "send_reminder_email"}:
            if review.get("connected_service") == "gmail":
                return await self._execute_connected(name, inputs, actor, confirmation_id, review=review)
            self._email_available()
            email = review["email"]
            response = await email_client.send_email(email["to"], email["subject"], "<p>" + html.escape(email["body"]).replace("\n", "<br>") + "</p>")
            if not isinstance(response, dict) or not response.get("id") or response.get("error"):
                raise AppError("Email provider did not confirm acceptance")
            return {"provider": "resend", "provider_message_id": str(response["id"]), "status": "accepted", "delivered": "not_verified"}
        raise ValidationError("Unknown write tool")

    async def _execute_connected(self, name, inputs, actor, confirmation_id, *, review: dict):
        client = self._connector(actor)
        if name == "post_recruiting_update_to_slack":
            return await client.call_tool("SLACK_SEND_MESSAGE", {"channel": review["channel"]["id"], "markdown_text": review["message"]}, confirmation_id=confirmation_id)
        if name == "add_interview_to_calendar":
            return await client.call_tool("GOOGLECALENDAR_CREATE_EVENT", {"calendar_id": review["calendar"]["id"], **review["event"]}, confirmation_id=confirmation_id)
        email = review["email"]
        tool = "GMAIL_CREATE_EMAIL_DRAFT" if name == "create_candidate_email_draft" else "GMAIL_SEND_EMAIL"
        return await client.call_tool(tool, {"recipient_email": email["to"], "subject": email["subject"], "body": email["body"]}, confirmation_id=confirmation_id)

    @staticmethod
    def _require_not_started(interview_id: str) -> None:
        from app.sessions.models import SessionStatus
        from app.sessions.store import session_store
        live = session_store.get(interview_id)
        if live and live.status in {SessionStatus.STARTING, SessionStatus.IN_PROGRESS, SessionStatus.COMPLETED, SessionStatus.CANCELLED}:
            raise ConflictError("This interview has already started or ended")
