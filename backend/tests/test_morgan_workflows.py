"""HR workflow boundaries, persisted batches, and explicit connector actions."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.voice import tools
from tests.test_voice_tools import db, service, call, confirm, scheduled, read_result, PendingStore


@pytest.fixture
def batch(db):
    db.rows["applications"][0]["status"] = "applied"
    db.rows["candidates"].append({"id": "candidate-c", "name": "Chris", "email": "chris@example.test"})
    db.rows["applications"].append({"id": "application-c", "job_id": "job-a", "candidate_id": "candidate-c", "status": "rejected", "created_at": "2026-01-01T00:00:00Z"})
    db.rows["interview_templates"] = [{"id": "template-a", "name": "Intern interview", "description": "QA",
        "created_by": "recruiter-a", "tenant_id": None, "version": 1, "archived_at": None,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        "duration_minutes": 20, "rounds": [{"id": "intro", "type": "introduction", "name": "Introduction",
            "enabled": True, "duration_minutes": 20, "agent_ids": ["alex", "jordan"], "focus_areas": ["Communication"]}]}]
    return ["application-a", "application-c"]


def schedule_args(batch, **overrides):
    return {"application_ids": batch, "job_id": "job-a", "template_id": "template-a",
            "start_at": "2099-01-01T15:30:00+05:30", "timezone": "Asia/Kolkata", "gap_minutes": 5, **overrides}


def change_after_review(service, change):
    """Model another request editing data while the durable claim is awaited."""
    class EditingStore(PendingStore):
        async def claim(self, key):
            claimed = await super().claim(key)
            if claimed:
                change()
            return claimed
    service.pending_store = EditingStore()


@pytest.mark.asyncio
async def test_bulk_shortlist_review_and_replay_persist_once(db, service, batch):
    proposal = await call(service, "bulk_shortlist_candidates", {"application_ids": batch})
    details = proposal["pending_action"]["details"]
    assert details["eligible_count"] == 2 and details["items"][0]["candidate"]["name"] == "Ada"
    assert db.writes == []
    first = await confirm(service, proposal)
    assert first["status"] == "succeeded" and first["result"]["succeeded"] == 2
    writes = deepcopy(db.writes)
    assert (await confirm(service, proposal))["replayed"] is True
    assert db.writes == writes
    assert all(row["status"] == "shortlisted" for row in db.rows["applications"] if row["id"] in batch)
    assert not tools.email_client.send_email.called


@pytest.mark.asyncio
@pytest.mark.parametrize("ids,error", [(["application-a", "application-b"], ForbiddenError), (["application-a", "missing"], NotFoundError), (["application-a", "application-a"], ValidationError)])
async def test_batch_preflight_rejects_unauthorized_missing_or_duplicate_without_writes(db, service, ids, error):
    with pytest.raises(error):
        await call(service, "bulk_shortlist_candidates", {"application_ids": ids})
    assert db.writes == []


@pytest.mark.asyncio
async def test_bulk_schedule_copies_reviewed_template_and_uses_consecutive_slots(db, service, batch):
    proposal = await call(service, "bulk_schedule_interviews", schedule_args(batch))
    items = proposal["pending_action"]["details"]["items"]
    assert [item["scheduled_at"] for item in items] == ["2099-01-01T10:00:00+00:00", "2099-01-01T10:25:00+00:00"]
    assert db.writes == []
    result = await confirm(service, proposal)
    assert result["status"] == "succeeded" and result["result"]["succeeded"] == 2
    booked = db.rows["scheduled_interviews"]
    assert len(booked) == 2 and all(row["duration_minutes"] == 20 for row in booked)
    assert booked[0]["template_snapshot"]["rounds"][0]["agent_ids"] == ["alex", "jordan"]
    db.rows["interview_templates"][0]["rounds"][0]["agent_ids"] = ["alex"]
    assert booked[0]["template_snapshot"]["rounds"][0]["agent_ids"] == ["alex", "jordan"]
    assert result["result"]["email_sent"] is False
    assert result["result"]["external_calendar_created"] is False
    assert not tools.email_client.send_email.called


@pytest.mark.asyncio
async def test_claim_time_template_edit_cannot_replace_confirmed_snapshot_or_times(db, service, batch):
    def edit():
        template = db.rows["interview_templates"][0]
        template.update(version=2, duration_minutes=30)
        template["rounds"][0].update(duration_minutes=30, agent_ids=["jordan"])
    change_after_review(service, edit)
    proposal = await call(service, "bulk_schedule_interviews", schedule_args(batch))
    approved = deepcopy(proposal["pending_action"]["details"])
    result = await confirm(service, proposal)
    assert result["status"] == "succeeded"
    booked = db.rows["scheduled_interviews"]
    assert [row["scheduled_at"] for row in booked] == [item["scheduled_at"] for item in approved["items"]]
    assert all(row["template_snapshot"] == approved["template"] and row["duration_minutes"] == 20 for row in booked)
    assert db.rows["interview_templates"][0]["duration_minutes"] == 30
    before = deepcopy(db.writes)
    assert (await confirm(service, proposal))["replayed"] is True
    assert db.writes == before


@pytest.mark.asyncio
async def test_claim_time_status_change_does_not_shift_later_reviewed_slots(db, service, batch):
    change_after_review(service, lambda: db.rows["applications"][0].update(status="completed"))
    proposal = await call(service, "bulk_schedule_interviews", schedule_args(batch))
    result = await confirm(service, proposal)
    assert result["status"] == "partial"
    assert [item["status"] for item in result["result"]["items"]] == ["failed", "succeeded"]
    assert db.rows["applications"][0]["status"] == "completed"
    assert len(db.rows["scheduled_interviews"]) == 1
    assert db.rows["scheduled_interviews"][0]["scheduled_at"] == "2099-01-01T10:25:00+00:00"


@pytest.mark.asyncio
async def test_claim_time_active_interview_prevents_duplicate_booking_without_shifting_batch(db, service, batch):
    def add_interview():
        # A concurrent durable booking can precede its application-status update.
        db.rows["scheduled_interviews"].append({"id": "concurrent-interview", "application_id": "application-a",
            "candidate_id": "candidate-a", "job_id": "job-a", "status": "scheduled"})
    change_after_review(service, add_interview)
    proposal = await call(service, "bulk_schedule_interviews", schedule_args(batch))
    result = await confirm(service, proposal)
    assert result["status"] == "partial"
    assert [item["status"] for item in result["result"]["items"]] == ["failed", "succeeded"]
    assert sum(row["application_id"] == "application-a" for row in db.rows["scheduled_interviews"]) == 1
    assert db.rows["applications"][0]["status"] == "applied"
    assert db.rows["scheduled_interviews"][1]["scheduled_at"] == "2099-01-01T10:25:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["job_owner", "role", "candidate_relationship"])
async def test_claim_time_access_or_relationship_change_stops_batch_before_writes(db, service, batch, change):
    def edit():
        if change == "job_owner":
            db.rows["jobs"][0]["created_by"] = "recruiter-b"
        elif change == "role":
            db.rows["users"][0]["role"] = "candidate"
        else:
            db.rows["applications"][0]["candidate_id"] = "candidate-c"
    change_after_review(service, edit)
    proposal = await call(service, "bulk_schedule_interviews", schedule_args(batch))
    assert (await confirm(service, proposal))["status"] == "failed"
    assert db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [
    {"start_at": "2099-01-01T15:30:00"}, {"start_at": "2099-01-01T15:30:00Z"},
    {"timezone": "not-a-zone"}, {"start_at": "2000-01-01T15:30:00+05:30"},
    {"start_at": "2099-01-01T23:50:00Z", "timezone": "UTC"},
])
async def test_bulk_schedule_invalid_times_never_partially_shortlist(db, service, batch, overrides):
    with pytest.raises(ValidationError):
        await call(service, "bulk_schedule_interviews", schedule_args(batch, **overrides))
    assert db.writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["template", "candidate", "status", "ownership"])
async def test_batch_confirmation_rechecks_reviewed_details(db, service, batch, change):
    proposal = await call(service, "bulk_schedule_interviews", schedule_args(batch))
    if change == "template":
        db.rows["interview_templates"][0]["version"] = 2
    elif change == "candidate":
        db.rows["candidates"][0]["email"] = "changed@example.test"
    elif change == "status":
        db.rows["applications"][0]["status"] = "completed"
    else:
        db.rows["jobs"][0]["created_by"] = "recruiter-b"
    with pytest.raises((ConflictError, ForbiddenError)):
        await confirm(service, proposal)
    assert db.writes == []
    if change != "ownership":
        result = await read_result(service, proposal)
        assert result["status"] == "failed" and result["outcome_unknown"] is False
        assert result["code"] == "details_changed"


@pytest.mark.asyncio
async def test_batch_skips_active_interview_without_consuming_first_slot(db, service, batch):
    scheduled(db)
    proposal = await call(service, "bulk_schedule_interviews", schedule_args(batch))
    details = proposal["pending_action"]["details"]
    assert details["skipped_count"] == 1 and details["eligible_count"] == 1
    assert details["items"][1]["scheduled_at"] == "2099-01-01T10:00:00+00:00"
    result = await confirm(service, proposal)
    assert result["result"]["skipped"] == 1 and result["result"]["succeeded"] == 1
    assert len(db.rows["scheduled_interviews"]) == 2


@pytest.mark.asyncio
async def test_partial_batch_reports_each_outcome_and_does_not_retry(db, service, batch, monkeypatch):
    original = service.applications.shortlist
    async def shortlist(app_id):
        if app_id == "application-c":
            raise RuntimeError("synthetic failure")
        return await original(app_id)
    monkeypatch.setattr(service.applications, "shortlist", shortlist)
    proposal = await call(service, "bulk_shortlist_candidates", {"application_ids": batch})
    result = await confirm(service, proposal)
    assert result["status"] == "partial"
    assert [item["status"] for item in result["result"]["items"]] == ["succeeded", "failed"]
    writes = deepcopy(db.writes)
    assert (await confirm(service, proposal))["replayed"]
    assert db.writes == writes


@pytest.mark.asyncio
async def test_polling_result_during_slow_execution_is_nonblocking(db, service, monkeypatch):
    proposal = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    entered, release = asyncio.Event(), asyncio.Event()
    async def slow(*args, **kwargs):
        entered.set()
        await release.wait()
        return {"status": "synthetic-complete"}
    monkeypatch.setattr(service, "_execute", slow)
    task = asyncio.create_task(confirm(service, proposal))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        receipt = await asyncio.wait_for(read_result(service, proposal), .2)
        assert receipt["status"] == "executing" and db.writes == []
        key = proposal["pending_action"]["confirmation_id"]
        assert service._pending[key].expires_at > datetime.now(timezone.utc) + timedelta(minutes=50)
    finally:
        release.set()
        await task
    assert (await read_result(service, proposal))["status"] == "succeeded"


@pytest.mark.asyncio
async def test_interrupted_action_has_unknown_outcome_without_replay(db, service):
    proposal = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    key = proposal["pending_action"]["confirmation_id"]
    result = await service.mark_interrupted(key, user_claims={"sub": "recruiter-a"}, session_id="voice-a")
    assert result["status"] == "failed" and result["outcome_unknown"] is True
    assert (await confirm(service, proposal))["replayed"] is True
    assert db.writes == []
    with pytest.raises(ForbiddenError):
        await service.mark_interrupted(key, user_claims={"sub": "recruiter-b"}, session_id="voice-a")


@pytest.mark.asyncio
async def test_interruption_recovery_preserves_completed_result(db, service):
    proposal = await call(service, "schedule_interview", {"application_id": "application-a", "slot_id": "slot-a"})
    completed = await confirm(service, proposal)
    writes = deepcopy(db.writes)
    result = await service.mark_interrupted(proposal["pending_action"]["confirmation_id"], user_claims={"sub": "recruiter-a"}, session_id="voice-a")
    assert result == completed and db.writes == writes


@pytest.fixture
def connector(service, monkeypatch):
    client = AsyncMock()
    async def connected(name, args, **kwargs):
        if name == "SLACK_LIST_CONVERSATIONS":
            return {"channels": [{"id": "C123", "name": "hiring", "is_archived": False}]}
        if name == "GOOGLECALENDAR_LIST_CALENDARS":
            return {"calendars": [{"id": "hr@example.test", "summary": "HR", "primary": True, "accessRole": "owner"}]}
        if name == "GMAIL_GET_PROFILE":
            return {"verified": True}
        return {"status": "accepted", "provider_id": "test-receipt", "delivered": "not_verified"}
    client.call_tool.side_effect = connected
    monkeypatch.setattr(service, "_connector", lambda _actor: client)
    return client


@pytest.mark.asyncio
async def test_gmail_draft_uses_saved_candidate_recipient_and_claimed_confirmation(service, connector):
    proposal = await call(service, "create_candidate_email_draft", {"application_id": "application-a", "subject": "Next step", "body": "Please review your interview slot."})
    assert proposal["pending_action"]["details"]["email"]["to"] == "a@example.test"
    assert all(c.args[0] == "GMAIL_GET_PROFILE" for c in connector.call_tool.call_args_list)
    result = await confirm(service, proposal)
    assert result["status"] == "succeeded"
    writes = [c for c in connector.call_tool.call_args_list if c.args[0] == "GMAIL_CREATE_EMAIL_DRAFT"]
    assert len(writes) == 1
    assert writes[0].kwargs["confirmation_id"] == proposal["pending_action"]["confirmation_id"]
    assert writes[0].args[1]["recipient_email"] == "a@example.test"
    await confirm(service, proposal)
    assert sum(c.args[0] == "GMAIL_CREATE_EMAIL_DRAFT" for c in connector.call_tool.call_args_list) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["create_candidate_email_draft", "send_candidate_email", "send_reminder_email"])
async def test_claim_time_email_edit_never_changes_confirmed_recipient(db, service, connector, monkeypatch, name):
    monkeypatch.setattr(tools.settings, "MORGAN_COMPOSIO_OWNER_USER_ID", "recruiter-a")
    monkeypatch.setattr(tools.settings, "MORGAN_COMPOSIO_API_KEY", "synthetic-connector-key")
    args = {"application_id": "application-a", "subject": "Next step", "body": "Reviewed body"}
    if name == "send_reminder_email":
        scheduled(db)
        args = {"interview_id": "interview-a"}
    change_after_review(service, lambda: db.rows["candidates"][0].update(email="changed@example.test"))
    proposal = await call(service, name, args)
    approved = proposal["pending_action"]["details"]["email"]
    assert (await confirm(service, proposal))["status"] == "succeeded"
    target = "GMAIL_CREATE_EMAIL_DRAFT" if name == "create_candidate_email_draft" else "GMAIL_SEND_EMAIL"
    writes = [c for c in connector.call_tool.call_args_list if c.args[0] == target]
    assert len(writes) == 1
    assert writes[0].args[1] == {"recipient_email": approved["to"], "subject": approved["subject"], "body": approved["body"]}
    assert approved["to"] == "a@example.test"


@pytest.mark.asyncio
async def test_claim_time_email_edit_never_changes_resend_recipient(db, service, monkeypatch):
    monkeypatch.setattr(tools.settings, "MORGAN_COMPOSIO_OWNER_USER_ID", "")
    monkeypatch.setattr(tools.settings, "RESEND_API_KEY", "synthetic-resend-key")
    monkeypatch.setattr(tools.settings, "RESEND_FROM_EMAIL", "hr@example.com")
    sender = AsyncMock(return_value={"id": "synthetic-receipt"})
    monkeypatch.setattr(tools.email_client, "send_email", sender)
    change_after_review(service, lambda: db.rows["candidates"][0].update(email="changed@example.test"))
    proposal = await call(service, "send_candidate_email", {"application_id": "application-a", "subject": "Next step", "body": "Reviewed body"})
    assert (await confirm(service, proposal))["status"] == "succeeded"
    sender.assert_awaited_once_with("a@example.test", "Next step", "<p>Reviewed body</p>")


@pytest.mark.asyncio
async def test_calendar_export_reviews_existing_slot_and_notification_choice(db, service, connector):
    scheduled(db)
    proposal = await call(service, "add_interview_to_calendar", {"interview_id": "interview-a"})
    event = proposal["pending_action"]["details"]["event"]
    assert event["start_datetime"] == "2099-01-01T10:00:00+00:00"
    assert event["attendees"] == ["a@example.test"] and event["send_updates"] == "none"
    assert (await confirm(service, proposal))["status"] == "succeeded"
    event_calls = [c for c in connector.call_tool.call_args_list if c.args[0] == "GOOGLECALENDAR_CREATE_EVENT"]
    assert len(event_calls) == 1 and event_calls[0].args[1]["send_updates"] == "none"


@pytest.mark.asyncio
async def test_claim_time_calendar_edit_cannot_replace_confirmed_event(db, service, connector):
    row = scheduled(db)
    def edit():
        row.update(scheduled_at="2099-02-01T15:00:00Z", duration_minutes=30)
        db.rows["candidates"][0]["email"] = "changed@example.test"
    change_after_review(service, edit)
    proposal = await call(service, "add_interview_to_calendar", {"interview_id": "interview-a", "notify_candidate": True})
    approved = deepcopy(proposal["pending_action"]["details"])
    assert (await confirm(service, proposal))["status"] == "succeeded"
    writes = [c for c in connector.call_tool.call_args_list if c.args[0] == "GOOGLECALENDAR_CREATE_EVENT"]
    assert len(writes) == 1
    assert writes[0].args[1] == {"calendar_id": approved["calendar"]["id"], **approved["event"]}
    assert writes[0].args[1]["start_datetime"] == "2099-01-01T10:00:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["schedule_interview", "reschedule_interview", "cancel_interview", "update_application_status"])
async def test_individual_business_mutation_rejects_claim_time_target_changes(db, service, action):
    args = {"application_id": "application-a", "slot_id": "slot-a"}
    if action in {"reschedule_interview", "cancel_interview"}:
        interview = scheduled(db)
        args = {"interview_id": interview["id"], **({"slot_id": "slot-a2"} if action == "reschedule_interview" else {})}
    elif action == "update_application_status":
        args = {"application_id": "application-a", "status": "rejected"}
    def edit():
        if action in {"schedule_interview", "reschedule_interview"}:
            slot_id = args["slot_id"]
            next(row for row in db.rows["interview_slots"] if row["id"] == slot_id)["start_time"] = "10:30"
        else:
            db.rows["applications"][0]["status"] = "in_progress"
    change_after_review(service, edit)
    proposal = await call(service, action, args)
    assert (await confirm(service, proposal))["status"] == "failed"
    assert db.writes == []
    assert (await confirm(service, proposal))["replayed"] is True


@pytest.mark.asyncio
async def test_slack_update_requires_review_of_channel_and_exact_message(service, connector):
    proposal = await call(service, "post_recruiting_update_to_slack", {"job_id": "job-a", "channel_id": "C123", "message": "Interviews are scheduled."})
    assert proposal["pending_action"]["details"]["channel"] == {"id": "C123", "name": "hiring"}
    assert not any(c.args[0] == "SLACK_SEND_MESSAGE" for c in connector.call_tool.call_args_list)
    assert (await confirm(service, proposal))["status"] == "succeeded"
    writes = [c for c in connector.call_tool.call_args_list if c.args[0] == "SLACK_SEND_MESSAGE"]
    assert len(writes) == 1 and writes[0].args[1] == {"channel": "C123", "markdown_text": "Interviews are scheduled."}


@pytest.mark.asyncio
async def test_connected_resource_lookup_can_reach_second_page(service, connector):
    connector.call_tool.side_effect = [
        {"channels": [{"id": "C000", "name": "general"}], "next_cursor": "page-two"},
        {"channels": [{"id": "C123", "name": "hiring"}], "next_cursor": ""},
    ]
    proposal = await call(service, "post_recruiting_update_to_slack", {"job_id": "job-a", "channel_id": "C123", "message": "Interviews are scheduled."})
    assert proposal["pending_action"]["details"]["channel"]["id"] == "C123"
    assert connector.call_tool.call_args_list[1].args == ("SLACK_LIST_CONVERSATIONS", {"cursor": "page-two"})


@pytest.mark.asyncio
async def test_global_external_connection_cannot_be_used_by_other_recruiter(service, monkeypatch):
    monkeypatch.setattr(tools.settings, "MORGAN_COMPOSIO_OWNER_USER_ID", "recruiter-b")
    with pytest.raises(ForbiddenError):
        await call(service, "get_connected_services", {})


@pytest.mark.asyncio
async def test_same_tenant_candidate_search_stays_private(db, service):
    db.rows["users"][0]["tenant_id"] = "shared"
    for job in db.rows["jobs"]:
        job["tenant_id"] = "shared"
    result = await call(service, "search_candidates", {})
    assert [item["application"]["id"] for item in result["data"]["matches"]] == ["application-a"]


@pytest.mark.asyncio
async def test_other_recruiters_jobs_do_not_fill_private_job_limit(db, service):
    db.rows["users"][0]["tenant_id"] = "shared"
    owned = {**db.rows["jobs"][0], "tenant_id": "shared"}
    db.rows["jobs"] = [{"id": f"foreign-{index}", "created_by": "recruiter-b", "tenant_id": "shared"} for index in range(110)] + [owned]
    result = await call(service, "search_candidates", {})
    assert [item["application"]["id"] for item in result["data"]["matches"]] == ["application-a"]
    assert result["data"]["limited"] is False
