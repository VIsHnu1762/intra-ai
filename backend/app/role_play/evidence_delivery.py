import asyncio
from datetime import datetime, timezone
from app.integrations.feature_db import execute
from app.intelligence.core.contracts import EvidenceSignal
from app.knowledge_graph.assessment_projection import AssessmentEvidenceProjection


class RolePlayEvidenceDelivery:
    def __init__(self, repo, projection=None): self.repo,self.projection=repo,projection

    async def deliver(self, session):
        events=[e for e in await self.repo.events(session["id"]) if e["projection_status"] in {"pending","failed"}]
        delivered,failed=0,0; owned=False; projection=self.projection
        if not events: return {"delivered":0,"pending":0}
        try:
            if projection is None:
                projection=AssessmentEvidenceProjection.from_settings(); owned=True
                await asyncio.to_thread(projection.initialize)
            for event in events:
                try:
                    for item in event["evidence"]:
                        evidence=EvidenceSignal.model_validate(item)
                        if evidence.session_id!=session["id"] or evidence.candidate_id!=str(session["candidate_id"]):
                            raise ValueError("Evidence provenance mismatch")
                        await asyncio.to_thread(projection.project,evidence,owner_id=str(session["created_by"]),
                            tenant_key=session["tenant_key"],source_text=event["source_text"])
                    await self._status(event,"delivered",None); delivered+=1
                except Exception:
                    await self._status(event,"failed","GRAPH_PROJECTION_FAILED"); failed+=1
        except Exception:
            failed=len(events)
        finally:
            if owned and projection: await asyncio.to_thread(projection.close)
        return {"delivered":delivered,"pending":failed}

    async def _status(self,event,status,error):
        await execute(self.repo.sb.table("roleplay_events").update({"projection_status":status,
            "projection_attempts":event["projection_attempts"]+1,"projection_error":error,
            "projection_attempted_at":datetime.now(timezone.utc).isoformat()}).eq("id",event["id"]))
