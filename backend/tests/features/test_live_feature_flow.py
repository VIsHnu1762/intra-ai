"""Opt-in synthetic flows against AICredits, Supabase Storage and AuraDB.

Application rows use the real isolated PostgreSQL/PostgREST fixture. This is
deliberately not described as hosted Supabase schema deployment verification.
"""
import asyncio
import os
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import psycopg
import pytest
from supabase import create_client

from app.core.config import settings
from app.candidate_onboarding.service import OnboardingService
from app.group_discussion.evidence_delivery import GDEvidenceDelivery
from app.group_discussion.models import AcceptInvite, DiscussionMessage, GDConfiguration, GDControl, InviteInput, SessionCreate
from app.group_discussion.service import GDService
from app.integrations.aicredits_client import AICreditsClient
from app.knowledge_graph.assessment_projection import AssessmentEvidenceProjection
from app.role_play.evidence_delivery import RolePlayEvidenceDelivery
from app.role_play.models import ControlInput, TurnInput
from test_onboarding import docx, upload
from test_role_play import setup_session

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE_FEATURE_TESTS") != "1",
                              reason="Opt-in live services; uses synthetic content and cleans its own objects")


@pytest.mark.asyncio
async def test_live_resume_parser_and_private_supabase_storage(feature_sb, feature_actors):
    _, candidate, _ = feature_actors
    hosted = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    sb = SimpleNamespace(table=feature_sb.table, rpc=feature_sb.rpc, storage=hosted.storage)
    svc = OnboardingService(sb)
    content = docx("Synthetic candidate profile. Five years of Python, FastAPI and PostgreSQL development. "
                   "Built a support dashboard and tested API request validation. Bachelor of Computer Science.")
    try:
        first = await svc.upload(candidate, upload(content), 0, str(uuid4()))
        assert first.parse_source == "aicredits", "Live parsing must not be counted as verified via a fallback"
        assert first.profile.skills
        assert (await svc.status(candidate)).current.id == first.id
        assert (await svc.download(candidate, first.id))[0] == content
        bucket = await asyncio.to_thread(hosted.storage.get_bucket, settings.SUPABASE_STORAGE_BUCKET)
        assert bucket.public is False
    finally:
        versions = await svc.repo.versions(candidate.user_id)
        keys = [version["storage_key"] for version in versions]
        if keys:
            await asyncio.to_thread(hosted.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove, keys)


