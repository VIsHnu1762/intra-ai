"""Unit tests for InterviewSession model + service (3 configurations)."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from app.sessions.models import (
    InterviewConfiguration,
    InterviewSession,
    SessionStatus,
    _make_channel_name,
)
from app.sessions.store import SessionStore
from app.sessions.service import InterviewSessionService


# ── Channel naming ──────────────────────────────────────────────────────────


def test_channel_name_format():
    assert _make_channel_name("abc123") == "intra-abc123"


def test_channel_name_strips_whitespace():
    assert _make_channel_name("  abc123  ") == "intra-abc123"


def test_channel_name_no_double_prefix():
    assert _make_channel_name("intra-abc123") == "intra-abc123"


def test_channel_name_lowercased():
    assert _make_channel_name("ABC123") == "intra-abc123"


# ── InterviewSession creation ───────────────────────────────────────────────


def _config(interview_id="test-001", agent_ids=None) -> InterviewConfiguration:
    return InterviewConfiguration(
        interview_id=interview_id,
        candidate_id="cand-001",
        agent_ids=agent_ids or ["alex"],
        duration_minutes=45,
    )


def test_session_from_config_alex_only():
    session = InterviewSession.from_config(_config(agent_ids=["alex"]))
    assert session.interview_id == "test-001"
    assert session.channel_name == "intra-test-001"
    assert session.agent_ids == ["alex"]
    assert session.current_agent_id == "alex"
    assert session.status == SessionStatus.CREATED


def test_session_from_config_jordan_only():
    session = InterviewSession.from_config(_config(agent_ids=["jordan"]))
    assert session.agent_ids == ["jordan"]
    assert session.current_agent_id == "jordan"


def test_session_from_config_alex_and_jordan():
    session = InterviewSession.from_config(_config(agent_ids=["alex", "jordan"]))
    assert session.agent_ids == ["alex", "jordan"]
    assert session.current_agent_id == "alex"   # first agent is current


def test_session_from_config_empty_agents_raises():
    # Empty strings strip to nothing → cleaned list is empty → ValueError
    config = _config()
    config.agent_ids = ["", "  "]
    with pytest.raises(ValueError, match="at least one"):
        InterviewSession.from_config(config)


# ── Start window validation ──────────────────────────────────────────────────


def test_startable_no_scheduled_time():
    session = InterviewSession.from_config(_config())
    can_start, reason = session.is_startable()
    assert can_start is True
    assert reason == "ok"


def test_startable_within_window():
    """Scheduled 5 min from now, window is 10 min → should be startable."""
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    config = _config()
    config.scheduled_start = future
    session = InterviewSession.from_config(config)
    can_start, _ = session.is_startable(start_window_minutes=10)
    assert can_start is True


def test_not_startable_too_early():
    """Scheduled 30 min from now, window is 10 min → NOT startable."""
    future = datetime.now(timezone.utc) + timedelta(minutes=30)
    config = _config()
    config.scheduled_start = future
    session = InterviewSession.from_config(config)
    can_start, reason = session.is_startable(start_window_minutes=10)
    assert can_start is False
    assert "opens in" in reason


def test_startable_past_time():
    """Scheduled in the past → always startable."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    config = _config()
    config.scheduled_start = past
    session = InterviewSession.from_config(config)
    can_start, _ = session.is_startable()
    assert can_start is True


# ── SessionStore ─────────────────────────────────────────────────────────────


def test_store_create_and_get():
    store = SessionStore()
    config = _config("store-test-001", ["alex"])
    session = store.create(config)
    assert store.has("store-test-001")
    retrieved = store.get("store-test-001")
    assert retrieved is not None
    assert retrieved.channel_name == "intra-store-test-001"


def test_store_idempotent_create():
    store = SessionStore()
    config = _config("idem-001", ["alex"])
    s1 = store.create(config)
    s2 = store.create(config)
    assert s1 is s2


def test_store_missing_returns_none():
    store = SessionStore()
    assert store.get("nonexistent") is None


# ── InterviewSessionService — create ─────────────────────────────────────────


def test_service_create_session():
    store = SessionStore()
    svc = InterviewSessionService(store=store)
    config = _config("svc-001", ["jordan"])
    session = svc.create_session(config)
    assert session.interview_id == "svc-001"
    assert session.channel_name == "intra-svc-001"
    assert session.agent_ids == ["jordan"]


def test_service_require_session_raises_not_found():
    from app.core.exceptions import NotFoundError
    store = SessionStore()
    svc = InterviewSessionService(store=store)
    with pytest.raises(NotFoundError):
        svc.require_session("does-not-exist")


# ── InterviewSessionService — start (time window) ────────────────────────────


@pytest.mark.asyncio
async def test_service_start_too_early_raises():
    from app.core.exceptions import ValidationError
    store = SessionStore()
    svc = InterviewSessionService(store=store)
    future = datetime.now(timezone.utc) + timedelta(minutes=30)
    config = InterviewConfiguration(
        interview_id="too-early-001",
        candidate_id="cand-x",
        agent_ids=["alex"],
        scheduled_start=future,
    )
    svc.create_session(config)

    with pytest.raises(ValidationError, match="not yet open"):
        await svc.start_session("too-early-001", start_window_minutes=5)


# ── to_dict serialization ────────────────────────────────────────────────────


def test_session_to_dict_keys():
    session = InterviewSession.from_config(_config(agent_ids=["alex", "jordan"]))
    d = session.to_dict()
    assert "interview_id" in d
    assert "channel_name" in d
    assert "agent_ids" in d
    assert "current_agent_id" in d
    assert d["status"] == "CREATED"
