"""Cross-recruiter ATS isolation using real JWT and persisted fake repositories."""

from copy import deepcopy

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import settings
from app.core.deps import get_supabase
from app.core.exceptions import register_exception_handlers
from app.core.security import create_access_token
from app.routes import applications, candidates, evaluation, interviews, jobs, reports, scheduling
from tests.test_interview_templates import DB, Query


class JoinedQuery(Query):
    def execute(self):
        result = super().execute()
        if self.table == "candidates":
            for row in result.data:
                row["parsed_resumes"] = deepcopy([item for item in self.db.rows["parsed_resumes"] if item["candidate_id"] == row["id"]])
        if self.table in {"applications", "scheduled_interviews"}:
            for row in result.data:
                row["jobs"] = deepcopy(next((item for item in self.db.rows["jobs"] if item["id"] == row["job_id"]), {}))
                row["candidates"] = deepcopy(next((item for item in self.db.rows["candidates"] if item["id"] == row["candidate_id"]), {}))
        return result


class WorkspaceDB(DB):
    def table(self, table): return JoinedQuery(self, table)


@pytest.fixture
def workspace(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET", "workspace-tests-only-not-a-live-secret")
    db = WorkspaceDB()
    stamp = "2026-01-01T00:00:00Z"
    db.rows["users"] = [
        {"id": "hr-a", "role": "recruiter", "name": "A", "email": "hr-a@example.test"},
        {"id": "hr-b", "role": "recruiter", "name": "B", "email": "hr-b@example.test"},
        {"id": "admin", "role": "admin", "name": "Admin", "email": "admin@example.test"},
        {"id": "user-a", "role": "candidate", "name": "Sam", "email": "sam@example.test"},
        {"id": "user-b", "role": "candidate", "name": "Bea", "email": "bea@example.test"},
    ]
    basejob = {"department": "Engineering", "description": "JD", "location": "Remote", "job_type": "remote", "required_skills": ["Python"], "experience_min": 0, "experience_max": 2, "status": "published", "created_at": stamp, "updated_at": stamp}
    db.rows["jobs"] = [{**basejob, "id": "job-b", "title": "B private draft", "created_by": "hr-b", "status": "draft"}, {**basejob, "id": "job-a", "title": "A developer", "created_by": "hr-a"}, {**basejob, "id": "job-a2", "title": "A engineer", "created_by": "hr-a"}]
    db.rows["candidates"] = [{"id": "candidate-b", "name": "Bea", "email": "bea@example.test", "created_at": stamp}, {"id": "candidate-a", "name": "Sam", "email": "sam@example.test", "resume_url": "foreign-company-cv.pdf", "created_at": stamp}]
    db.rows["applications"] = [
        {"id": "app-b", "job_id": "job-b", "candidate_id": "candidate-b", "status": "shortlisted", "created_at": stamp},
        {"id": "app-shared-b", "job_id": "job-b", "candidate_id": "candidate-a", "status": "rejected", "resume_url": "foreign-company-cv.pdf", "created_at": stamp},
        {"id": "app-a", "job_id": "job-a", "candidate_id": "candidate-a", "status": "shortlisted", "resume_url": "/api/v1/applications/app-a/resume/pdf", "created_at": stamp},
    ]
    db.rows["parsed_resumes"] = [
        {"id": "resume-b", "application_id": "app-shared-b", "candidate_id": "candidate-a", "skills": ["Other-company-private"], "created_at": "2026-02-01T00:00:00Z"},
        {"id": "resume-a", "application_id": "app-a", "candidate_id": "candidate-a", "skills": ["Python"], "created_at": stamp},
    ]
    db.rows["scheduled_interviews"] = [
        {"id": "interview-b", "application_id": "app-b", "job_id": "job-b", "candidate_id": "candidate-b", "status": "scheduled", "scheduled_at": "2099-01-01T10:00:00Z", "created_at": stamp},
        {"id": "interview-a", "application_id": "app-a", "job_id": "job-a", "candidate_id": "candidate-a", "status": "scheduled", "scheduled_at": "2099-01-01T10:00:00Z", "duration_minutes": 25, "created_at": stamp},
        {"id": "interview-a2", "application_id": "app-a", "job_id": "job-a", "candidate_id": "candidate-a", "status": "completed", "scheduled_at": "2099-01-01T10:00:00Z", "created_at": stamp},
    ]
    db.rows["reports"] = [{"id": f"report-{suffix}", "interview_id": f"interview-{suffix}", "overall_score": 75, "recommendation": "hire", "created_at": stamp} for suffix in ("b", "a", "a2")]
    db.rows["interview_questions"] = [{"id": "question-a", "interview_id": "interview-a", "text": "Question"}, {"id": "question-b", "interview_id": "interview-b", "text": "Other question"}]
    app = FastAPI()
    for module in (candidates, jobs, applications, scheduling, interviews, reports, evaluation):
        app.include_router(module.router, prefix="/api/v1")
    app.include_router(reports.reports_router, prefix="/api/v1")
    app.dependency_overrides[get_supabase] = lambda: db
    register_exception_handlers(app)
    return app, db


def headers(user="hr-a", role="recruiter", **extra):
    return {"Authorization": "Bearer " + create_access_token({"sub": user, "role": role, **extra})}


@pytest.mark.asyncio
@pytest.mark.parametrize("path,key,expected,total", [
    ("jobs", "jobs", "job-a", 2), ("candidates", "candidates", "candidate-a", 1),
    ("interviews", "interviews", "interview-a", 2), ("reports", "reports", "report-a", 2),
])
async def test_lists_filter_before_pagination_and_totals(workspace, path, key, expected, total):
    app, _db = workspace
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/{path}?per_page=1", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["total"] == total
    assert [row["id"] for row in response.json()[key]] == [expected]
    assert "foreign-company-cv" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", [
    ("GET", "jobs/job-b", None), ("PATCH", "jobs/job-b", {"description": "Tampered"}),
    ("POST", "jobs/job-b/publish", None), ("POST", "jobs/job-b/archive", None),
    ("GET", "jobs/job-b/applications", None), ("GET", "jobs/job-b/slots", None), ("POST", "jobs/job-b/slots", []),
    ("GET", "candidates/candidate-b", None), ("GET", "candidates/candidate-b/applications", None),
    ("GET", "applications/app-b", None), ("GET", "applications/app-b/parsed-resume", None),
    ("GET", "applications/app-b/resume/pdf", None), ("POST", "applications/app-b/shortlist", None),
    ("POST", "applications/app-b/reject", None), ("POST", "applications/app-b/invite", None),
    ("POST", "applications/app-b/schedule", {"slot_id": "slot"}), ("POST", "applications/app-b/reschedule", {"slot_id": "slot"}),
    ("POST", "applications/app-b/instant", None), ("GET", "interviews/interview-b", None),
    ("POST", "interviews/interview-b/start", None), ("POST", "interviews/interview-b/end", None),
    ("GET", "interviews/interview-b/questions", None), ("POST", "interviews/interview-b/questions/generate", {"round_type": "technical"}),
    ("POST", "interviews/interview-b/answers", {"question_id": "question-b", "transcript": "Tampered", "duration_seconds": 5}),
    ("POST", "interviews/interview-b/evaluate", None), ("GET", "interviews/interview-b/evaluation", None),
    ("GET", "reports/report-b", None), ("POST", "interviews/interview-b/report/generate", None),
    ("GET", "interviews/interview-b/report", None), ("GET", "interviews/interview-b/report/pdf", None),
])
async def test_other_recruiter_direct_reads_and_writes_are_forbidden(workspace, method, path, body):
    app, db = workspace
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, "/api/v1/" + path, json=body, headers=headers())
    assert response.status_code == 403, response.text
    assert db.writes == []


