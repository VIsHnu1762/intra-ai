"""Recovery and integration gaps that need real transactional verification."""
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from app.candidate_onboarding.repository import OnboardingRepository
from app.feature_runtime.deploy_migrations import _validate_destination
from app.feature_runtime.migrations import MigrationError
from app.integrations.feature_db import rpc
from app.role_play.models import ControlInput, TurnInput
from app.role_play.service import RolePlayService
from app.voice.context import authorized_context
from app.voice.models import DashboardContext
from test_role_play import RolePlayLLM, setup_session


@pytest.mark.asyncio
async def test_taylor_reuses_current_onboarding_profile_without_changing_application_cv(feature_sb, feature_database, feature_actors):
    _, candidate, peer = feature_actors
    repo = OnboardingRepository(feature_sb)
    for revision, skill in enumerate(["Python", "TypeScript"]):
        await repo.save(candidate, {
            "id": str(uuid4()), "filename": "profile.docx", "extension": "docx",
            "storage_key": "synthetic/" + uuid4().hex, "content_sha256": str(revision) * 64,
            "request_id": str(uuid4()), "raw_text": "Synthetic candidate resume for context integration tests.",
            "profile": {"skills": [skill]}, "parse_source": "aicredits",
        }, revision)
    context = await authorized_context(candidate, DashboardContext(), feature_sb, "taylor")
    assert context["cv_claims_not_verified_evidence"]["skills"] == ["TypeScript"]
    assert context["cv_provenance"]["version"] == 2
    from app.candidate_onboarding.context import practice_profile
    assert await practice_profile(peer, feature_sb) is None
    await setup_session(feature_sb, feature_database, feature_actors)
    application = feature_sb.table("applications").select("id").eq("candidate_id", candidate.candidate_id).limit(1).execute().data[0]
    context = await authorized_context(candidate, DashboardContext(application_id=application["id"]), feature_sb, "taylor")
    assert "cv_provenance" not in context
    assert context.get("cv_claims_not_verified_evidence", {}).get("skills") != ["TypeScript"]


@pytest.mark.asyncio
async def test_roleplay_policy_snapshot_survives_restart_and_report(feature_sb, feature_database, feature_actors):
    from test_company_intelligence import context as policy_fixture
    recruiter, candidate, _ = feature_actors
    llm = RolePlayLLM()
    svc, row = await setup_session(feature_sb, feature_database, feature_actors, llm)
    snapshot = row["scenario_snapshot"]
    snapshot["definition"]["policy_query"] = "pilot approval"
    feature_sb.table("roleplay_sessions").update({"scenario_snapshot": snapshot}).eq("id", row["id"]).execute()
    class Policy:
        calls = 0
        async def enrich(self, owner, tenant, query):
            assert owner == recruiter.user_id and query == "pilot approval"
            self.calls += 1
            assert self.calls == 1, "Pinned policy must not refresh after a restart"
            return policy_fixture()
    policy = Policy()
    svc.policy_enricher = policy
    await svc.control(candidate, row["id"], ControlInput(request_id=uuid4(), expected_revision=0, action="start"))
    view = await svc.turn(candidate, row["id"], TurnInput(request_id=uuid4(), expected_revision=1,
        text="I will explain the options and confirm the proposed next step with you."))
    recovered = RolePlayService(feature_sb, client=llm, policy_enricher=policy)
    view = await recovered.turn(candidate, row["id"], TurnInput(request_id=uuid4(), expected_revision=2,
        text="I will document our agreement and contact you tomorrow to confirm the result."))
    assert view["status"] == "completed" and policy.calls == 1
    reports = await recovered.generate_report(candidate, row["id"])
    assert reports["policy_contexts"][0]["excerpts"][0]["version_id"] == "version-2"
    assert reports["total_turns"] == 2 and reports["unevaluated_turns"] == 0
    analyses = [json.loads(messages[-1]["content"]) for _, messages in llm.calls
                if "Evaluate the candidate's behavior" in messages[0]["content"]]
    assert len(analyses) == 2
    assert all(value["authorized_policy_context"]["status"] == "available" for value in analyses)
    assert all("Speak as the simulated persona" not in messages[0]["content"] for _, messages in llm.calls)
    assert "UNREVEALED" not in json.dumps(view)


