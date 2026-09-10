import hashlib
import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.integrations.aicredits_client import AICreditsError
from app.integrations.assessment_realtime import LocalTextSessionAdapter
from app.integrations.feature_db import tenant_key
from app.voice.authorization import require_candidate, require_recruiter
from app.intelligence.role_play.analyzer import RolePlayIntelligence
from app.intelligence.core.evidence import ground_findings
from app.role_play.models import PersonaDefinition, ScenarioDefinition, RolePlayState, RolePlayAction, RolePlayActionType
from app.role_play.orchestrator import RolePlayOrchestrator
from app.role_play.response_generator import RolePlayResponseGenerator
from app.role_play.repository import RolePlayRepository
from app.role_play.reporting import RolePlayReporting, report_view


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


class RolePlayService:
    def __init__(self, sb, client=None, realtime=None, policy_enricher=None):
        self.repo = RolePlayRepository(sb); self.client = client
        self.policy_enricher = policy_enricher
        self.intelligence = RolePlayIntelligence(client); self.orchestrator = RolePlayOrchestrator()
        self.responses = RolePlayResponseGenerator(client); self.realtime = realtime or LocalTextSessionAdapter()

    async def save_definition(self, actor, kind, body, key=None):
        require_recruiter(actor)
        if key:
            old = await self.repo.definition(actor, key, kind)
            if not old: raise NotFoundError("Role-play definition not found")
        if kind == "scenario":
            persona = await self.repo.definition(actor, str(body.definition.persona_id), "persona")
            if not persona or persona.get("archived_at"): raise ValidationError("Choose an active persona from your workspace")
        key = key or str(uuid5(NAMESPACE_URL, actor.user_id + ":" + kind + ":" + str(body.request_id)))
        return await self.repo.save_definition(actor, key, kind, body, fingerprint(body.definition.model_dump(mode="json")))

    async def require_session(self, actor, key, *, candidate_turn=False):
        row = await self.repo.session(key)
        if not row: raise NotFoundError("Role-play session not found")
        if actor.role == "candidate":
            if str(row["candidate_id"]) != actor.candidate_id: raise NotFoundError("Role-play session not found")
        elif candidate_turn or str(row["created_by"]) != actor.user_id or row["tenant_key"] != tenant_key(actor):
            raise ForbiddenError("Role-play session is outside your workspace")
        else: require_recruiter(actor)
        return row

    async def create(self, actor, body):
        require_recruiter(actor)
        candidate = await require_candidate(actor, body.candidate_id, self.repo.sb)
        scenario = await self.repo.definition(actor, str(body.scenario_id), "scenario")
        if not scenario or scenario.get("archived_at"): raise NotFoundError("Active scenario not found")
        definition = ScenarioDefinition.model_validate(scenario["definition"])
        persona = await self.repo.definition(actor, str(definition.persona_id), "persona")
        if not persona or persona.get("archived_at"): raise ValidationError("Scenario persona is unavailable")
        person = PersonaDefinition.model_validate(persona["definition"])
        state = RolePlayState(escalation=person.initial_escalation, unresolved_objections=person.concerns[:10])
        parsed = candidate.get("parsed_resumes") or []
        claims = parsed[0] if isinstance(parsed,list) and parsed else parsed if isinstance(parsed,dict) else {}
        profile = {key: claims.get(key, [])[:10] for key in ("skills", "experience", "education", "projects")}
        payload = {"id": str(uuid5(NAMESPACE_URL, actor.user_id+":roleplay-session:"+str(body.request_id))),
            "scenario_id": str(body.scenario_id), "candidate_id": body.candidate_id,
            "scenario_snapshot": {"id": scenario["id"], "revision": scenario["revision"], "definition": definition.model_dump(mode="json")},
            "persona_snapshot": {"id": persona["id"], "revision": persona["revision"], "definition": person.model_dump(mode="json")},
            "candidate_profile": profile, "state": state.model_dump(mode="json"), "request_id": str(body.request_id),
            "request_hash": fingerprint(body.model_dump(mode="json"))}
        return await self.repo.create_session(actor, payload)

    async def view(self, actor, key):
        row = await self.require_session(actor,key)
        events = await self.repo.events(key)
        return self.project(row, actor, events)

    def project(self, row, actor, events=None):
        scenario = row["scenario_snapshot"]["definition"]
        state = row["state"]; phase = scenario["phases"][state["phase_index"]]
        elapsed = (datetime.now(timezone.utc)-datetime.fromisoformat(state["started_at"].replace("Z","+00:00"))).total_seconds() if state.get("started_at") else 0
        result = {"id": row["id"], "title": scenario["title"], "description": scenario["description"],
            "candidate_role": scenario["candidate_role"], "persona_name": row["persona_snapshot"]["definition"]["name"],
            "status": row["status"], "revision": row["revision"], "phase": {"title": phase["title"], "brief": phase["brief"]},
            "turn_count": state["turn_count"], "time_remaining_seconds": max(0,round(scenario["duration_seconds"]-elapsed)) if row["status"] not in {"completed","cancelled"} else 0,
            "report_status": row["report_status"], "report": report_view(row.get("report"),actor.role=="candidate"),
            "realtime": self.realtime.describe(row["id"]), "created_at": row["created_at"]}
        if actor.role != "candidate": result["candidate_id"] = str(row["candidate_id"])
        if events is not None:
            result["events"] = [{"id":event["id"],"revision":event["revision"],"kind":event["kind"],
                "text":event["source_text"],"response":event["response"],"created_at":event["created_at"],
                "analysis_status":event["analysis"].get("status","unavailable"),"policy_context":event.get("policy_context")} for event in events]
        return result

    async def _replay(self, key, request_id, request_hash):
        event = await self.repo.event_request(key,str(request_id))
        if event and event["request_hash"] != request_hash: raise ConflictError("Request ID belongs to another event")
        return event

    async def control(self, actor, key, body):
        row = await self.require_session(actor,key, candidate_turn=body.action=="start")
        request_hash = fingerprint({"kind": body.action})
        if await self._replay(key,body.request_id,request_hash): return await self.view(actor,key)
        state = RolePlayState.model_validate(row["state"]); now=datetime.now(timezone.utc)
        scenario = ScenarioDefinition.model_validate(row["scenario_snapshot"]["definition"])
        if body.action=="start":
            if state.status!="assigned": raise ConflictError("This scenario has already started")
            state.status="active"; state.started_at=now; state.revealed_keys=scenario.phases[0].reveal_keys[:]
            response=scenario.phases[0].brief
        elif body.action in {"finish","cancel"}:
            if state.status not in {"assigned","active"}: raise ConflictError("This scenario has ended")
            state.status="completed" if body.action=="finish" else "cancelled"; state.ended_at=now; state.completion_reason="participant_finished" if actor.role=="candidate" else "recruiter_finished"
            response="The simulation has ended."
        event={"id":str(uuid4()),"kind":body.action,"request_id":str(body.request_id),"request_hash":request_hash,
            "source_text":"","response":response,"analysis":{"status":"not_applicable"},"evidence":[],"action":{},"policy_context":None}
        await self.repo.commit(actor,key,body.expected_revision,event,state)
        return await self.view(actor,key)

    async def turn(self, actor, key, body):
        row=await self.require_session(actor,key,candidate_turn=True)
        request_hash=fingerprint({"kind":"turn","text":body.text})
        if await self._replay(key,body.request_id,request_hash): return await self.view(actor,key)
        if row["revision"]!=body.expected_revision: raise ConflictError("Another turn arrived; refresh the session")
        state=RolePlayState.model_validate(row["state"])
        if state.status!="active": raise ConflictError("Start an active session before responding")
        scenario=ScenarioDefinition.model_validate(row["scenario_snapshot"]["definition"])
        persona=PersonaDefinition.model_validate(row["persona_snapshot"]["definition"])
        now=datetime.now(timezone.utc)
        if state.started_at and (now-state.started_at).total_seconds()>=scenario.duration_seconds:
            raise ConflictError("The time limit has elapsed. Finish the session to review your feedback")
        phase=scenario.phases[state.phase_index]; event_id=str(uuid4())
        events=await self.repo.events(key)
        recent=[{"candidate":e["source_text"],"persona":e["response"]} for e in events[-4:]]
        policy_context = await self._policy_context(row, scenario, events)
        analysis=None; evidence=[]; error=None
        try:
            analysis=await self.intelligence.analyze(text=body.text,scenario=scenario,phase=phase,recent_turns=recent,
                                                     policy_context=policy_context)
            evidence=ground_findings(analysis.findings,text=body.text,competencies=scenario.competencies,
                event_id=event_id,candidate_id=str(row["candidate_id"]),session_id=key,source_type="role_play",observed_at=now,phase_id=phase.id)
        except AICreditsError as exc:
            analysis=None; error=exc.code
        new_state,action=self.orchestrator.decide(state,persona,scenario,analysis,now=now)
        try:
            response = self.responses.policy_response(action) if scenario.policy_query else await self.responses.generate(persona,scenario,new_state,action,body.text,recent)
        except AICreditsError: response="Please explain the next step you would take in this situation."
        event={"id":event_id,"kind":"turn","request_id":str(body.request_id),"request_hash":request_hash,
            "source_text":body.text,"response":response,"action":action.model_dump(mode="json"),
            "analysis":{"status":"evaluated" if analysis and evidence else "unavailable","error_code":error,
                        "signals":[s.model_dump(mode="json") for s in analysis.signals] if analysis else []},
            "evidence":[e.model_dump(mode="json") for e in evidence],"policy_context":policy_context}
        await self.repo.commit(actor,key,body.expected_revision,event,new_state)
        return await self.view(actor,key)

    async def _policy_context(self, row, scenario, events):
        if not scenario.policy_query:
            return None
        # Pin the first usable source snapshot, including across process restarts.
        for event in events:
            context = event.get("policy_context")
            if isinstance(context, dict) and context.get("status") == "available":
                return context
        from app.core.config import settings
        if settings.COMPANY_KNOWLEDGE_ENABLED:
            from app.company_knowledge.grounding import CompanyPolicyEnricher
            try:
                enricher = self.policy_enricher or CompanyPolicyEnricher(self.repo.sb)
                context = await enricher.enrich(str(row["created_by"]), row["tenant_key"], scenario.policy_query)
                return context.model_dump(mode="json")
            except Exception:
                pass
        return {"source": "company_policy", "status": "unavailable", "excerpts": [],
                "effective_at": datetime.now(timezone.utc).isoformat(),
                "message": "Company policy is unavailable. Ask the company for clarification; do not assume a rule."}

    async def generate_report(self, actor, key):
        row=await self.require_session(actor,key)
        result=await RolePlayReporting(self.repo,self.client).generate(row,actor)
        return report_view(result,actor.role=="candidate")
