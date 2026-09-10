import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from pydantic import ValidationError as PydanticValidationError
from app.core.deps import get_current_user, get_supabase
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError, register_exception_handlers
from app.integrations.aicredits_client import AICreditsError
from app.intelligence.role_play.analyzer import RolePlayAnalysis, BehavioralSignal
from app.role_play.models import PersonaDefinition, PersonaWrite, ScenarioDefinition, ScenarioWrite, SessionCreate, TurnInput, ControlInput, RolePlaySignal, RolePlayState
from app.role_play.orchestrator import RolePlayOrchestrator
from app.role_play.service import RolePlayService
from app.role_play.routes import router, service
from app.role_play.evidence_delivery import RolePlayEvidenceDelivery


class RolePlayLLM:
    def __init__(self): self.calls=[]; self.fail=False; self.bad_quote=False
    async def generate_feature_json(self,purpose,*,messages):
        self.calls.append((purpose,messages)); assert purpose=="role_play"
        if self.fail: raise AICreditsError("rate_limited")
        prompt=messages[0]["content"]; data=json.loads(messages[1]["content"])
        if "Evaluate the candidate's behavior" in prompt:
            text=data["candidate_text"]
            return {"findings":[{"competency":"communication","observation":"The candidate proposes a concrete next step.",
                "quote":"invented text" if self.bad_quote else text,"score":7,"confidence":.8}],
                "signals":[{"signal":"solution","quote":text}]}
        if "Format a role-play coaching report" in prompt:
            evidence_id=data["assessment"]["evidence"][0]["id"]
            return {"summary":"The candidate offered clear next steps in the observed simulation.",
                "strengths":[{"text":"You described a concrete next step.","evidence_ids":[evidence_id]}],
                "improvements":[{"text":"Explain how you would confirm the outcome.","evidence_ids":[evidence_id]}]}
        return {"text":"How would you confirm that this plan addresses the concern?"}


def persona():
    return PersonaDefinition(name="Sam",description="A customer frustrated by a delayed order.",personality="Concerned but willing to listen",
        communication_style="Direct and specific",concerns=["A reliable delivery date"],
        restricted_information=["UNREVEALED-ACCOUNT-SECRET"],allowed_information=["The shipment is delayed."])


def scenario(persona_id):
    return ScenarioDefinition(title="Delivery conversation",description="Help a customer understand the next steps after a delayed shipment.",candidate_role="Customer support lead",persona_id=persona_id,
        phases=[{"id":"understand","title":"Understand the concern","brief":"A customer asks when their delayed shipment will arrive.","objectives":["Clarify the next step"]},
                {"id":"resolve","title":"Agree a resolution","brief":"Agree a practical next step with the customer.","objectives":["Confirm a resolution"],"reveal_keys":["delivery"]}],
        hidden_information={"delivery":"The confirmed delivery window is next Tuesday.","internal":"UNREVEALED-BUSINESS-SECRET"})


async def setup_session(sb,dsn,actors,client=None):
    recruiter,candidate,_=actors
    with psycopg.connect(dsn,autocommit=True) as conn:
        job="j-"+uuid4().hex
        conn.execute("INSERT INTO jobs(id,title,department,location,description,created_by,status) VALUES(%s,'Support','Operations','Remote','Support role',%s,'published')",(job,recruiter.user_id))
        conn.execute("INSERT INTO applications(id,job_id,candidate_id) VALUES(%s,%s,%s)",(str(uuid4()),job,candidate.candidate_id))
    svc=RolePlayService(sb,client=client or RolePlayLLM())
    p=await svc.save_definition(recruiter,"persona",PersonaWrite(request_id=uuid4(),definition=persona()))
    sc=await svc.save_definition(recruiter,"scenario",ScenarioWrite(request_id=uuid4(),definition=scenario(p["id"])))
    row=await svc.create(recruiter,SessionCreate(scenario_id=sc["id"],candidate_id=candidate.candidate_id,request_id=uuid4()))
    return svc,row


def test_scenario_validation_and_deterministic_escalation():
    p=persona(); sc=scenario(uuid4()); engine=RolePlayOrchestrator()
    state=RolePlayState(status="active",started_at=datetime.now(timezone.utc))
    signal=RolePlayAnalysis(findings=[],signals=[BehavioralSignal(signal=RolePlaySignal.HOSTILITY,quote="This is your fault")])
    next_state,action=engine.decide(state,p,sc,signal)
    assert next_state.escalation==3 and action.action.value=="ESCALATE" and state.escalation==2
    signal.signals=[BehavioralSignal(signal=RolePlaySignal.EMPATHY,quote="I understand")]
    next_state,action=engine.decide(next_state,p,sc,signal)
    assert next_state.escalation==2 and action.action.value=="DEESCALATE"
    invalid=sc.model_dump(mode="json"); invalid["phases"][1]["reveal_keys"]=["unknown"]
    with pytest.raises(PydanticValidationError): ScenarioDefinition.model_validate(invalid)


