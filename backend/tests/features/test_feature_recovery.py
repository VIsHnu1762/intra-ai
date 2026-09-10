import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.feature_runtime.worker import FeatureRecoveryWorker
from app.feature_runtime.projection_queue import DueProjectionEvents


@pytest.mark.asyncio
async def test_disabled_domains_do_not_run_reasoning_or_touch_graph(feature_sb):
    worker = FeatureRecoveryWorker(feature_sb, gd_enabled=False, roleplay_enabled=False)
    result = await worker.run_once()
    assert result["gd_events_processed"] == 0
    assert result["projection_sessions_processed"] == 0
    assert result["failures"] == 0


@pytest.mark.asyncio
async def test_projection_queue_does_not_retry_future_events_when_another_event_is_due():
    now = datetime.now(timezone.utc)
    class Repository:
        sb = object()
        async def events(self, key):
            return [{"id": "due", "projection_next_attempt_at": (now - timedelta(seconds=1)).isoformat()},
                    {"id": "future", "projection_next_attempt_at": (now + timedelta(hours=1)).isoformat()},
                    {"id": "invalid", "projection_next_attempt_at": "invalid"},
                    {"id": "legacy"}]
    assert [event["id"] for event in await DueProjectionEvents(Repository()).events("session")] == ["due", "legacy"]


@pytest.mark.asyncio
async def test_failed_projection_marks_worker_degraded_without_overwriting_gd_backoff(monkeypatch):
    import app.feature_runtime.worker as module
    from app.group_discussion.evidence_delivery import GDEvidenceDelivery
    class Database:
        def __init__(self): self.heartbeat = None; self.updated_tables = []
        def table(self, name):
            outer = self
            class Query:
                payload = None
                def select(self, *_): return self
                def eq(self, *_): return self
                def limit(self, *_): return self
                def upsert(self, payload): self.payload = payload; return self
                def update(self, payload): outer.updated_tables.append(name); return self
                def in_(self, *_): return self
                def lte(self, *_): return self
                def execute(self):
                    if name == "feature_worker_health":
                        outer.heartbeat = self.payload
                        return SimpleNamespace(data=[self.payload])
                    return SimpleNamespace(data=[{"id": "session"}])
            return Query()
    async def queue(sb, name, **kwargs):
        return ["session"] if name == "pending_gd_projection_sessions" else []
    async def failed(self, session):
        return {"delivered": 0, "failed": 1, "pending": 1}
    monkeypatch.setattr(module, "rpc", queue)
    monkeypatch.setattr(GDEvidenceDelivery, "deliver", failed)
    sb = Database()
    result = await FeatureRecoveryWorker(sb, gd_enabled=True, roleplay_enabled=False, projection=object()).run_once()
    assert result["failures"] == 1
    assert result["projection_events_delivered"] == 0
    assert sb.heartbeat["status"] == "degraded"
    assert "gd_events" not in sb.updated_tables


@pytest.mark.asyncio
async def test_real_migrated_schema_and_worker_pass_readiness(feature_sb):
    from app.feature_runtime.readiness import ReadinessProbe
    worker = FeatureRecoveryWorker(feature_sb, gd_enabled=False, roleplay_enabled=False)
    await worker.run_once()
    result = await ReadinessProbe().check(feature_sb)
    assert result["status"] == "ready", result
    row = feature_sb.table("feature_worker_health").select("*").eq("worker_id", worker.worker_id).single().execute().data
    assert row["status"] == "ok"


@pytest.mark.asyncio
async def test_empty_gd_queue_uses_no_provider_or_graph(feature_sb):
    class NeverCalled:
        async def generate_feature_json(self, *args, **kwargs):
            raise AssertionError("Empty queues cannot call an LLM")
        def project(self, *args, **kwargs):
            raise AssertionError("Empty queues cannot call Neo4j")
    worker = FeatureRecoveryWorker(feature_sb, gd_enabled=True, roleplay_enabled=False,
                                   client=NeverCalled(), projection=NeverCalled())
    # Other feature tests may have delivered records; no pending GD evidence remains.
    result = await worker.run_once()
    assert result["failures"] == 0