@pytest.mark.asyncio
async def test_shared_candidate_dossier_and_applications_omit_other_company_resume(workspace):
    app, _db = workspace
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        dossier = await client.get("/api/v1/candidates/candidate-a", headers=headers())
        applications = await client.get("/api/v1/candidates/candidate-a/applications", headers=headers())
    assert dossier.status_code == applications.status_code == 200
    assert dossier.json()["parsed_resume"]["skills"] == ["Python"]
    assert dossier.json()["resume_url"] == "/api/v1/applications/app-a/resume/pdf"
    assert [item["id"] for item in applications.json()["applications"]] == ["app-a"]
    assert "Other-company-private" not in dossier.text and "foreign-company-cv" not in applications.text


@pytest.mark.asyncio
async def test_same_tenant_and_admin_do_not_override_private_job_owner(workspace):
    app, db = workspace
    for user in db.rows["users"]: user["tenant_id"] = "tenant-a"
    for job in db.rows["jobs"]: job["tenant_id"] = "tenant-a"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for actor, role in [("hr-a", "recruiter"), ("admin", "admin")]:
            assert (await client.get("/api/v1/jobs/job-b", headers=headers(actor, role))).status_code == 403
        listing = await client.get("/api/v1/jobs", headers=headers("admin", "admin"))
    assert listing.json()["total"] == 0


