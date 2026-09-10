"""Replayable GD projection; Supabase events remain the authoritative evidence."""
import asyncio
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.integrations.feature_db import execute
from app.intelligence.core.contracts import EvidenceSignal
from app.knowledge_graph.assessment_projection import AssessmentEvidenceProjection


class GDEvidenceDelivery:
    def __init__(self, repo, projection=None):
        self.repo = repo
        self.projection = projection

    async def deliver(self, session):
        events = [event for event in await self.repo.events(session["id"])
                  if event.get("projection_status") in {"pending", "failed"}]
        result = {"delivered": 0, "failed": 0, "pending": len(events)}
        if not events:
            return result
        projection = self.projection
        owns_projection = projection is None
        if projection is None:
            if not all((settings.NEO4J_URI, settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)):
                return result
            try:
                projection = AssessmentEvidenceProjection.from_settings()
                await asyncio.to_thread(projection.initialize)
            except Exception:
                if projection is not None:
                    await asyncio.to_thread(projection.close)
                return result
        try:
            for event in events:
                attempts = int(event.get("projection_attempts") or 0) + 1
                try:
                    evidence = [EvidenceSignal.model_validate(item) for item in event["evidence"]]
                    if not evidence:
                        raise ValueError("Missing saved evidence")
                    for item in evidence:
                        if (str(item.event_id) != str(event["id"])
                                or str(item.session_id) != str(session["id"])
                                or str(item.candidate_id) != str(event["candidate_id"])
                                or str(item.participant_id) != str(event["participant_id"])
                                or item.source_type != "group_discussion"
                                or item.quote not in event["source_text"]):
                            raise ValueError("Evidence identity or provenance mismatch")
                        await asyncio.to_thread(
                            projection.project, item, owner_id=str(session["created_by"]),
                            tenant_key=session["tenant_key"], source_text=event["source_text"],
                        )
                    update = {"projection_status": "delivered", "projection_error": None,
                              "projection_attempts": attempts}
                    result["delivered"] += 1
                    result["pending"] -= 1
                except Exception as exc:
                    delay = min(3600, 15 * (2 ** min(attempts - 1, 8)))
                    update = {"projection_status": "failed", "projection_error": type(exc).__name__[:100],
                              "projection_attempts": attempts,
                              "projection_next_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()}
                    result["failed"] += 1
                # A lost acknowledgement is safe: the next projection MERGEs the same IDs.
                await execute(self.repo.sb.table("gd_events").update(update).eq("id", event["id"]))
        finally:
            if owns_projection:
                await asyncio.to_thread(projection.close)
        return result