@pytest.mark.asyncio
async def test_expiry_is_atomic_idempotent_and_preserves_evidence(feature_sb, feature_database, feature_actors):
    from app.group_discussion.models import GDConfiguration, SessionCreate
    from app.group_discussion.service import GDService
    recruiter, candidate, _ = feature_actors
    svc, row = await setup_session(feature_sb, feature_database, feature_actors)
    await svc.control(candidate, row["id"], ControlInput(request_id=uuid4(), expected_revision=0, action="start"))
    await svc.turn(candidate, row["id"], TurnInput(request_id=uuid4(), expected_revision=1,
        text="I will check the delivery problem and propose a clear next step."))
    gd = await GDService(feature_sb).create(recruiter, SessionCreate(request_id=uuid4(), configuration=GDConfiguration(
        title="Timeout discussion", topic="How should a small team prioritize customer feedback?")))
    with psycopg.connect(feature_database, autocommit=True) as conn:
        conn.execute("UPDATE roleplay_sessions SET state=jsonb_set(state,'{started_at}',to_jsonb(now()-interval '2 hours')) WHERE id=%s", (row["id"],))
        conn.execute("UPDATE gd_sessions SET status='active',started_at=now()-interval '2 hours' WHERE id=%s", (gd["id"],))
    for function, table, key, kind in [("expire_roleplay_sessions", "roleplay_events", row["id"], "finish"),
                                        ("expire_gd_sessions", "gd_events", gd["id"], "expired")]:
        await asyncio.gather(*(rpc(feature_sb, function, p_limit=100) for _ in range(2)))
        assert await rpc(feature_sb, function, p_limit=100) == 0
        events = feature_sb.table(table).select("*").eq("session_id", key).eq("kind", kind).execute().data
        assert len(events) == 1 and events[0]["action"]["action"] in {"END_SCENARIO", "END_DISCUSSION"}
        assert events[0]["evidence"] == []
    final = await svc.repo.session(row["id"])
    assert final["status"] == "completed" and final["state"]["completion_reason"] == "time_limit"
    assert final["revision"] == 3
    assert len([e for e in await svc.repo.events(row["id"]) if e["evidence"]]) == 1
    with psycopg.connect(feature_database, autocommit=True) as conn:
        for function in ("expire_roleplay_sessions", "expire_gd_sessions"):
            for role in ("anon", "authenticated"):
                assert conn.execute("SELECT has_function_privilege(%s,%s,'execute')", (role, f"public.{function}(integer)")).fetchone()[0] is False


def test_supabase_destination_guard_accepts_direct_and_matching_session_pooler(monkeypatch):
    import app.feature_runtime.deploy_migrations as module
    monkeypatch.setattr(module, "settings", SimpleNamespace(SUPABASE_URL="https://abcdefghijklmnopqrst.supabase.co"))
    _validate_destination("postgresql://postgres:synthetic@db.abcdefghijklmnopqrst.supabase.co:5432/postgres")
    _validate_destination("postgresql://postgres.abcdefghijklmnopqrst:synthetic@aws-0-ap-south-1.pooler.supabase.com:5432/postgres")
    _validate_destination("postgresql://postgres:synthetic@localhost:5432/postgres", allow_non_matching_host=True)
    for dsn in ["postgresql://postgres.otherproject:synthetic@aws-0-ap-south-1.pooler.supabase.com:5432/postgres",
                "postgresql://postgres:synthetic@db.abcdefghijklmnopqrst.supabase.co:6543/postgres",
                "postgresql://postgres:synthetic@localhost:5432/postgres",
                "postgresql://postgres:synthetic@db.anotherproject.supabase.co:5432/postgres"]:
        with pytest.raises(MigrationError):
            _validate_destination(dsn)
    with pytest.raises(MigrationError):
        _validate_destination("postgresql://postgres:synthetic@external.example:5432/postgres", allow_non_matching_host=True)
