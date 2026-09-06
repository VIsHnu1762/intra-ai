"""Persistent template scope, optimistic edits, and scheduling snapshot regressions."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError as SchemaError

from app.core.deps import get_current_user, get_supabase
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError, register_exception_handlers
from app.repositories.application_repo import ApplicationRepo
from app.repositories.interview_repo import InterviewRepo
from app.repositories.interview_template_repo import InterviewTemplatesUnavailable
from app.routes.interview_templates import router
from app.schemas.interview_templates import InterviewTemplateCreate, InterviewTemplateUpdate
from app.services.interview_template_service import InterviewTemplateService
from app.services.scheduling_service import SchedulingService, _copy_template_snapshot, _slot_start
from app.voice.authorization import Actor


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters = db, table, []
        self.op, self.payload, self.low, self.high = "read", None, 0, 10000

    def select(self, *_args, **_kwargs): return self
    def order(self, *_args, **_kwargs): return self
    def eq(self, key, value):
        self.filters.append((key, value))
        return self
    def is_(self, key, _null): return self.eq(key, None)
    def in_(self, key, values): return self.eq(key, set(values))
    def limit(self, count):
        self.high = count
        return self
    def range(self, low, high):
        self.low, self.high = low, high + 1
        return self
    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self
    def update(self, payload):
        self.op, self.payload = "update", payload
        return self
    def delete(self):
        self.op = "delete"
        return self
    def execute(self):
        rows = self.db.rows.setdefault(self.table, [])
        selected = [row for row in rows if all(row.get(key) in val if isinstance(val, set) else row.get(key) == val for key, val in self.filters)]
        if self.op == "insert":
            selected = deepcopy(self.payload if isinstance(self.payload, list) else [self.payload])
            rows.extend(selected)
        elif self.op == "update":
            for row in selected: row.update(deepcopy(self.payload))
        elif self.op == "delete":
            for row in selected: rows.remove(row)
        if self.op != "read": self.db.writes.append((self.table, self.op, deepcopy(self.payload)))
        result = deepcopy(selected[self.low:self.high])
        if self.table == "jobs":
            for row in result:
                row["job_rounds"] = deepcopy([item for item in self.db.rows.get("job_rounds", []) if item["job_id"] == row["id"]])
        return SimpleNamespace(data=result, count=len(selected))


class DB:
    def __init__(self):
        self.rows = {"interview_templates": [], "scheduled_interviews": [], "job_rounds": []}
        self.writes = []
    def table(self, table): return Query(self, table)


@pytest.fixture
def db():
    return DB()


@pytest.fixture
def actor():
    return Actor("hr-a", "recruiter", "a@example.test", "Ada")


def payload(**changes):
    return {
        "name": "Software developer", "description": "Project discussion",
        "rounds": [
            {"type": "introduction", "duration_minutes": 5, "agent_ids": ["alex"], "focus_areas": ["Project ownership"]},
            {"type": "technical", "duration_minutes": 20, "agent_ids": ["alex", "jordan"], "focus_areas": ["API design", "Trade-offs"]},
        ], **changes,
    }


async def create(db, actor):
    return await InterviewTemplateService(db).create(actor, InterviewTemplateCreate(**payload()))


@pytest.mark.asyncio
async def test_create_persists_and_second_service_reads_same_template(db, actor):
    result = await create(db, actor)
    assert result.duration_minutes == 25 and result.version == 1
    assert result.rounds[1].agent_ids == ["alex", "jordan"]
    assert (await InterviewTemplateService(db).get(actor, result.id)) == result
    assert db.rows["interview_templates"][0]["created_by"] == actor.user_id
    assert "created_by" not in result.model_dump()


@pytest.mark.asyncio
async def test_private_workspace_isolation_including_admin(db, actor):
    result = await create(db, actor)
    service = InterviewTemplateService(db)
    for outsider in [Actor("hr-b", "recruiter", "", ""), Actor("admin", "admin", "", ""), Actor(actor.user_id, "admin", "", "", "tenant-a")]:
        assert await service.list(outsider, include_archived=True) == []
        with pytest.raises(NotFoundError): await service.get(outsider, result.id)
        with pytest.raises(NotFoundError): await service.update(outsider, result.id, InterviewTemplateUpdate(name="Stolen"))
        with pytest.raises(NotFoundError): await service.archive(outsider, result.id)


@pytest.mark.asyncio
async def test_tenant_templates_shared_only_with_persisted_same_tenant(db):
    owner = Actor("hr-a", "recruiter", "", "", "tenant-a")
    teammate = Actor("hr-b", "recruiter", "", "", "tenant-a")
    foreign = Actor("hr-a", "admin", "", "", "tenant-b")
    result = await create(db, owner)
    assert (await InterviewTemplateService(db).get(teammate, result.id)).id == result.id
    with pytest.raises(NotFoundError): await InterviewTemplateService(db).require_snapshot(foreign, result.id)


@pytest.mark.asyncio
async def test_candidate_cannot_access_template_service(db, actor):
    result = await create(db, actor)
    candidate = Actor("candidate", "candidate", "", "")
    with pytest.raises(ForbiddenError): await InterviewTemplateService(db).list(candidate)
    with pytest.raises(ForbiddenError): await InterviewTemplateService(db).create(candidate, InterviewTemplateCreate(**payload()))
    with pytest.raises(ForbiddenError): await InterviewTemplateService(db).require_snapshot(candidate, result.id)


@pytest.mark.asyncio
async def test_edit_versions_archive_and_independent_snapshot(db, actor):
    result = await create(db, actor)
    service = InterviewTemplateService(db)
    snapshot = await service.require_snapshot(actor, result.id)
    updated = await service.update(actor, result.id, InterviewTemplateUpdate(name="New name", expected_version=1))
    assert updated.version == 2 and updated.name == "New name"
    with pytest.raises(ConflictError): await service.update(actor, result.id, InterviewTemplateUpdate(name="Lost edit", expected_version=1))
    snapshot["rounds"][0]["focus_areas"].append("Mutation")
    assert (await service.get(actor, result.id)).rounds[0].focus_areas == ["Project ownership"]
    archived = await service.archive(actor, result.id)
    assert archived.version == 3 and archived.archived_at
    assert await service.archive(actor, result.id) == archived
    assert await service.list(actor) == []
    assert len(await service.list(actor, include_archived=True)) == 1
    with pytest.raises(ConflictError): await service.require_snapshot(actor, result.id)
    with pytest.raises(ConflictError): await service.update(actor, result.id, InterviewTemplateUpdate(name="Revived"))


@pytest.mark.asyncio
async def test_compare_and_swap_rejects_concurrent_edit(db, actor, monkeypatch):
    result = await create(db, actor)
    service = InterviewTemplateService(db)
    original = service._repo.update
    async def raced(*args):
        db.rows["interview_templates"][0]["version"] += 1
        return await original(*args)
    monkeypatch.setattr(service._repo, "update", raced)
    with pytest.raises(ConflictError): await service.update(actor, result.id, InterviewTemplateUpdate(name="Lost"))
    assert db.rows["interview_templates"][0]["name"] == result.name


@pytest.mark.asyncio
async def test_registered_third_agent_supported_but_unknown_not_silently_replaced(db, actor, monkeypatch):
    from app.services import interview_template_service as module
    monkeypatch.setattr(module.agent_registry, "has_agent", lambda value: value in {"alex", "jordan", "casey"})
    data = payload()
    data["rounds"][1]["agent_ids"] = ["alex", "jordan", "casey"]
    result = await InterviewTemplateService(db).create(actor, InterviewTemplateCreate(**data))
    assert result.rounds[1].agent_ids == ["alex", "jordan", "casey"]
    data["rounds"][1]["agent_ids"] = ["taylor"]
    with pytest.raises(ValidationError): await InterviewTemplateService(db).create(actor, InterviewTemplateCreate(**data))


@pytest.mark.parametrize("change", [
    {"name": "   "}, {"rounds": []}, {"created_by": "other"}, {"tenant_id": "other"},
    {"rounds": [{"type": "technical", "duration_minutes": 60, "agent_ids": ["alex"], "focus_areas": ["API"]}] * 2},
    {"rounds": [{"type": "technical", "duration_minutes": 0}]},
    {"rounds": [{"type": "technical", "duration_minutes": 10, "enabled": False}]},
    {"rounds": [{"type": "technical", "duration_minutes": 10, "agent_ids": ["alex"], "focus_areas": [" "]}]},
    {"rounds": [{"type": "technical", "duration_minutes": 10, "agent_ids": [], "focus_areas": ["API"]}]},
    {"rounds": [{"type": "technical", "duration_minutes": 10, "agent_ids": ["alex"], "focus_areas": ["__intra_agent_ids__:foreign"]}]},
])
def test_invalid_template_not_accepted(change):
    with pytest.raises(SchemaError): InterviewTemplateCreate(**payload(**change))


@pytest.mark.parametrize("value", [{}, {"name": None}, {"description": None}, {"rounds": None}, {"expected_version": 2}, {"version": 4}])
def test_invalid_patch_not_accepted(value):
    with pytest.raises(SchemaError): InterviewTemplateUpdate(**value)


@pytest.mark.asyncio
async def test_database_failure_is_explicit_safe_503_not_in_memory_success(actor):
    query = SimpleNamespace(insert=lambda _data: query, execute=lambda: (_ for _ in ()).throw(RuntimeError("secret database detail")))
    db = SimpleNamespace(table=lambda _table: query)
    with pytest.raises(InterviewTemplatesUnavailable) as error:
        await create(db, actor)
    assert error.value.status_code == 503 and "secret" not in str(error.value)


def seed_job(db, actor):
    db.rows["jobs"] = [{
        "id": "job-a", "created_by": actor.user_id, "title": "Developer", "department": "Engineering",
        "description": "Original JD", "location": "Remote", "job_type": "remote", "required_skills": ["Python"],
        "experience_min": 0, "experience_max": 2, "status": "published", "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z", "eligibility_threshold": 65,
    }]
    db.rows["applications"] = [{"id": "app-a", "job_id": "job-a", "candidate_id": "candidate-a", "status": "shortlisted"}]
    db.rows["candidates"] = [{"id": "candidate-a", "name": "Sam", "email": "sam@example.test"}]
    db.rows["interview_slots"] = [{"id": "slot-a", "job_id": "job-a", "date": "2099-01-01", "start_time": "10:00:00", "end_time": "11:00:00", "is_booked": False}]


@pytest.mark.asyncio
async def test_apply_only_changes_job_rounds_and_authorizes_both_resources(db, actor):
    seed_job(db, actor)
    template = await create(db, actor)
    original = deepcopy(db.rows["jobs"][0])
    service = InterviewTemplateService(db)
    result = await service.apply_to_job(actor, template.id, "job-a")
    assert result.interview_rounds[1].agent_ids == ["alex", "jordan"]
    current = db.rows["jobs"][0]
    assert {k: v for k, v in current.items() if k != "updated_at"} == {k: v for k, v in original.items() if k != "updated_at"}
    db.rows["jobs"][0]["created_by"] = "other-recruiter"
    before = len(db.writes)
    with pytest.raises(ForbiddenError): await service.apply_to_job(actor, template.id, "job-a")
    assert len(db.writes) == before


@pytest.fixture
def scheduler(db, actor, monkeypatch):
    seed_job(db, actor)
    monkeypatch.setattr(SchedulingService, "_ensure_live_session", lambda *_a, **_kw: None)
    monkeypatch.setattr(SchedulingService, "_update_live_session_start", lambda *_a, **_kw: None)
    return SchedulingService(InterviewRepo(db), ApplicationRepo(db))


@pytest.mark.asyncio
async def test_booking_copies_snapshot_and_duration_unchanged_by_edit_archive_reschedule(db, actor, scheduler):
    template = await create(db, actor)
    service = InterviewTemplateService(db)
    snapshot = await service.require_snapshot(actor, template.id)
    booked = await scheduler.book_slot("app-a", "slot-a", template_snapshot=snapshot)
    snapshot["rounds"][0]["focus_areas"] = ["Caller mutation"]
    await service.update(actor, template.id, InterviewTemplateUpdate(rounds=[{"type": "technical", "duration_minutes": 10, "agent_ids": ["jordan"], "focus_areas": ["New focus"]}]))
    await service.archive(actor, template.id)
    saved = deepcopy(db.rows["scheduled_interviews"][0])
    assert booked.duration_minutes == 25 and saved["template_snapshot"]["template_version"] == 1
    assert saved["template_snapshot"]["rounds"][0]["focus_areas"] == ["Project ownership"]
    db.rows["interview_slots"].append({**db.rows["interview_slots"][0], "id": "slot-b", "date": "2099-01-02", "is_booked": False})
    moved = await scheduler.reschedule("app-a", "slot-b")
    assert moved.duration_minutes == 25
    assert db.rows["scheduled_interviews"][0]["template_snapshot"] == saved["template_snapshot"]


@pytest.mark.asyncio
async def test_snapshot_runtime_uses_saved_rounds_instead_of_edited_job(db, actor, monkeypatch):
    template = await create(db, actor)
    snapshot = await InterviewTemplateService(db).require_snapshot(actor, template.id)
    from app.sessions.service import interview_session_service
    captured = []
    monkeypatch.setattr(interview_session_service, "create_session", captured.append)
    application = {"id": "app-a", "candidate_id": "candidate-a", "jobs": {"id": "job-a", "title": "Developer", "description": "Real JD", "required_competencies": ["Edited focus"], "job_rounds": [{"type": "technical", "duration_minutes": 60, "agent_ids": ["alex"], "focus_areas": ["New focus"]}]}, "candidates": {"name": "Sam"}}
    interview = {"id": "interview-a", "application_id": "app-a", "scheduled_at": "2099-01-01T10:00:00Z", "template_snapshot": snapshot, "duration_minutes": 25}
    # The same materializer is called at booking and on backend-restart restore.
    SchedulingService._ensure_live_session(application, interview)
    config = captured[0]
    assert config.agent_ids == ["alex", "jordan"] and config.duration_minutes == 25
    assert config.metadata["required_competencies"] == ["Project ownership", "API design", "Trade-offs"]
    assert config.metadata["job_description"] == "Real JD" and config.metadata["candidate_name"] == "Sam"
    config.metadata["round_configs"][0]["focus_areas"].append("Runtime mutation")
    assert snapshot["rounds"][0]["focus_areas"] == ["Project ownership"]


@pytest.mark.asyncio
async def test_instant_snapshot_is_durable_and_cannot_be_replaced_on_retry(db, actor, scheduler):
    template = await create(db, actor)
    snapshot = await InterviewTemplateService(db).require_snapshot(actor, template.id)
    pending = await scheduler.start_instant("app-a", template_snapshot=snapshot)
    assert pending.duration_minutes == 25
    retried = await scheduler.start_instant("app-a", template_snapshot=snapshot)
    assert pending.id == retried.id
    changed = {**snapshot, "name": "Different"}
    with pytest.raises(ConflictError): await scheduler.start_instant("app-a", template_snapshot=changed)
    accepted = await scheduler.respond_to_instant("app-a")
    assert accepted.duration_minutes == 25 and accepted.status == "instant_active"


@pytest.mark.asyncio
async def test_invalid_or_too_long_snapshot_rejected_before_slot_claim(db, actor, scheduler):
    template = await create(db, actor)
    snapshot = await InterviewTemplateService(db).require_snapshot(actor, template.id)
    with pytest.raises(ValidationError): await scheduler.book_slot("app-a", "slot-a", template_snapshot={**snapshot, "duration_minutes": 5})
    db.rows["interview_slots"][0]["end_time"] = "10:15:00"
    with pytest.raises(ValidationError): await scheduler.book_slot("app-a", "slot-a", template_snapshot=snapshot)
    assert not db.rows["interview_slots"][0]["is_booked"] and not db.rows["scheduled_interviews"]


@pytest.mark.asyncio
async def test_failed_insert_releases_claimed_slot_and_does_not_mark_scheduled(db, scheduler, monkeypatch):
    monkeypatch.setattr(scheduler._repo, "create", AsyncMock(side_effect=RuntimeError("missing column")))
    with pytest.raises(RuntimeError): await scheduler.book_slot("app-a", "slot-a")
    assert not db.rows["interview_slots"][0]["is_booked"]
    assert db.rows["applications"][0]["status"] == "shortlisted"


@pytest.mark.asyncio
async def test_slot_claim_prevents_second_booking_and_cross_job_schedule(db, scheduler):
    db.rows["interview_slots"][0]["job_id"] = "other-job"
    with pytest.raises(ValidationError): await scheduler.book_slot("app-a", "slot-a")
    assert not db.rows["interview_slots"][0]["is_booked"]
    repo = InterviewRepo(db)
    await repo.book_slot("slot-a")
    with pytest.raises(ConflictError): await repo.book_slot("slot-a")


@pytest.mark.parametrize("time,expected", [("10:30", "10:30:00+00:00"), ("10:30:00", "10:30:00+00:00"), ("10:30:00+05:30", "05:00:00+00:00")])
def test_slot_time_formats_and_utc_conversion(time, expected):
    assert _slot_start({"date": "2099-01-01", "start_time": time}) == "2099-01-01T" + expected


@pytest.mark.asyncio
async def test_routes_derive_role_and_tenant_from_persisted_user_not_claims(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    register_exception_handlers(app)
    claims = {"sub": "u", "role": "admin", "tenant_id": "forged"}
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[get_supabase] = lambda: db
    db.rows["users"] = [{"id": "u", "role": "candidate", "email": "x@example.test"}]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/interview-templates")).status_code == 403
        db.rows["users"][0].update(role="recruiter", tenant_id="real")
        created = await client.post("/api/v1/interview-templates", json=payload())
        assert created.status_code == 201
        assert db.rows["interview_templates"][0]["tenant_id"] == "real"
        assert "tenant_id" not in created.json()
        assert len((await client.get("/api/v1/interview-templates")).json()) == 1
        db.rows["users"][0]["is_active"] = False
        assert (await client.get("/api/v1/interview-templates")).status_code == 401
