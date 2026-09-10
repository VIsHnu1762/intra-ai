from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.deps import get_supabase
from app.feature_runtime.readiness import ReadinessProbe
from app.routes.health import router


def flags(enabled=True):
    return SimpleNamespace(CANDIDATE_ONBOARDING_ENABLED=enabled, COMPANY_KNOWLEDGE_ENABLED=enabled,
                           ROLE_PLAY_ENABLED=enabled, GROUP_DISCUSSION_ENABLED=enabled)


class Database:
    def __init__(self, missing=None, stale=False):
        self.missing = missing
        self.stale = stale
        self.calls = 0
    def table(self, name):
        outer = self
        class Query:
            def select(self, *_): return self
            def limit(self, *_): return self
            def order(self, *_, **__): return self
            def execute(self):
                outer.calls += 1
                if name == outer.missing:
                    raise RuntimeError("Unavailable schema")
                if name == "feature_worker_health":
                    seen = datetime.now(timezone.utc) - timedelta(seconds=600 if outer.stale else 1)
                    return SimpleNamespace(data=[{"status": "ok", "last_seen_at": seen.isoformat()}])
                return SimpleNamespace(data=[])
        return Query()


@pytest.mark.asyncio
async def test_readiness_requires_enabled_schema_and_fresh_worker():
    probe = ReadinessProbe(flags(), ttl=0)
    assert (await probe.check(Database()))["status"] == "ready"
    assert (await probe.check(Database(missing="gd_events")))["status"] == "not_ready"
    assert (await probe.check(Database(stale=True)))["status"] == "not_ready"
    assert (await ReadinessProbe(flags(False)).check(Database(stale=True)))["status"] == "ready"


@pytest.mark.asyncio
async def test_readiness_caches_bounded_checks_not_business_data():
    sb = Database()
    probe = ReadinessProbe(flags())
    first = await probe.check(sb)
    calls = sb.calls
    assert await probe.check(sb) is first
    assert sb.calls == calls
    assert "candidate" not in str(first).lower()


def test_liveness_is_independent_and_readiness_returns_503():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.readiness_probe = ReadinessProbe(flags(), ttl=0)
    app.dependency_overrides[get_supabase] = lambda: Database(missing="gd_sessions")
    client = TestClient(app)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/ready").status_code == 503
