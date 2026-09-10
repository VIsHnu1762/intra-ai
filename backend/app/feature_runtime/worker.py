"""Restartable feature recovery worker using the existing Supabase and AuraDB.

Run with ``python -m app.feature_runtime.worker``. Domain decisions remain in
GDProcessing and the feature services; this runner only schedules durable work.
"""
import argparse
import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from supabase import create_client

from app.core.config import settings
from app.integrations.feature_db import execute, rpc
from app.feature_runtime.projection_queue import DueProjectionEvents
from app.knowledge_graph.assessment_projection import AssessmentEvidenceProjection

logger = logging.getLogger("intra.feature_worker")


class FeatureRecoveryWorker:
    def __init__(self, sb, *, gd_enabled=None, roleplay_enabled=None, client=None, projection=None):
        self.sb = sb
        self.gd_enabled = settings.GROUP_DISCUSSION_ENABLED if gd_enabled is None else gd_enabled
        self.roleplay_enabled = settings.ROLE_PLAY_ENABLED if roleplay_enabled is None else roleplay_enabled
        self.client = client
        self.projection = projection
        self.worker_id = str(uuid4())

    async def _heartbeat(self, status, detail):
        await execute(self.sb.table("feature_worker_health").upsert({
            "worker_id": self.worker_id, "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "status": status, "detail": detail,
        }))

    async def run_once(self):
        result = {"gd_events_processed": 0, "projection_sessions_processed": 0,
                  "gd_sessions_expired": 0, "roleplay_sessions_expired": 0,
                  "projection_events_delivered": 0, "projection_events_pending": 0, "failures": 0,
                  "graph_configured": bool(self.projection or all((settings.NEO4J_URI, settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)))}
        await self._heartbeat("working", result)
        if self.roleplay_enabled:
            result["roleplay_sessions_expired"] = int(await rpc(self.sb, "expire_roleplay_sessions", p_limit=32) or 0)
        if self.gd_enabled:
            result["gd_sessions_expired"] = int(await rpc(self.sb, "expire_gd_sessions", p_limit=32) or 0)
            from app.group_discussion.repository import GDRepository
            from app.group_discussion.processing import GDProcessing
            repo = GDRepository(self.sb)
            sessions = await rpc(self.sb, "pending_gd_analysis_sessions", p_limit=8)
            limiter = asyncio.Semaphore(4)

            async def process(key):
                async with limiter:
                    try:
                        return await asyncio.wait_for(GDProcessing(repo, self.client).drain(str(key), max_events=1), timeout=90)
                    except Exception as exc:
                        logger.warning("gd_recovery_deferred error_type=%s", type(exc).__name__)
                        result["failures"] += 1
                        return 0

            result["gd_events_processed"] = sum(await asyncio.gather(*(process(key) for key in sessions or [])))

        queues = []
        if self.gd_enabled:
            queues.append(("gd", "pending_gd_projection_sessions", "gd_events", "gd_sessions"))
        if self.roleplay_enabled:
            queues.append(("roleplay", "pending_roleplay_projection_sessions", "roleplay_events", "roleplay_sessions"))
        work = []
        for source, function, events, sessions in queues:
            keys = await rpc(self.sb, function, p_limit=8)
            work.extend((source, str(key), events, sessions) for key in keys or [])
        projection = self.projection
        owns_projection = False
        if work and result["graph_configured"] and projection is None:
            try:
                projection = AssessmentEvidenceProjection.from_settings()
                owns_projection = True
                await asyncio.to_thread(projection.initialize)
            except Exception as exc:
                logger.warning("assessment_projection_unavailable error_type=%s", type(exc).__name__)
                result["failures"] += 1
                if projection is not None:
                    await asyncio.to_thread(projection.close)
                projection = None
                owns_projection = False
        try:
            for source, key, event_table, session_table in work:
                if projection is None:
                    continue
                attempted_at = datetime.now(timezone.utc)
                try:
                    rows = await execute(self.sb.table(session_table).select("*").eq("id", key).limit(1))
                    if not rows:
                        continue
                    if source == "gd":
                        from app.group_discussion.evidence_delivery import GDEvidenceDelivery
                        from app.group_discussion.repository import GDRepository
                        delivery = await GDEvidenceDelivery(DueProjectionEvents(GDRepository(self.sb)), projection).deliver(rows[0])
                    else:
                        from app.role_play.evidence_delivery import RolePlayEvidenceDelivery
                        from app.role_play.repository import RolePlayRepository
                        delivery = await RolePlayEvidenceDelivery(DueProjectionEvents(RolePlayRepository(self.sb)), projection).deliver(rows[0])
                    result["projection_sessions_processed"] += 1
                    result["projection_events_delivered"] += int(delivery.get("delivered", 0))
                    result["projection_events_pending"] += int(delivery.get("pending", 0))
                    result["failures"] += int(delivery.get("failed", 0))
                except Exception as exc:
                    logger.warning("assessment_delivery_deferred source=%s error_type=%s", source, type(exc).__name__)
                    result["failures"] += 1
                # GD owns its per-event exponential backoff. Do not shorten it.
                # Existing RP manual delivery is unchanged; only worker attempts are delayed.
                if source == "roleplay":
                    await execute(self.sb.table(event_table).update({
                        "projection_next_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
                    }).eq("session_id", key).in_("projection_status", ["pending", "failed"])
                      .lte("projection_next_attempt_at", attempted_at.isoformat()))
        finally:
            if owns_projection:
                await asyncio.to_thread(projection.close)
        deferred_graph = bool(work and projection is None)
        await self._heartbeat("degraded" if result["failures"] or result["projection_events_pending"] or deferred_graph else "ok", result)
        return result

    async def run(self, stop, interval):
        while not stop.is_set():
            try:
                result = await self.run_once()
                logger.info("feature_recovery_tick %s", result)
            except Exception as exc:
                # No raw provider responses, connection strings, transcripts or credentials in logs.
                logger.error("feature_recovery_failed error_type=%s", type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass


async def main(once=False, interval=3):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(name, stop.set)
        except NotImplementedError:
            pass
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    worker = FeatureRecoveryWorker(sb)
    if once:
        await worker.run_once()
    else:
        await worker.run(stop, interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process one bounded batch and exit")
    parser.add_argument("--interval", type=float, default=3)
    args = parser.parse_args()
    if not 1 <= args.interval <= 300:
        parser.error("--interval must be between 1 and 300 seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main(args.once, args.interval))