@pytest.mark.asyncio
async def test_real_roleplay_flow_pinning_restart_evidence_report_and_graph(feature_sb,feature_database,feature_actors):
    recruiter,candidate,peer=feature_actors; client=RolePlayLLM()
    svc,row=await setup_session(feature_sb,feature_database,feature_actors,client)
    key=row["id"]
    view=await svc.control(candidate,key,ControlInput(request_id=uuid4(),expected_revision=0,action="start"))
    assert view["status"]=="active" and view["realtime"]["voice_available"] is False
    text="I will check the delivery schedule and confirm a reliable next step."
    first=TurnInput(request_id=uuid4(),expected_revision=1,text=text)
    view=await svc.turn(candidate,key,first)
    assert view["phase"]["title"]=="Agree a resolution" and view["turn_count"]==1
    assert "UNREVEALED" not in json.dumps(view)
    assert "UNREVEALED" not in json.dumps(client.calls)
    calls=len(client.calls)
    assert (await svc.turn(candidate,key,first))["revision"]==2 and len(client.calls)==calls
    with pytest.raises(ConflictError): await svc.turn(candidate,key,first.model_copy(update={"text":"changed text"}))
    recovered=RolePlayService(feature_sb,client=client)
    view=await recovered.turn(candidate,key,TurnInput(request_id=uuid4(),expected_revision=2,text="I will call you tomorrow to confirm whether the delivery plan worked."))
    assert view["status"]=="completed"
    events=await svc.repo.events(key)
    assert len([e for e in events if e["evidence"]])==2
    assert all(item["quote"] in event["source_text"] for event in events for item in event["evidence"])
    report=await recovered.generate_report(candidate,key)
    assert report["candidate_rating"]==3.8 and "evidence" not in report and "narrative" not in report
    assert (await recovered.generate_report(recruiter,key))["overall_score"]==70
    with pytest.raises(NotFoundError): await svc.view(peer,key)
    with pytest.raises(ForbiddenError): await svc.turn(recruiter,key,first)
    projection=Mock(); projection.project.side_effect=RuntimeError("Graph unavailable")
    delivery=RolePlayEvidenceDelivery(svc.repo,projection)
    assert (await delivery.deliver(row))["pending"]==2
    projection.project.side_effect=None
    assert (await delivery.deliver(row))=={"delivered":2,"pending":0}
    assert (await delivery.deliver(row))=={"delivered":0,"pending":0}


@pytest.mark.asyncio
async def test_real_provider_failure_records_turn_without_inventing_evidence(feature_sb,feature_database,feature_actors):
    _,candidate,_=feature_actors; client=RolePlayLLM()
    svc,row=await setup_session(feature_sb,feature_database,feature_actors,client)
    await svc.control(candidate,row["id"],ControlInput(request_id=uuid4(),expected_revision=0,action="start"))
    client.fail=True
    view=await svc.turn(candidate,row["id"],TurnInput(request_id=uuid4(),expected_revision=1,text="I will clarify the delivery problem."))
    assert view["events"][-1]["analysis_status"]=="unavailable"
    assert not (await svc.repo.events(row["id"]))[-1]["evidence"]
    await svc.control(candidate,row["id"],ControlInput(request_id=uuid4(),expected_revision=2,action="finish"))
    with pytest.raises(ValidationError): await svc.generate_report(candidate,row["id"])
    assert (await svc.repo.session(row["id"]))["report_status"]=="failed"


@pytest.mark.asyncio
async def test_real_concurrent_turns_and_forged_evidence(feature_sb,feature_database,feature_actors):
    _,candidate,_=feature_actors; client=RolePlayLLM()
    svc,row=await setup_session(feature_sb,feature_database,feature_actors,client)
    await svc.control(candidate,row["id"],ControlInput(request_id=uuid4(),expected_revision=0,action="start"))
    results=await asyncio.gather(*(svc.turn(candidate,row["id"],TurnInput(request_id=uuid4(),expected_revision=1,text="I will check the delivery schedule.")) for _ in range(2)),return_exceptions=True)
    assert sum(isinstance(r,dict) for r in results)==1
    assert any(isinstance(r,ConflictError) for r in results)
    client.bad_quote=True
    await svc.turn(candidate,row["id"],TurnInput(request_id=uuid4(),expected_revision=2,text="I will contact the warehouse."))
    event=(await svc.repo.events(row["id"]))[-1]
    assert not event["evidence"] and event["analysis"]["status"]=="unavailable"


@pytest.mark.asyncio
async def test_real_roleplay_api_private_projection(feature_sb,feature_database,feature_actors):
    _,candidate,peer=feature_actors
    svc,row=await setup_session(feature_sb,feature_database,feature_actors)
    app=FastAPI();app.include_router(router,prefix="/api/v1");register_exception_handlers(app)
    claims={"sub":candidate.user_id,"role":"admin"}
    app.dependency_overrides[get_current_user]=lambda:claims;app.dependency_overrides[get_supabase]=lambda:feature_sb
    app.dependency_overrides[service]=lambda:svc
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        response=await client.get("/api/v1/roleplay/sessions/"+row["id"])
        assert response.status_code==200,response.text
        assert "hidden_information" not in response.text and "restricted_information" not in response.text
        assert (await client.get("/api/v1/roleplay/personas")).status_code==403
        claims["sub"]=peer.user_id
        assert (await client.get("/api/v1/roleplay/sessions/"+row["id"])).status_code==404
