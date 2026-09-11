"""Bounded operational checks. Never probes an LLM or starts an Agora session."""
import asyncio
import time
from datetime import datetime, timezone

from app.core.config import settings
from app.integrations.feature_db import execute


class ReadinessProbe:
    def __init__(self, config=None, ttl=5):
        self.config = config or settings
        self.ttl = ttl
        self._lock = asyncio.Lock()
        self._cached = None
        self._checked_at = 0
        self._client_id = None

    async def _table(self, sb, table):
        try:
            await asyncio.wait_for(execute(sb.table(table).select("*").limit(0)), timeout=5)
            return True
        except Exception as exc:
            import structlog
            structlog.get_logger("intra_readiness").warning("table_check_failed", table=table, error=str(exc), error_type=type(exc).__name__)
            return False

    async def _worker(self, sb):
        try:
            rows = await asyncio.wait_for(execute(sb.table("feature_worker_health").select("last_seen_at,status")
                .order("last_seen_at", desc=True).limit(1)), timeout=5)
            if not rows or rows[0]["status"] not in {"ok", "working"}:
                return False
            seen = datetime.fromisoformat(rows[0]["last_seen_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - seen).total_seconds()
            return 0 <= age <= 300
        except Exception:
            return False

    async def check(self, sb):
        async with self._lock:
            if self._cached is not None and self._client_id == id(sb) and time.monotonic() - self._checked_at < self.ttl:
                return self._cached
            tables = ["users", "candidates", "jobs", "applications", "scheduled_interviews", "parsed_resumes", "reports"]
            features = []
            if self.config.CANDIDATE_ONBOARDING_ENABLED:
                features.extend(["candidate_profiles", "candidate_resume_versions"])
            if self.config.COMPANY_KNOWLEDGE_ENABLED:
                features.extend(["company_documents", "company_document_versions"])
            if self.config.ROLE_PLAY_ENABLED:
                features.extend(["roleplay_definitions", "roleplay_sessions", "roleplay_events"])
            if self.config.GROUP_DISCUSSION_ENABLED:
                features.extend(["gd_sessions", "gd_participants", "gd_events"])

            available = await asyncio.gather(*(self._table(sb, table) for table in tables + features))
            core_ready = all(available[:len(tables)])
            feature_ready = all(available[len(tables):])
            worker_required = self.config.ROLE_PLAY_ENABLED or self.config.GROUP_DISCUSSION_ENABLED
            worker_ready = await self._worker(sb) if worker_required and core_ready and feature_ready else not worker_required
            ready = core_ready and feature_ready and worker_ready
            result = {
                "status": "ready" if ready else "not_ready",
                "version": "1.0.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": {"application_schema": core_ready, "enabled_feature_schema": feature_ready,
                           "recovery_worker_required": worker_required, "recovery_worker_fresh": worker_ready},
                "external_probe_scope": "Supabase schema and saved worker heartbeat only; no LLM, Agora, storage-object or Neo4j network probe",
            }
            self._cached, self._checked_at, self._client_id = result, time.monotonic(), id(sb)
            return result
