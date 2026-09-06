"""Regression coverage for recruiter scheduling and instant interview windows."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ValidationError
from app.services.scheduling_service import SchedulingService


class FakeApplicationRepo:
    def __init__(self, row):
        self.row = row
        self.status_updates = []

    async def get_by_id(self, _application_id):
        return self.row

    async def update_status(self, _application_id, status, extra=None):
        self.row["status"] = status
        self.status_updates.append(status)
        return self.row


class FakeInterviewRepo:
    def __init__(self, interview, slot=None):
        self.interview = interview
        self.slot = slot
        self.booked = []
        self.released = []
        self.updated = []

    async def get_latest_by_application_id(self, _application_id):
        return self.interview

    async def get_slot_by_id(self, _slot_id):
        return self.slot

    async def book_slot(self, slot_id):
        self.booked.append(slot_id)
        return self.slot

    async def release_slot(self, slot_id):
        self.released.append(slot_id)
        return self.slot

    async def update(self, _interview_id, data):
        self.updated.append(data)
        self.interview.update(data)
        return self.interview


@pytest.mark.asyncio
async def test_reschedule_moves_booking_and_releases_old_slot():
    app = {"id": "app-1", "status": "scheduled", "job_id": "job-1", "candidate_id": "cand-1", "jobs": {}}
    interview = {
        "id": "interview-1",
        "application_id": "app-1",
        "status": "scheduled",
        "slot_id": "old-slot",
        "scheduled_at": "2026-09-10T09:00:00Z",
        "room_token": "room-1",
    }
    new_slot = {
        "id": "new-slot",
        "job_id": "job-1",
        "date": "2026-09-11",
        "start_time": "10:00",
        "end_time": "11:00",
        "is_booked": False,
    }
    interview_repo = FakeInterviewRepo(interview, new_slot)
    result = await SchedulingService(interview_repo, FakeApplicationRepo(app)).reschedule(
        "app-1", "new-slot"
    )

    assert result.id == "interview-1"
    assert result.scheduled_at.isoformat().startswith("2026-09-11T10:00:00")
    assert interview_repo.booked == ["new-slot"]
    assert interview_repo.released == ["old-slot"]
    assert interview_repo.updated[0]["status"] == "scheduled"


@pytest.mark.asyncio
async def test_instant_response_expires_and_persists_expired_state():
    app = {"id": "app-1", "status": "invited", "job_id": "job-1", "candidate_id": "cand-1"}
    interview = {
        "id": "interview-1",
        "application_id": "app-1",
        "status": "instant_pending",
        "scheduled_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        "room_token": "room-1",
    }
    interview_repo = FakeInterviewRepo(interview)

    with pytest.raises(ValidationError, match="expired"):
        await SchedulingService(interview_repo, FakeApplicationRepo(app)).respond_to_instant("app-1")

    assert interview_repo.updated == [{"status": "instant_expired"}]
