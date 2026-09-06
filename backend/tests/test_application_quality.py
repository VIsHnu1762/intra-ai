"""Regression coverage for recruiter overrides and application scoring fallbacks."""

from unittest.mock import AsyncMock

import pytest

from app.models.enums import ApplicationStatus
from app.services.application_service import ApplicationService
from app.services.eligibility_service import EligibilityService


@pytest.mark.asyncio
async def test_recruiter_can_reconsider_an_automatically_rejected_application() -> None:
    repo = type("Repo", (), {})()
    repo.get_by_id = AsyncMock(
        return_value={"id": "app-1", "status": ApplicationStatus.REJECTED.value}
    )
    repo.update_status = AsyncMock(
        return_value={
            "id": "app-1",
            "job_id": "job-1",
            "candidate_id": "candidate-1",
            "status": ApplicationStatus.SHORTLISTED.value,
            "eligibility_score": 43.0,
            "created_at": "2026-09-05T00:00:00+00:00",
        }
    )

    result = await ApplicationService(repo, None, None).shortlist("app-1")

    assert result.status == ApplicationStatus.SHORTLISTED
    assert result.eligibility_score == 43.0
    repo.update_status.assert_awaited_once_with("app-1", ApplicationStatus.SHORTLISTED.value)


def test_experience_score_uses_explicit_application_years_when_parser_has_no_entries() -> None:
    assert EligibilityService._calculate_experience_match([], 3, 7, candidate_years=6) == 100.0
    assert EligibilityService._calculate_experience_match([], 3, 7, candidate_years=1) == 33.33
