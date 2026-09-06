"""Opt-in real PostgreSQL checks in a disposable database, never the app database.

RUN_REPORT_MIGRATION_DB_TESTS=1 PYTHONPATH=. venv/bin/pytest -q tests/test_report_migration_db.py
"""
import json
import os
from pathlib import Path
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_REPORT_MIGRATION_DB_TESTS") != "1", reason="Requires explicit isolated local PostgreSQL test opt-in")


def sql(db, statement, *, check=True):
    result = subprocess.run(["docker", "exec", "-i", "intra_ai_postgres", "psql", "-X", "-U", "postgres", "-d", db,
                             "-At", "-v", "ON_ERROR_STOP=1"], input=statement, text=True, capture_output=True, timeout=20)
    if check:
        assert result.returncode == 0, result.stderr
    return result


@pytest.fixture(scope="module")
def isolated_db():
    name = "intra_report_migration_test_" + uuid4().hex
    sql("postgres", f'CREATE DATABASE "{name}";')
    try:
        sql(name, """CREATE TABLE scheduled_interviews(id text PRIMARY KEY, status text NOT NULL);
        CREATE TABLE reports(id text PRIMARY KEY, interview_id text UNIQUE NOT NULL REFERENCES scheduled_interviews(id),
          round_assessments jsonb, overall_score numeric NOT NULL, recommendation text NOT NULL,
          strengths jsonb, improvements jsonb, salary_recommendation jsonb, proctoring_summary jsonb,
          pdf_url text, created_at timestamptz NOT NULL DEFAULT now());
        ALTER TABLE scheduled_interviews ENABLE ROW LEVEL SECURITY;
        ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
        GRANT USAGE ON SCHEMA public TO service_role;
        GRANT ALL ON scheduled_interviews,reports TO service_role;""")
        migration = (Path(__file__).parents[1] / "migrations/20260906_post_interview_reports.sql").read_text()
        sql(name, migration)
        sql(name, migration)  # additive migration can be reapplied without data rewriting
        yield name
    finally:
        assert name.startswith("intra_report_migration_test_") and len(name) == len("intra_report_migration_test_") + 32
        sql("postgres", f'DROP DATABASE "{name}" WITH (FORCE);')


@pytest.fixture
def db(isolated_db):
    sql(isolated_db, "TRUNCATE reports,scheduled_interviews CASCADE; INSERT INTO scheduled_interviews VALUES('interview','completed');")
    return isolated_db


def literal(value):
    return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"


def claim(db, attempt="first", source=None):
    source_sql = "NULL" if source is None else literal(source)
    return json.loads(sql(db, f"SELECT claim_interview_report('interview','{attempt}',{source_sql});").stdout)


def report(**changes):
    return {"id": "report", "interview_id": "interview", "overall_score": 75, "recommendation": "hire",
            "round_assessments": [], "strengths": ["Clear"], "improvements": ["More evidence"],
            "created_at": "2026-09-06T00:00:00Z", "candidate_rating": 4,
            "candidate_feedback": ["Good overall performance.", "Clear explanation.", "Add specific results."],
            "analysis": {"overall_summary": "Good overall performance."}, **changes}


def finish(db, payload=None, attempt="first", check=True):
    return sql(db, f"SELECT finish_interview_report('interview','{attempt}',{literal(report() if payload is None else payload)});", check=check)


def test_concurrent_claim_single_owner_and_source_freeze(db):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda a: claim(db, a, {"source": a}), ["first", "second"]))
    assert results[0]["attempt_id"] == results[1]["attempt_id"]
    owner = results[0]["attempt_id"]
    assert json.loads(sql(db, "SELECT report_source FROM scheduled_interviews;").stdout) == {"source": owner}
    sql(db, "UPDATE scheduled_interviews SET report_generation=jsonb_set(report_generation,'{started_at}',to_jsonb(now()-interval '6 minutes')); ")
    assert claim(db, "retry", {"source": "changed"})["attempt_id"] == "retry"
    assert json.loads(sql(db, "SELECT report_source FROM scheduled_interviews;").stdout) == {"source": owner}
    stale = finish(db, attempt=owner, check=False)
    assert stale.returncode and "REPORT_ATTEMPT_SUPERSEDED" in stale.stderr
    assert sql(db, "SELECT count(*) FROM reports;").stdout.strip() == "0"


