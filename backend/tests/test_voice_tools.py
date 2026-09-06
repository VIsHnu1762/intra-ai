"""Controlled tool security/confirmation tests; no providers or live messages."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.integrations.email_client import send_email as real_send_email
from app.voice import authorization as auth
from app.voice import tools


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters, self.offset, self.maximum = [], 0, 10000
        self.membership_filters = []
        self.operation, self.payload = "read", None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, key, values):
        self.membership_filters.append((key, list(values)))
        return self

    def is_(self, key, value):
        self.filters.append((key, None if value == "null" else value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, maximum):
        self.maximum = maximum
        return self

    def range(self, low, high):
        self.offset, self.maximum = low, high - low + 1
        return self

    def update(self, value):
        self.operation, self.payload = "update", value
        return self

    def insert(self, value):
        self.operation, self.payload = "insert", value
        return self

    def execute(self):
        table = self.db.rows.setdefault(self.table, [])
        matches = [item for item in table if all(item.get(key) == value for key, value in self.filters) and all(item.get(key) in values for key, values in self.membership_filters)]
        if self.operation == "update":
            self.db.writes.append((self.table, deepcopy(self.payload)))
            for item in matches:
                item.update(self.payload)
        elif self.operation == "insert":
            self.db.writes.append((self.table, deepcopy(self.payload)))
            additions = self.payload if isinstance(self.payload, list) else [self.payload]
            table.extend(deepcopy(additions))
            matches = additions
        return SimpleNamespace(data=deepcopy(matches[self.offset:self.offset + self.maximum]), count=len(matches))


class DB:
    def __init__(self):
        self.writes = []
        self.rows = {
            "users": [
                {"id": "recruiter-a", "email": "hr-a@example.test", "role": "recruiter", "name": "A"},
                {"id": "recruiter-b", "email": "hr-b@example.test", "role": "recruiter", "name": "B"},
                {"id": "admin", "email": "admin@example.test", "role": "admin"},
                {"id": "user-a", "email": "a@example.test", "role": "candidate"},
                {"id": "user-b", "email": "b@example.test", "role": "candidate"},
            ],
            "jobs": [
                {"id": "job-a", "title": "Engineer", "created_by": "recruiter-a"},
                {"id": "job-b", "title": "Designer", "created_by": "recruiter-b"},
            ],
            "candidates": [
                {"id": "candidate-a", "email": "a@example.test", "name": "Ada", "resume_url": "private-cross-job.pdf", "parsed_resumes": [{"id": "resume-a", "application_id": "application-a", "skills": ["Python"]}, {"id": "resume-other", "application_id": "application-other", "skills": ["private"]}]},
                {"id": "candidate-b", "email": "b@example.test", "name": "Bea"},
            ],
            "applications": [
                {"id": "application-a", "job_id": "job-a", "candidate_id": "candidate-a", "status": "shortlisted", "created_at": "2026-01-01T00:00:00Z"},
                {"id": "application-b", "job_id": "job-b", "candidate_id": "candidate-b", "status": "shortlisted", "created_at": "2026-01-01T00:00:00Z"},
                {"id": "application-other", "job_id": "job-b", "candidate_id": "candidate-a", "status": "applied", "created_at": "2026-01-01T00:00:00Z"},
            ],
            "scheduled_interviews": [],
            "interview_reports": [],
            "interview_slots": [
                {"id": "slot-a", "job_id": "job-a", "date": "2099-01-01", "start_time": "10:00", "end_time": "11:00", "is_booked": False},
                {"id": "slot-a2", "job_id": "job-a", "date": "2099-01-02", "start_time": "10:00", "end_time": "11:00", "is_booked": False},
                {"id": "slot-b", "job_id": "job-b", "date": "2099-01-01", "start_time": "10:00", "end_time": "11:00", "is_booked": False},
            ],
        }

    def table(self, table):
        return Query(self, table)


@pytest.fixture
def db():
    return DB()


@pytest.fixture
def service(db, monkeypatch):
    monkeypatch.setattr(tools.SchedulingService, "_ensure_live_session", lambda *_a, **_k: None)
    monkeypatch.setattr(tools.SchedulingService, "_update_live_session_start", lambda *_a, **_k: None)
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", "")
    monkeypatch.setattr(tools.email_client, "send_email", AsyncMock(side_effect=AssertionError("Unexpected email")))
    return tools.VoiceToolService(db)


def scheduled(db, suffix="a"):
    row = {"id": f"interview-{suffix}", "application_id": f"application-{suffix}", "job_id": f"job-{suffix}", "candidate_id": f"candidate-{suffix}", "status": "scheduled", "slot_id": f"slot-{suffix}", "scheduled_at": "2099-01-01T10:00:00Z", "created_at": "2026-01-01T00:00:00Z"}
    db.rows["scheduled_interviews"].append(row)
    next(item for item in db.rows["applications"] if item["id"] == f"application-{suffix}")["status"] = "scheduled"
    return row


async def call(service, name, args, user="recruiter-a", session="voice-a", **kwargs):
    return await service.call(name, args, user_claims={"sub": user}, session_id=session, **kwargs)


async def confirm(service, pending, user="recruiter-a", session="voice-a"):
    return await service.confirm(pending["pending_action"]["confirmation_id"], user_claims={"sub": user}, session_id=session)


@pytest.mark.asyncio
async def test_claimed_recruiter_role_never_overrides_persisted_candidate(db, service):
    actor = await auth.identity({"sub": "user-a", "role": "admin", "candidate_id": "candidate-b"}, db)
    assert actor.role == "candidate" and actor.candidate_id == "candidate-a"
    with pytest.raises(ForbiddenError):
        await service.call("get_candidate", {"candidate_id": "candidate-a"}, user_claims={"sub": "user-a", "role": "admin"}, session_id="voice-a")


@pytest.mark.asyncio
async def test_deleted_user_and_inactive_user_cannot_use_tools(db, service):
    with pytest.raises(UnauthorizedError):
        await call(service, "search_candidates", {}, user="missing")
    db.rows["users"][0]["is_active"] = False
    with pytest.raises(UnauthorizedError):
        await call(service, "search_candidates", {})


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["recruiter-a", "admin"])
async def test_no_global_admin_or_cross_recruiter_access(db, service, role):
    with pytest.raises(ForbiddenError):
        await call(service, "get_application", {"application_id": "application-b"}, user=role)
    with pytest.raises(ForbiddenError):
        await call(service, "get_candidate", {"candidate_id": "candidate-b"}, user=role)


@pytest.mark.asyncio
async def test_tenant_scoped_identity_not_browser_tenant(db, service):
    db.rows["users"][0]["tenant_id"] = "tenant-a"
    db.rows["jobs"][0]["tenant_id"] = "tenant-a"
    db.rows["jobs"][1]["tenant_id"] = "tenant-b"
    actor = await auth.identity({"sub": "recruiter-a", "tenant_id": "tenant-b"}, db)
    assert actor.tenant_id == "tenant-a"
    assert (await auth.require_job(actor, "job-a", db))["id"] == "job-a"
    with pytest.raises(ForbiddenError):
        await auth.require_job(actor, "job-b", db)
    db.rows["candidates"][0]["tenant_id"] = "tenant-b"
    with pytest.raises(ForbiddenError):
        await call(service, "get_application", {"application_id": "application-a"})


@pytest.mark.asyncio
async def test_unassigned_recruiter_cannot_access_tenant_job(db):
    db.rows["jobs"][0]["tenant_id"] = "tenant-a"
    actor = await auth.identity({"sub": "recruiter-a"}, db)
    with pytest.raises(ForbiddenError):
        await auth.require_job(actor, "job-a", db)


@pytest.mark.asyncio
async def test_candidate_context_uses_owned_application_even_global_signup(db):
    db.rows["jobs"][0]["tenant_id"] = "tenant-a"
    actor = await auth.identity({"sub": "user-a", "email": "b@example.test"}, db)
    assert (await auth.require_job(actor, "job-a", db))["id"] == "job-a"
    with pytest.raises(ForbiddenError):
        await auth.require_candidate(actor, "candidate-b", db)
    with pytest.raises(ForbiddenError):
        await auth.require_application(actor, "application-b", db)


@pytest.mark.asyncio
async def test_candidate_tenant_conflict_is_denied(db):
    db.rows["users"][3]["tenant_id"] = "tenant-a"
    db.rows["jobs"][0]["tenant_id"] = "tenant-b"
    actor = await auth.identity({"sub": "user-a"}, db)
    with pytest.raises(ForbiddenError):
        await auth.require_job(actor, "job-a", db)


@pytest.mark.asyncio
async def test_candidate_resume_is_filtered_to_authorized_applications(service):
    result = await call(service, "get_candidate", {"candidate_id": "candidate-a"})
    assert result["data"]["resumes"] == [{"id": "resume-a", "application_id": "application-a", "skills": ["Python"]}]
    assert "resume_url" not in result["data"]


@pytest.mark.asyncio
async def test_model_visible_read_is_bounded_with_explicit_notice(db, service):
    db.rows["candidates"][0]["parsed_resumes"][0]["projects"] = [{"description": "x" * 10000} for _ in range(80)]
    result = await call(service, "get_candidate", {"candidate_id": "candidate-a"})
    assert result["truncated"] is True
    assert len(result["data"]["resumes"][0]["projects"]) == 50
    assert len(result["data"]["resumes"][0]["projects"][0]["description"]) == 3000


@pytest.mark.asyncio
async def test_search_filters_before_disclosure(service):
    result = await call(service, "search_candidates", {})
    assert len(result["data"]["matches"]) == 1
    assert result["data"]["matches"][0]["application"]["id"] == "application-a"
    assert (await call(service, "search_candidates", {"search": "Bea"}))["data"]["matches"] == []
    with pytest.raises(ForbiddenError):
        await call(service, "search_candidates", {"job_id": "job-b"})


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(tools.TOOL_INPUTS))
async def test_every_tool_rejects_taylor_and_unknown_arguments(service, name):
    with pytest.raises(ForbiddenError):
        await call(service, name, {}, persona="taylor")
    with pytest.raises(ValidationError):
        await call(service, name, {"tenant_id": "tenant-b", "arbitrary_sql": "select *"})


@pytest.mark.asyncio
async def test_unknown_tools_and_invalid_limit_are_rejected(service):
    for name, args in [("execute_sql", {}), ("search_candidates", {"limit": True}), ("get_candidate", {"candidate_id": "../../"})]:
        with pytest.raises(ValidationError):
            await call(service, name, args)


@pytest.mark.asyncio
async def test_get_interview_checks_entire_relationship(db, service):
    row = scheduled(db)
    result = await call(service, "get_interview", {"interview_id": row["id"]})
    assert result["data"]["application_id"] == "application-a"
    row["candidate_id"] = "candidate-b"
    with pytest.raises(ForbiddenError):
        await call(service, "get_interview", {"interview_id": row["id"]})


@pytest.mark.asyncio
async def test_report_links_scope_through_interview(db, service):
    scheduled(db)
    scheduled(db, "b")
    db.rows["reports"] = [{"id": "report-a", "interview_id": "interview-a", "overall_score": 75}, {"id": "report-b", "interview_id": "interview-b", "overall_score": 90}]
    result = await call(service, "get_report", {"report_id": "report-a"})
    assert result["data"]["overall_score"] == 75
    with pytest.raises(ForbiddenError):
        await call(service, "get_report", {"report_id": "report-b"})


@pytest.mark.asyncio
async def test_saved_slots_are_not_claimed_to_be_calendar_availability(service):
    result = await call(service, "find_available_slots", {"job_id": "job-a"})
    assert result["data"]["external_calendar_verified"] is False
    assert len(result["data"]["slots"]) == 2


@pytest.mark.asyncio
async def test_schedule_requires_review_and_one_time_confirmation(db, service):
    args = {"application_id": "application-a", "slot_id": "slot-a"}
    pending = await call(service, "schedule_interview", args)
    assert pending["status"] == "confirmation_required" and db.writes == []
    assert pending["pending_action"]["details"]["slot"]["timezone"] == "UTC"
    args["slot_id"] = "slot-b"
    pending["pending_action"]["details"]["slot"]["id"] = "slot-b"
    result = await confirm(service, pending)
    assert result["status"] == "succeeded"
    assert "room_token" not in result["result"]
    assert db.rows["scheduled_interviews"][0]["slot_id"] == "slot-a"
    writes = len(db.writes)
    replay = await confirm(service, pending)
    assert replay["replayed"] and len(db.writes) == writes


@pytest.mark.asyncio
async def test_confirmation_is_owner_and_session_bound(service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    with pytest.raises(ForbiddenError):
        await confirm(service, pending, user="recruiter-b")
    with pytest.raises(ForbiddenError):
        await confirm(service, pending, session="another-session")


@pytest.mark.asyncio
async def test_confirmation_rechecks_role_ownership_and_time(db, service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    db.rows["users"][0]["role"] = "candidate"
    with pytest.raises(ForbiddenError):
        await confirm(service, pending)
    db.rows["users"][0]["role"] = "recruiter"
    db.rows["jobs"][0]["created_by"] = "recruiter-b"
    with pytest.raises(ForbiddenError):
        await confirm(service, pending)
    db.rows["jobs"][0]["created_by"] = "recruiter-a"
    key = pending["pending_action"]["confirmation_id"]
    service._pending[key].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(ConflictError, match="expired"):
        await confirm(service, pending)
    assert db.writes == []


@pytest.mark.asyncio
async def test_changed_review_invalidates_confirmation(db, service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    db.rows["interview_slots"][0]["start_time"] = "12:00"
    with pytest.raises(ConflictError, match="Details changed"):
        await confirm(service, pending)
    assert db.writes == []


@pytest.mark.asyncio
async def test_decline_prevents_execution(db, service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    key = pending["pending_action"]["confirmation_id"]
    result = await service.decline(key, user_claims={"sub": "recruiter-a"}, session_id="voice-a")
    assert result["status"] == "declined"
    assert (await confirm(service, pending))["status"] == "declined"
    assert db.writes == []


@pytest.mark.asyncio
async def test_reschedule_moves_only_matching_interview_and_slot(db, service):
    scheduled(db)
    pending = await call(service, "reschedule_interview", {"interview_id": "interview-a", "slot_id": "slot-a2"})
    result = await confirm(service, pending)
    assert result["status"] == "succeeded"
    assert db.rows["scheduled_interviews"][0]["slot_id"] == "slot-a2"
    with pytest.raises(ForbiddenError):
        await call(service, "reschedule_interview", {"interview_id": "interview-a", "slot_id": "slot-b"})


@pytest.mark.asyncio
async def test_schedule_cannot_book_other_jobs_slot(service):
    with pytest.raises(ForbiddenError):
        await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-b"})


@pytest.mark.asyncio
async def test_cancel_does_not_evaluate_or_send_email(db, service):
    scheduled(db)
    pending = await call(service, "cancel_interview", {"interview_id": "interview-a"})
    assert db.writes == []
    result = await confirm(service, pending)
    assert result["status"] == "succeeded"
    assert db.rows["scheduled_interviews"][0]["status"] == "cancelled"
    assert db.rows["applications"][0]["status"] == "shortlisted"
    assert not any(table in {"reports", "evaluations", "candidate_answers"} for table, _ in db.writes)
    tools.email_client.send_email.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["in_progress", "completed", "cancelled"])
async def test_cancel_rejects_started_or_terminal_interview(db, service, status):
    row = scheduled(db)
    row["status"] = status
    with pytest.raises(ValidationError):
        await call(service, "cancel_interview", {"interview_id": "interview-a"})


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["invited", "rejected", "shortlisted"])
async def test_status_tools_use_existing_business_services(db, service, status):
    pending = await call(service, "update_application_status", {"application_id": "application-a", "status": status})
    result = await confirm(service, pending)
    assert result["status"] == "succeeded"
    assert db.rows["applications"][0]["status"] == status


@pytest.mark.asyncio
async def test_status_tools_cannot_fabricate_evaluation_outcomes(service):
    with pytest.raises(ValidationError):
        await call(service, "update_application_status", {"application_id": "application-a", "status": "completed"})


@pytest.mark.asyncio
async def test_unconfigured_email_never_claims_success(service):
    with pytest.raises(ValidationError, match="not configured"):
        await call(service, "send_candidate_email", {"application_id": "application-a", "subject": "Hello", "body": "Hello"})
    tools.email_client.send_email.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("sender", ["", "   ", "noreply@localhost:3000", "not-an-email", "Intra AI <>", "qa@example.com\r\nCc: attacker@example.com", "qa@example.com,attacker@example.com"])
async def test_morgan_requires_valid_explicit_resend_sender(service, monkeypatch, sender):
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "fake-test-only")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", sender)
    with pytest.raises(ValidationError, match="verified Resend domain"):
        await call(service, "send_candidate_email", {"application_id": "application-a", "subject": "Hello", "body": "Hello"})
    tools.email_client.send_email.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("sender,expected", [("Intra AI QA <qa@example.com>", "Intra AI QA <qa@example.com>"), (" hr@example.com ", "hr@example.com"), ("", "Intra AI <noreply@app.example.com>")])
async def test_shared_email_client_uses_explicit_sender_and_preserves_legacy_fallback(service, monkeypatch, sender, expected):
    import httpx
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "fake-test-only")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", sender)
    monkeypatch.setattr(tools.settings, "FRONTEND_URL", "https://app.example.com")
    post = AsyncMock(return_value=httpx.Response(200, json={"id": "fake-provider-message"}))

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *args, **kwargs):
            return await post(*args, **kwargs)

    monkeypatch.setattr(tools.email_client.httpx, "AsyncClient", FakeClient)
    result = await real_send_email("candidate@example.com", "Hello", "<p>Hello</p>")
    assert result == {"id": "fake-provider-message"}
    assert post.call_args.kwargs["json"]["from"] == expected
    assert post.call_args.kwargs["json"]["to"] == ["candidate@example.com"]
    assert post.call_args.args[0] == "https://api.resend.com/emails"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["send_candidate_email", "send_reminder_email"])
async def test_email_uses_saved_recipient_and_requires_confirmation(db, service, monkeypatch, name):
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "fake-test-only")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", "Intra AI QA <qa@example.com>")
    send = AsyncMock(return_value={"id": "provider-message"})
    monkeypatch.setattr(tools.email_client, "send_email", send)
    scheduled(db)
    args = {"interview_id": "interview-a"} if name == "send_reminder_email" else {"application_id": "application-a", "subject": "Hello", "body": "<script>not html</script>"}
    pending = await call(service, name, args)
    assert pending["pending_action"]["details"]["email"]["to"] == "a@example.test"
    send.assert_not_called()
    result = await confirm(service, pending)
    assert result["result"]["status"] == "accepted"
    assert result["result"]["delivered"] == "not_verified"
    assert send.call_args.args[0] == "a@example.test"
    assert "<script>" not in send.call_args.args[2]


@pytest.mark.asyncio
async def test_email_failure_and_timeout_are_safe_non_replayed(db, service, monkeypatch):
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "fake-test-only")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", "Intra AI QA <qa@example.com>")
    send = AsyncMock(side_effect=RuntimeError("secret-provider-token"))
    monkeypatch.setattr(tools.email_client, "send_email", send)
    pending = await call(service, "send_candidate_email", {"application_id": "application-a", "subject": "Hello", "body": "Hello"})
    result = await confirm(service, pending)
    assert result["status"] == "failed" and "secret-provider-token" not in str(result)
    assert (await confirm(service, pending))["replayed"]
    send.assert_awaited_once()


class PendingStore:
    def __init__(self):
        self.values, self.claims = {}, set()

    async def get(self, key):
        return deepcopy(self.values.get(key))

    async def put(self, key, value, ttl):
        assert ttl > 0
        self.values[key] = deepcopy(value)

    async def claim(self, key):
        if key in self.claims:
            return False
        self.claims.add(key)
        return True


@pytest.mark.asyncio
async def test_pending_survives_service_restart_and_cannot_execute_twice(db, service):
    store = PendingStore()
    service.pending_store = store
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    other = tools.VoiceToolService(db, pending_store=store)
    assert (await confirm(other, pending))["status"] == "succeeded"
    assert (await confirm(service, pending))["replayed"]
    assert len(db.rows["scheduled_interviews"]) == 1


@pytest.mark.asyncio
async def test_completed_confirmation_replay_rechecks_resource_access(db, service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    assert (await confirm(service, pending))["status"] == "succeeded"
    db.rows["jobs"][0]["created_by"] = "recruiter-b"
    with pytest.raises(ForbiddenError):
        await confirm(service, pending)


@pytest.mark.asyncio
async def test_persisted_inflight_claim_never_reexecutes(db, service):
    store = PendingStore()
    service.pending_store = store
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    key = pending["pending_action"]["confirmation_id"]
    assert await store.claim(key)
    fresh = tools.VoiceToolService(db, pending_store=store)
    with pytest.raises(ConflictError, match="already claimed"):
        await confirm(fresh, pending)
    assert db.writes == []


@pytest.mark.asyncio
async def test_confirmation_rejects_changed_recipient(db, service, monkeypatch):
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "fake-test-only")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", "Intra AI QA <qa@example.com>")
    pending = await call(service, "send_candidate_email", {"application_id": "application-a", "subject": "Hello", "body": "Hello"})
    db.rows["candidates"][0]["email"] = "changed@example.test"
    with pytest.raises(ConflictError, match="Details changed"):
        await confirm(service, pending)
    tools.email_client.send_email.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args", [("send_candidate_email", {"application_id": "application-a", "subject": "Hi\r\nCc: attacker", "body": "Hi"}), ("send_candidate_email", {"application_id": "application-a", "to": "attacker@example.test", "subject": "Hi", "body": "Hi"})])
async def test_email_recipient_and_header_injection_rejected(service, tool, args):
    with pytest.raises(ValidationError):
        await call(service, tool, args)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,args", [("cancel_interview", {"interview_id": "interview-a"}), ("reschedule_interview", {"interview_id": "interview-a", "slot_id": "slot-a2"})])
async def test_live_start_blocks_scheduling_mutations(db, service, monkeypatch, tool, args):
    from app.sessions.models import SessionStatus
    from app.sessions.store import session_store
    scheduled(db)
    monkeypatch.setattr(session_store, "get", lambda _key: SimpleNamespace(status=SessionStatus.STARTING))
    with pytest.raises(ConflictError):
        await call(service, tool, args)
    assert db.writes == []


@pytest.mark.asyncio
async def test_concurrent_confirmations_execute_once(db, service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    results = await asyncio.gather(confirm(service, pending), confirm(service, pending))
    assert all(result["status"] == "succeeded" for result in results)
    assert len(db.rows["scheduled_interviews"]) == 1


@pytest.mark.asyncio
async def test_provider_error_without_message_id_is_not_sent(db, service, monkeypatch):
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "fake-test-only")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", "Intra AI QA <qa@example.com>")
    monkeypatch.setattr(tools.email_client, "send_email", AsyncMock(return_value={"message": "bad credential"}))
    pending = await call(service, "send_candidate_email", {"application_id": "application-a", "subject": "Hello", "body": "Hello"})
    assert (await confirm(service, pending))["status"] == "failed"


def test_schema_allowlist_is_exact_and_closed():
    schemas = tools.tool_schemas()
    assert {schema["name"] for schema in schemas} == {
        "list_jobs", "get_recruiting_overview", "list_interview_templates", "get_interview_template",
        "bulk_shortlist_candidates", "bulk_schedule_interviews", "get_connected_services",
        "list_connected_calendars", "list_slack_channels", "create_candidate_email_draft",
        "add_interview_to_calendar", "post_recruiting_update_to_slack", "search_candidates",
        "get_candidate", "get_application", "get_interview", "get_report", "find_available_slots",
        "schedule_interview", "reschedule_interview", "cancel_interview", "update_application_status",
        "send_candidate_email", "send_reminder_email",
    }
    assert all(schema["inputSchema"]["additionalProperties"] is False for schema in schemas)
    assert "confirm" not in {schema["name"] for schema in schemas}
    by_name = {schema["name"]: schema for schema in schemas}
    bulk, single = by_name["bulk_shortlist_candidates"], by_name["update_application_status"]
    assert "two or more explicitly selected candidates" in bulk["description"]
    assert "Do not split this request" in bulk["description"]
    assert "exactly one application" in single["description"]
    assert "bulk_shortlist_candidates once" in single["description"]
    assert bulk["inputSchema"]["required"] == ["application_ids"]
    ids = bulk["inputSchema"]["properties"]["application_ids"]
    assert ids["type"] == "array" and ids["maxItems"] == 50
    assert "not candidate IDs or names" in ids["description"]
    assert single["inputSchema"]["properties"]["application_id"]["type"] == "string"


async def read_result(service, pending, user="recruiter-a", session="voice-a", persona="morgan"):
    return await service.read_result(pending["pending_action"]["confirmation_id"], user_claims={"sub": user}, session_id=session, persona=persona)


@pytest.mark.asyncio
@pytest.mark.parametrize("action,args", [("schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"}), ("update_application_status", {"application_id": "application-a", "status": "rejected"})])
async def test_read_result_accepts_changed_business_state_without_mutation(db, service, action, args):
    pending = await call(service, action, args)
    completed = await confirm(service, pending)
    writes = deepcopy(db.writes)
    assert await read_result(service, pending) == completed
    result = await read_result(service, pending)
    result["message"] = "tampered"
    assert (await read_result(service, pending))["message"] != "tampered"
    assert db.writes == writes


@pytest.mark.asyncio
@pytest.mark.parametrize("user,session,persona", [("recruiter-b", "voice-a", "morgan"), ("recruiter-a", "voice-b", "morgan"), ("recruiter-a", "voice-a", "taylor"), ("user-a", "voice-a", "morgan")])
async def test_read_result_enforces_identity_session_and_persona(service, user, session, persona):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    await confirm(service, pending)
    with pytest.raises(ForbiddenError):
        await read_result(service, pending, user=user, session=session, persona=persona)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["role", "tenant", "job", "candidate", "slot", "application"])
async def test_read_result_reauthorizes_all_original_resources(db, service, change):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    await confirm(service, pending)
    if change == "role":
        db.rows["users"][0]["role"] = "candidate"
    elif change == "tenant":
        db.rows["users"][0]["tenant_id"] = "changed-tenant"
    elif change == "job":
        db.rows["jobs"][0]["created_by"] = "recruiter-b"
    elif change == "candidate":
        db.rows["candidates"][0]["tenant_id"] = "other-tenant"
    elif change == "slot":
        db.rows["interview_slots"][0]["job_id"] = "job-b"
    elif change == "application":
        db.rows["applications"][0]["candidate_id"] = "candidate-b"
    writes = deepcopy(db.writes)
    with pytest.raises(ForbiddenError):
        await read_result(service, pending)
    assert db.writes == writes


@pytest.mark.asyncio
async def test_read_result_expired_and_missing_fail_not_found(db, service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    await confirm(service, pending)
    key = pending["pending_action"]["confirmation_id"]
    service._pending[key].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(NotFoundError):
        await read_result(service, pending)
    with pytest.raises(NotFoundError):
        await service.read_result("missing", user_claims={"sub": "recruiter-a"}, session_id="voice-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "executing", "invalidated"])
async def test_read_result_never_executes_nonterminal_action(db, service, state):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    service._pending[pending["pending_action"]["confirmation_id"]].status = state
    with pytest.raises(ConflictError):
        await read_result(service, pending)
    assert db.writes == []


@pytest.mark.asyncio
async def test_declined_and_failed_results_are_readable_and_bound(db, service, monkeypatch):
    declined = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    key = declined["pending_action"]["confirmation_id"]
    result = await service.decline(key, user_claims={"sub": "recruiter-a"}, session_id="voice-a")
    assert result["confirmation_id"] == key
    assert await read_result(service, declined) == result
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "fake-test-only")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", "Intra AI QA <qa@example.com>")
    failed = await call(service, "send_candidate_email", {"application_id": "application-a", "subject": "Hello", "body": "Hello"})
    result = await confirm(service, failed)
    assert result["status"] == "failed"
    assert await read_result(service, failed) == result


@pytest.mark.asyncio
async def test_read_result_restored_from_shared_store(db, service):
    store = PendingStore()
    service.pending_store = store
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    completed = await confirm(service, pending)
    restored = tools.VoiceToolService(db, pending_store=store)
    assert await read_result(restored, pending) == completed
    assert len(db.rows["scheduled_interviews"]) == 1


async def read_pending(service, pending, user="recruiter-a", session="voice-a", persona="morgan"):
    return await service.read_pending(pending["pending_action"]["confirmation_id"], user_claims={"sub": user}, session_id=session, persona=persona)


@pytest.mark.asyncio
async def test_pending_review_is_readable_without_revalidating_business_state(db, service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    db.rows["applications"][0]["status"] = "rejected"
    assert await read_pending(service, pending) == pending
    assert db.writes == []
    with pytest.raises(ValidationError):
        await confirm(service, pending)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["job", "candidate", "slot", "tenant", "role"])
async def test_pending_review_reauthorizes_before_exposing_personal_details(db, service, change):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    if change == "job":
        db.rows["jobs"][0]["created_by"] = "recruiter-b"
    elif change == "candidate":
        db.rows["candidates"][0]["tenant_id"] = "other-tenant"
    elif change == "slot":
        db.rows["interview_slots"][0]["job_id"] = "job-b"
    elif change == "tenant":
        db.rows["users"][0]["tenant_id"] = "other-tenant"
    elif change == "role":
        db.rows["users"][0]["role"] = "candidate"
    with pytest.raises(ForbiddenError):
        await read_pending(service, pending)
    assert db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("user,session,persona", [("recruiter-b", "voice-a", "morgan"), ("recruiter-a", "voice-b", "morgan"), ("recruiter-a", "voice-a", "taylor")])
async def test_pending_review_owner_session_persona_boundary(service, user, session, persona):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    with pytest.raises(ForbiddenError):
        await read_pending(service, pending, user=user, session=session, persona=persona)


@pytest.mark.asyncio
async def test_pending_review_expired_and_terminal_fail_closed(service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    key = pending["pending_action"]["confirmation_id"]
    await service.decline(key, user_claims={"sub": "recruiter-a"}, session_id="voice-a")
    with pytest.raises(ConflictError):
        await read_pending(service, pending)
    service._pending[key].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(NotFoundError):
        await read_pending(service, pending)


@pytest.mark.asyncio
async def test_read_result_reauthorizes_original_and_new_slot_relationships(db, service):
    scheduled(db)
    pending = await call(service, "reschedule_interview", {"interview_id": "interview-a", "slot_id": "slot-a2"})
    assert (await confirm(service, pending))["status"] == "succeeded"
    db.rows["interview_slots"][0]["job_id"] = "job-b"
    with pytest.raises(ForbiddenError):
        await read_result(service, pending)


@pytest.mark.asyncio
async def test_read_result_reauthorizes_newly_created_interview(db, service):
    pending = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    assert (await confirm(service, pending))["status"] == "succeeded"
    db.rows["scheduled_interviews"][0]["candidate_id"] = "candidate-b"
    with pytest.raises(ForbiddenError):
        await read_result(service, pending)
