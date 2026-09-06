"""Durable completion is shared by spoken COMPLETE and the stop endpoint."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.sessions.completion import persist_completed_interview

INTERVIEW_ID = "bf5fb89b-7404-42d5-882d-b549e6531e03"


@pytest.fixture
def persistence(monkeypatch):
    interviews = SimpleNamespace(
        get_by_id=AsyncMock(return_value={"id": INTERVIEW_ID, "status": "in_progress", "application_id": "app-1"}),
        update=AsyncMock(), get_report=AsyncMock(return_value=None),
    )
    applications = SimpleNamespace(update_status=AsyncMock())
    reports = SimpleNamespace(request_report=AsyncMock(return_value=SimpleNamespace(status="ready", report_id="report-1")))
    monkeypatch.setattr("app.repositories.interview_repo.InterviewRepo", MagicMock(return_value=interviews))
    monkeypatch.setattr("app.repositories.application_repo.ApplicationRepo", MagicMock(return_value=applications))
    monkeypatch.setattr("app.repositories.job_repo.JobRepo", MagicMock())
    monkeypatch.setattr("app.services.report_service.ReportService", MagicMock(return_value=reports))
    return interviews, applications, reports


@pytest.mark.asyncio
async def test_voice_completion_updates_interview_application_and_report(persistence):
    interviews, applications, reports = persistence
    result = await persist_completed_interview(INTERVIEW_ID, supabase=object())
    assert result == {"persistence_status": "completed", "report_status": "ready", "report_id": "report-1"}
    patch = interviews.update.call_args.args[1]
    assert patch["status"] == "completed" and patch["ended_at"]
    applications.update_status.assert_awaited_once_with("app-1", "completed")
    reports.request_report.assert_awaited_once_with(INTERVIEW_ID)


@pytest.mark.asyncio
async def test_report_failure_does_not_undo_completed_interview(persistence):
    interviews, _, reports = persistence
    reports.request_report.side_effect = ValueError("No interview evidence")
    result = await persist_completed_interview(INTERVIEW_ID, supabase=object())
    assert result["persistence_status"] == "completed"
    assert result["report_status"] == "failed"
    interviews.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_report_is_reused_without_duplicate_generation(persistence):
    interviews, _, reports = persistence
    interviews.get_by_id.return_value["status"] = "completed"
    interviews.get_report.return_value = {"id": "existing-report"}
    reports.request_report.return_value = SimpleNamespace(status="ready", report_id="existing-report")
    result = await persist_completed_interview(INTERVIEW_ID, supabase=object())
    assert result["report_id"] == "existing-report"
    interviews.update.assert_not_awaited()
    reports.request_report.assert_awaited_once_with(INTERVIEW_ID)


@pytest.mark.asyncio
async def test_synthetic_and_absent_interviews_do_not_fabricate_reports(persistence):
    interviews, applications, reports = persistence
    assert (await persist_completed_interview("voice-isolated", supabase=object()))["report_status"] == "not_applicable"
    interviews.get_by_id.assert_not_awaited()
    interviews.get_by_id.return_value = None
    assert (await persist_completed_interview(INTERVIEW_ID, supabase=object()))["report_status"] == "not_applicable"
    applications.update_status.assert_not_awaited()
    reports.request_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_returns_generation_state_without_waiting_for_models(persistence):
    _, _, reports = persistence
    reports.request_report.return_value = SimpleNamespace(status="generating", report_id=None)
    result = await persist_completed_interview(INTERVIEW_ID, supabase=object())
    assert result == {"persistence_status": "completed", "report_status": "generating"}