@pytest.mark.asyncio
async def test_live_roleplay_gd_evidence_reports_and_aura_projection(feature_sb, feature_database, feature_actors):
    recruiter, candidate, peer = feature_actors
    client = AICreditsClient()
    svc, row = await setup_session(feature_sb, feature_database, feature_actors, client)
    keys = [row["id"]]
    projection = AssessmentEvidenceProjection.from_settings()
    try:
        await asyncio.to_thread(projection.initialize)
        view = await svc.control(candidate, row["id"], ControlInput(request_id=uuid4(), expected_revision=0, action="start"))
        responses = [
            "I understand that the delay is frustrating. I will check the warehouse schedule and confirm a realistic delivery time with you today.",
            "I will send you the confirmed delivery window and call tomorrow to check whether that plan meets your needs.",
            "If the proposed window is inconvenient, I will ask which alternative works and confirm what the warehouse can provide before promising it.",
            "I will document the agreed next step, name its owner, and check the result with you tomorrow. I will not promise an unverified delivery date.",
        ]
        for text in responses:
            if view["status"] != "active":
                break
            view = await svc.turn(candidate, row["id"], TurnInput(request_id=uuid4(), expected_revision=view["revision"], text=text))
        if view["status"] == "active":
            view = await svc.control(candidate, row["id"], ControlInput(request_id=uuid4(), expected_revision=view["revision"], action="finish"))
        report = await svc.generate_report(candidate, row["id"])
        assert 1 <= report["candidate_rating"] <= 5 and report["evaluated_turns"] >= 2
        assert "evidence" not in report
        delivered = await RolePlayEvidenceDelivery(svc.repo, projection).deliver(row)
        assert delivered["pending"] == 0 and delivered["delivered"] >= 2

        app = feature_sb.table("applications").select("job_id").eq("candidate_id", candidate.candidate_id).limit(1).execute().data[0]
        with psycopg.connect(feature_database, autocommit=True) as conn:
            conn.execute("INSERT INTO applications(id,job_id,candidate_id) VALUES(%s,%s,%s)", (str(uuid4()), app["job_id"], peer.candidate_id))
        gd = GDService(feature_sb, client=client)
        session = await gd.create(recruiter, SessionCreate(request_id=uuid4(), configuration=GDConfiguration(
            title="Synthetic pilot discussion", topic="How should a small team prioritize a customer pilot with limited budget?",
            competencies=["communication", "argument_quality"])))
        key = session["id"]
        keys.append(key)
        for member in (candidate, peer):
            invite = await gd.invite(recruiter, key, InviteInput(candidate_id=member.candidate_id, request_id=uuid4()))
            token = parse_qs(urlparse(invite["join_url"]).fragment)["token"][0]
            await gd.accept(member, key, AcceptInvite(token=token, request_id=uuid4()))
        view = await gd.view(recruiter, key)
        view = await gd.control(recruiter, key, GDControl(action="start", expected_revision=view["revision"], request_id=uuid4()))
        contributions = [
            (candidate, "I propose a small pilot with ten customers before committing the entire budget. We should measure completion and support costs first."),
            (peer, "I agree with testing a pilot, but ten customers may miss important use cases. I suggest selecting customers from two different segments."),
            (candidate, "That is a useful concern. I would split the pilot across those two segments and agree a success threshold before reviewing the result."),
            (peer, "I would track completion separately for each segment and review the results with the team next Friday before deciding whether to expand."),
        ]
        for member, text in contributions:
            await gd.message(member, key, DiscussionMessage(text=text, request_id=uuid4()))
        view = await gd.view(recruiter, key)
        await gd.control(recruiter, key, GDControl(action="finish", expected_revision=view["revision"], request_id=uuid4()))
        participants = await gd.repo.participants(key)
        for member in (candidate, peer):
            participant = next(p for p in participants if str(p["candidate_id"]) == member.candidate_id)
            report = await gd.generate_report(member, key, participant["id"])
            assert 1 <= report["candidate_rating"] <= 5 and report["evaluated_turns"] == 2
            assert "evidence" not in report
        session = await gd.repo.session(key)
        delivery = await GDEvidenceDelivery(gd.repo, projection).deliver(session)
        assert delivery["delivered"] == 4 and delivery["pending"] == 0
        assert (await GDEvidenceDelivery(gd.repo, projection).deliver(session))["delivered"] == 0
        memory = await asyncio.to_thread(projection.candidate_memory, candidate_id=candidate.candidate_id,
            owner_id=recruiter.user_id, tenant_key=row["tenant_key"], limit=20)
        assert {entry["source_type"] for entry in memory} == {"role_play", "group_discussion"}
        assert all(entry["candidate_id"] == candidate.candidate_id for entry in memory)
        assert await asyncio.to_thread(projection.candidate_memory, candidate_id=candidate.candidate_id,
            owner_id="unrelated-owner", tenant_key=row["tenant_key"] ) == []
    finally:
        # Only the randomly generated synthetic sessions/candidates from this fixture.
        for label, field in [("AssessmentEvidence", "session_id"), ("AssessmentEvent", "session_id"), ("AssessmentSession", "session_id")]:
            await asyncio.to_thread(projection._execute_write,
                f"MATCH (n:{label}) WHERE n.{field} IN $keys DETACH DELETE n", {"keys": keys})
        await asyncio.to_thread(projection._execute_write,
            "MATCH (c:Candidate) WHERE c.candidate_id IN $ids DETACH DELETE c",
            {"ids": [candidate.candidate_id, peer.candidate_id]})
        await asyncio.to_thread(projection.close)