def test_finish_retry_is_immutable_and_clears_draft(db):
    claim(db)
    sql(db, "UPDATE scheduled_interviews SET report_draft='{}';")
    first = json.loads(finish(db).stdout)
    replay = json.loads(finish(db, report(overall_score=0,candidate_rating=1)).stdout)
    assert first == replay
    assert claim(db, "another")["status"] == "ready"
    assert sql(db, "SELECT count(*)=1 FROM reports;").stdout.strip() == "t"
    assert sql(db, "SELECT report_draft IS NULL AND report_generation->>'status'='ready' FROM scheduled_interviews;").stdout.strip() == "t"


@pytest.mark.parametrize("changes", [{"candidate_rating": 3}, {"candidate_feedback": "scalar"},
    {"candidate_feedback": ["a", "b"]}, {"candidate_feedback": ["a", "b", "\n\t"]},
    {"candidate_feedback": ["a", "b", 12]}, {"analysis": None}, {"analysis": {}}, {"analysis": []},
    {"overall_score": 101}, {"interview_id": "another"}])
def test_incomplete_output_never_marks_ready(db, changes):
    claim(db)
    result = finish(db, report(**changes), check=False)
    assert result.returncode and "REPORT_INCOMPLETE" in result.stderr
    assert sql(db, "SELECT count(*) FROM reports;").stdout.strip() == "0"
    assert sql(db, "SELECT report_generation->>'status' FROM scheduled_interviews;").stdout.strip() == "generating"


@pytest.mark.parametrize("feedback,analysis", [(None, None), ("malformed", {}), (["a", "b", "c"], None)])
def test_incomplete_existing_report_is_repaired_without_duplicate_id(db, feedback, analysis):
    sql(db, "INSERT INTO reports(id,interview_id,overall_score,recommendation,candidate_feedback,candidate_rating,analysis)"
            f" VALUES('legacy','interview',75,'hire',{literal(feedback)},4,{literal(analysis)});")
    assert claim(db)["status"] == "generating"
    saved = json.loads(finish(db).stdout)
    assert saved["id"] == "legacy" and saved["candidate_feedback"] == report()["candidate_feedback"]
    assert sql(db, "SELECT count(*) FROM reports;").stdout.strip() == "1"


def test_completed_report_cannot_be_overwritten_by_inflight_worker(db):
    claim(db)
    sql(db, "INSERT INTO reports SELECT * FROM jsonb_populate_record(NULL::reports," + literal(report()) + ");")
    saved = json.loads(finish(db, report(overall_score=0,candidate_rating=1)).stdout)
    assert saved["overall_score"] == 75 and saved["candidate_feedback"] == report()["candidate_feedback"]


def test_claim_null_source_allows_recovery_and_malformed_lease_is_recoverable(db):
    claim(db, source=None)
    sql(db, "UPDATE scheduled_interviews SET report_generation='{" + '"status":"generating","attempt_id":"old","started_at":"malformed"' + "}';")
    assert claim(db, "retry", {"evaluation": {"overall_score": 75}})["status"] == "generating"
    assert json.loads(sql(db, "SELECT report_source FROM scheduled_interviews;").stdout)["evaluation"]["overall_score"] == 75


def test_not_completed_and_rpc_privileges(db):
    sql(db, "UPDATE scheduled_interviews SET status='scheduled';")
    assert claim(db)["status"] == "not_completed"
    privileges = sql(db, "SELECT has_function_privilege('anon','public.claim_interview_report(text,text,jsonb)','EXECUTE'),"
        "has_function_privilege('authenticated','public.finish_interview_report(text,text,jsonb)','EXECUTE'),"
        "has_function_privilege('service_role','public.finish_interview_report(text,text,jsonb)','EXECUTE');")
    assert privileges.stdout.strip() == "f|f|t"
    assert sql(db, "SELECT bool_and(relrowsecurity) FROM pg_class WHERE oid IN ('reports'::regclass,'scheduled_interviews'::regclass);").stdout.strip() == "t"
