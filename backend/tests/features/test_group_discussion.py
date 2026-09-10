"""GD contract and persistence tests. No Agora or external LLM calls."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.group_discussion.models import GDConfiguration
from app.group_discussion.routes import router, service
from app.group_discussion.service import GDService
from app.services.workspace_access import current_actor, recruiter_actor


class GDLLM:
    async def generate_feature_json(self, purpose, *, messages):
        assert purpose == "gd"
        prompt = messages[0]["content"]
        data = json.loads(messages[-1]["content"])
        if "findings" in prompt:
            def own_text(value):
                if isinstance(value, str) and value.startswith("I propose "):
                    return value
                if isinstance(value, dict):
                    for item in value.values():
                        found = own_text(item)
                        if found:
                            return found
                return ""
            text = own_text(data)
            return {"findings": [{"competency": "communication", "observation": "Explains a proposed action.", "quote": text, "score": 7, "confidence": 0.8}], "signals": []}
        if "strengths" in prompt:
            evidence = data["assessment"]["evidence"][0]
            return {"summary": "Communicated a practical proposal.", "strengths": [{"text": "Explains a practical proposal.", "evidence_ids": [evidence["id"]]}], "improvements": [{"text": "Clarify the next measurement.", "evidence_ids": [evidence["id"]]}]}
        return {"text": "Let us hear a different perspective on this proposal."}


def test_configuration_rejects_unbounded_and_unknown_inputs():
    with pytest.raises(ValueError):
        GDConfiguration(title="Discussion", topic="How should we prioritize?", max_participants=13)
    with pytest.raises(ValueError):
        GDConfiguration(title="Discussion", topic="How should we prioritize?", provider="groq")


def test_gd_invitation_lifecycle_and_message_identity(feature_sb, feature_database, feature_actors):
    """Use real PostgREST/RPC transactions while replacing only model output."""
    actors = list(feature_actors.values()) if isinstance(feature_actors, dict) else list(feature_actors)
    owner = next(a for a in actors if a.role in {"recruiter", "admin"})
    candidate = next(a for a in actors if a.role == "candidate")
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    svc = GDService(feature_sb, client=GDLLM())
    app.dependency_overrides[service] = lambda: svc
    app.dependency_overrides[current_actor] = lambda: owner
    app.dependency_overrides[recruiter_actor] = lambda: owner
    client = TestClient(app, raise_server_exceptions=True)
    created = client.post("/api/v1/group-discussions", json={"configuration": {"title": "Fair prioritization", "topic": "How should a small team prioritize customer requests?", "competencies": ["communication"]}, "request_id": str(uuid4())})
    assert created.status_code == 201, created.text
    session = created.json()
    key = session["id"]
    assert session["status"] == "lobby"
    assert session["realtime"]["voice_available"] is False
    app.dependency_overrides[current_actor] = lambda: candidate
    # Membership, not possession of a session ID, determines access.
    from app.core.exceptions import AppError
    with pytest.raises(AppError):
        client.get(f"/api/v1/group-discussions/{key}")
    app.dependency_overrides[current_actor] = lambda: owner
    view = client.get(f"/api/v1/group-discussions/{key}")
    assert view.status_code == 200
    assert view.json()["participants"] == []


@pytest.mark.asyncio
async def test_gd_two_candidates_and_persisted_reports(feature_sb, feature_database, feature_actors):
    from test_role_play import setup_session, RolePlayLLM
    from app.core.exceptions import AppError
    await setup_session(feature_sb, feature_database, feature_actors, RolePlayLLM())
    actors = list(feature_actors.values()) if isinstance(feature_actors, dict) else list(feature_actors)
    owner = next(a for a in actors if a.role in {"recruiter", "admin"})
    candidate = next(a for a in actors if a.role == "candidate")
    user = feature_sb.table("users").select("*").eq("id", candidate.user_id).single().execute().data
    candidate_row = feature_sb.table("candidates").select("*").eq("id", candidate.candidate_id).single().execute().data
    application = feature_sb.table("applications").select("*").eq("candidate_id", candidate.candidate_id).limit(1).execute().data[0]
    uid, cid = str(uuid4()), str(uuid4())
    email = f"gd-{uid}@example.test"
    feature_sb.table("users").insert({**user, "id": uid, "email": email, "name": "Second participant"}).execute()
    feature_sb.table("candidates").insert({**candidate_row, "id": cid, "email": email, "name": "Second participant"}).execute()
    feature_sb.table("applications").insert({**application, "id": str(uuid4()), "candidate_id": cid}).execute()
    second = replace(candidate, user_id=uid, candidate_id=cid, email=email, name="Second participant")
    from test_company_intelligence import context as policy_fixture
    class PolicyEnricher:
        calls = 0
        async def enrich(self, owner_id, tenant_key, query):
            assert owner_id == owner.user_id
            assert query == "pilot approval"
            self.calls += 1
            return policy_fixture()
    policy = PolicyEnricher()
    selected = [owner]
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    svc = GDService(feature_sb, client=GDLLM(), policy_enricher=policy)
    app.dependency_overrides[service] = lambda: svc
    app.dependency_overrides[current_actor] = lambda: selected[0]
    app.dependency_overrides[recruiter_actor] = lambda: selected[0]
    client = TestClient(app)
    base = "/api/v1/group-discussions"
    payload = {"configuration": {"title": "Evidence discussion", "topic": "How should we prioritize a small customer pilot?", "competencies": ["communication"], "policy_query": "pilot approval"}, "request_id": str(uuid4())}
    session = client.post(base, json=payload).json()
    key = session["id"]
    url = f"{base}/{key}"
    assert client.post(base, json=payload).json()["id"] == key
    invitations = []
    for member in (candidate, second):
        invite = {"candidate_id": member.candidate_id, "request_id": str(uuid4())}
        response = client.post(url + "/invitations", json=invite)
        assert response.status_code == 201, response.text
        invitations.append(response.json())
        assert client.post(url + "/invitations", json=invite).json() == response.json()
    from urllib.parse import urlparse, parse_qs
    tokens = [parse_qs(urlparse(inv["join_url"]).fragment)["token"][0] for inv in invitations]
    selected[0] = second
    with pytest.raises(AppError):
        client.post(url + "/join", json={"token": tokens[0], "request_id": str(uuid4())})
    for member, token in zip((candidate, second), tokens):
        selected[0] = member
        join = {"token": token, "request_id": str(uuid4())}
        response = client.post(url + "/join", json=join)
        assert response.status_code == 200, response.text
        assert client.post(url + "/join", json=join).status_code == 200
        with pytest.raises(AppError):
            client.post(url + "/join", json={**join, "request_id": str(uuid4())})
    selected[0] = owner
    session = client.get(url).json()
    response = client.post(url + "/control", json={"action": "start", "expected_revision": session["revision"], "request_id": str(uuid4())})
    assert response.status_code == 200, response.text
    for member in (candidate, second):
        selected[0] = member
        for proposal in ("I propose a small customer pilot before committing the budget.", "I propose measuring retention and reviewing the result next week."):
            message = {"text": proposal, "request_id": str(uuid4())}
            response = client.post(url + "/messages", json=message)
            assert response.status_code == 201, response.text
            replay = client.post(url + "/messages", json=message)
            assert replay.status_code == 201, replay.text
    selected[0] = owner
    session = client.get(url).json()
    response = client.post(url + "/control", json={"action": "finish", "expected_revision": session["revision"], "request_id": str(uuid4())})
    assert response.status_code == 200, response.text
    records = feature_sb.table("gd_events").select("*").eq("session_id", key).eq("kind", "message").execute().data
    assert len(records) == 4
    assert policy.calls == 1
    assert all(row["policy_context"]["excerpts"][0]["version_id"] == "version-2" for row in records)
    assert all(row["evidence"] for row in records), [row["analysis"] for row in records]
    for row in records:
        for evidence in row["evidence"]:
            assert evidence["candidate_id"] == row["candidate_id"]
            assert evidence["participant_id"] == row["participant_id"]
            assert evidence["quote"] in row["source_text"]
    for member in (candidate, second):
        selected[0] = member
        participant = next(p for p in session["participants"] if p["candidate_id"] == member.candidate_id)
        response = client.post(url + f"/participants/{participant['id']}/report")
        assert response.status_code == 200, response.text
        report = response.json()
        assert 1 <= report["candidate_rating"] <= 5, report
        assert client.get(url).json()["report_status"] == "ready"
        assert report["policy_contexts"][0]["excerpts"][0]["version_id"] == "version-2"
        assert "evidence" not in report and "recommendation" not in report
    selected[0] = candidate
    own_view = client.get(url).json()
    assert all("candidate_id" not in participant for participant in own_view["participants"])
    peer_id = next(p["id"] for p in session["participants"] if p["candidate_id"] == second.candidate_id)
    with pytest.raises(AppError):
        client.post(url + f"/participants/{peer_id}/report")
    from app.group_discussion.evidence_delivery import GDEvidenceDelivery
    from app.group_discussion.repository import GDRepository
    from app.intelligence.core.contracts import EvidenceSignal
    class Projection:
        def __init__(self): self.ids = set(); self.fail = False
        def project(self, item, **scope):
            assert isinstance(item, EvidenceSignal)
            assert scope["owner_id"] == owner.user_id
            assert item.quote in scope["source_text"]
            if self.fail:
                raise RuntimeError("Synthetic projection outage")
            self.ids.add(item.id)
    projection = Projection()
    row = feature_sb.table("gd_sessions").select("*").eq("id", key).single().execute().data
    delivery = GDEvidenceDelivery(GDRepository(feature_sb), projection)
    projection.fail = True
    failed = await delivery.deliver(row)
    assert failed["failed"] == 4 and failed["delivered"] == 0
    deferred = feature_sb.table("gd_events").select("projection_status,projection_next_attempt_at").eq("session_id", key).eq("kind", "message").execute().data
    assert all(event["projection_status"] == "failed" for event in deferred)
    assert all(datetime.fromisoformat(event["projection_next_attempt_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc) for event in deferred)
    projection.fail = False
    result = await delivery.deliver(row)
    assert result["delivered"] == 4 and result["failed"] == 0
    assert len(projection.ids) == 4
    assert (await delivery.deliver(row))["delivered"] == 0
    # A synthetic, local contract artifact for the browser harness, never PII.
    from pathlib import Path
    Path("/tmp/intra-gd-contract.json").write_text(json.dumps({"recruiter": session, "candidate": own_view, "report": report}, indent=2))