@pytest.mark.asyncio
async def test_persisted_role_and_active_state_override_valid_stale_jwt(workspace):
    app, db = workspace
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/candidates", headers=headers("user-a", "admin"))).status_code == 403
        db.rows["users"][0]["is_active"] = False
        assert (await client.get("/api/v1/jobs/job-a", headers=headers())).status_code == 401
        assert (await client.get("/api/v1/jobs")).status_code == 401
        assert (await client.get("/api/v1/jobs", headers={"Authorization": "Bearer invalid"})).status_code == 401


@pytest.mark.asyncio
async def test_public_jobs_and_candidate_own_performance_work_but_detailed_reports_are_recruiter_only(workspace):
    app, _db = workspace
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/jobs/public/job-a")).status_code == 200
        assert (await client.get("/api/v1/jobs/public/job-b")).status_code == 404
        own = await client.get("/api/v1/reports/report-a", headers=headers("user-a", "candidate"))
        other = await client.get("/api/v1/reports/report-a", headers=headers("user-b", "candidate"))
        own_performance = await client.get("/api/v1/interviews/interview-a/performance", headers=headers("user-a", "candidate"))
        other_performance = await client.get("/api/v1/interviews/interview-a/performance", headers=headers("user-b", "candidate"))
        mine = await client.get("/api/v1/candidates/me/applications", headers=headers("user-a", "candidate", email="bea@example.test"))
    assert own.status_code == other.status_code == other_performance.status_code == 403
    assert own_performance.status_code == 200
    assert own_performance.json()["status"] == "not_completed" and own_performance.json()["rating"] is None
    assert "recommendation" not in own_performance.json()
    assert {row["id"] for row in mine.json()["applications"]} == {"app-a", "app-shared-b"}


@pytest.mark.asyncio
async def test_candidate_answer_cannot_reference_another_interviews_question(workspace):
    app, db = workspace
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = {"question_id": "question-b", "transcript": "My answer", "duration_seconds": 5}
        rejected = await client.post("/api/v1/interviews/interview-a/answers", json=body, headers=headers("user-a", "candidate"))
        assert rejected.status_code == 422 and not db.writes
        body["question_id"] = "question-a"
        accepted = await client.post("/api/v1/interviews/interview-a/answers", json=body, headers=headers("user-a", "candidate"))
    assert accepted.status_code == 201
    assert db.rows["candidate_answers"][0]["interview_id"] == "interview-a"


@pytest.mark.asyncio
async def test_resume_upload_cross_recruiter_is_forbidden_before_processing(workspace):
    app, db = workspace
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/applications/app-b/resume", headers=headers(), files={"resume": ("cv.pdf", b"synthetic", "application/pdf")})
    assert response.status_code == 403 and db.writes == []


@pytest.mark.asyncio
async def test_report_job_filter_applies_before_pagination(workspace):
    app, _db = workspace
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/reports?job_id=job-a&per_page=1&page=2", headers=headers())
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["reports"][0]["id"] == "report-a2"


@pytest.mark.asyncio
async def test_candidate_tagged_to_another_tenant_is_not_counted_or_returned(workspace):
    app, db = workspace
    db.rows["candidates"][1]["tenant_id"] = "other-tenant"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/candidates", headers=headers())
        detail = await client.get("/api/v1/candidates/candidate-a", headers=headers())
    assert listing.json() == {"candidates": [], "total": 0}
    assert detail.status_code == 403


@pytest.mark.asyncio
async def test_new_job_uses_persisted_creator_and_tenant(workspace):
    app, db = workspace
    db.rows["users"][0]["tenant_id"] = "real-tenant"
    body = {
        "title": "Private opening", "department": "Engineering", "location": "Remote", "job_type": "remote",
        "description": "JD", "required_skills": ["Python"], "experience_min": 0, "experience_max": 1,
        "interview_rounds": [{"type": "technical", "duration_minutes": 15, "agent_ids": ["alex"], "focus_areas": ["API"]}],
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/jobs", json=body, headers=headers(tenant_id="forged-tenant"))
    assert response.status_code == 201, response.text
    saved = db.rows["jobs"][-1]
    assert saved["created_by"] == "hr-a" and saved["tenant_id"] == "real-tenant"
