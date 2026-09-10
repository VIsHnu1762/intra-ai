from datetime import datetime, timezone
from uuid import uuid4
from app.core.config import settings
from app.integrations.aicredits_client import AICreditsError
from app.intelligence.core.evidence import ground_findings
from app.intelligence.group_discussion.analyzer import GDIntelligence
from app.intelligence.group_discussion.signals import participation_signals
from app.group_discussion.models import GDConfiguration
from app.group_discussion.moderator import GDModerator
from app.group_discussion.response_generator import GDResponseGenerator


class GDProcessing:
    def __init__(self,repo,client=None,policy_enricher=None):
        self.repo=repo;self.intelligence=GDIntelligence(client);self.moderator=GDModerator();self.responses=GDResponseGenerator(client)
        self.policy_enricher=policy_enricher

    async def drain(self,key,max_events=3):
        completed=0
        for _ in range(max_events):
            lease=str(uuid4());claimed=await self.repo.claim(key,lease)
            if not claimed:return completed
            event=claimed["event"];session=claimed["session"]
            configuration=GDConfiguration.model_validate(session["configuration"])
            participants=await self.repo.participants(key)
            events=[e for e in await self.repo.events(key) if e["sequence"]<=event["sequence"]]
            recent=[{"participant":e["participant_id"],"text":e["source_text"]} for e in events if e["kind"]=="message"][-4:]
            policy_context=None
            if configuration.policy_query:
                # Pin the first usable source snapshot for all participants in this discussion.
                # Later document edits cannot silently change the rules mid-discussion.
                policy_context=next((e["policy_context"] for e in events
                    if isinstance(e.get("policy_context"),dict) and e["policy_context"].get("status")=="available"),None)
                if policy_context is None:
                    policy_context={"source":"company_policy","status":"unavailable","excerpts":[],
                        "effective_at":datetime.now(timezone.utc).isoformat(),
                        "message":"Company policy is unavailable. Do not infer or invent a rule."}
                    if settings.COMPANY_KNOWLEDGE_ENABLED:
                        try:
                            from app.company_knowledge.grounding import CompanyPolicyEnricher
                            enricher=self.policy_enricher or CompanyPolicyEnricher(self.repo.sb)
                            grounded=await enricher.enrich(str(session["created_by"]),session["tenant_key"],configuration.policy_query)
                            policy_context=grounded.model_dump(mode="json")
                        except Exception:
                            # Raw contributions remain durable even if optional knowledge retrieval fails.
                            pass
            analysis=None;evidence=[];error=None
            try:
                analysis=await self.intelligence.analyze(event,configuration,recent,policy_context=policy_context)
                evidence=ground_findings(analysis.findings,text=event["source_text"],competencies=configuration.competencies,
                    event_id=event["id"],candidate_id=str(event["candidate_id"]),session_id=key,source_type="group_discussion",
                    observed_at=datetime.fromisoformat(event["created_at"].replace("Z","+00:00")),participant_id=event["participant_id"])
            except AICreditsError as exc:analysis=None;error=exc.code
            signals=participation_signals(events,participants,started_at=session.get("started_at"),duration_seconds=configuration.duration_seconds)
            action,state=self.moderator.decide(session,signals,analysis,participants,event["sequence"])
            try:response=self.responses.policy_response(action) if configuration.policy_query else await self.responses.generate(action,configuration,recent,participants)
            except AICreditsError:response="Please keep the discussion focused and give everyone an opportunity to contribute." if action.action.value!="CONTINUE" else ""
            payload={"analysis":{"status":"evaluated" if analysis and evidence else "unavailable","error_code":error,
                "signals":[s.model_dump() for s in analysis.signals] if analysis else []},
                "evidence":[e.model_dump(mode="json") for e in evidence],"action":action.model_dump(mode="json"),
                "response":response,"moderator_state":state,"deterministic_signals":signals,
                "policy_context":policy_context or {}}
            await self.repo.finish(key,event["id"],lease,payload);completed+=1
        return completed
