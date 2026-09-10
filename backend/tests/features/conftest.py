"""Real isolated PostgreSQL + PostgREST. Storage is explicitly an in-memory fake."""
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from urllib.parse import urlsplit

import httpx
import pytest
import psycopg
from jose import jwt
from postgrest import SyncPostgrestClient


class MemoryStorage:
    def __init__(self): self.objects = {}
    def from_(self, _bucket): return self
    def upload(self, key, data, file_options=None): self.objects[key] = data
    def download(self, key): return self.objects[key]
    def remove(self, keys):
        for key in keys: self.objects.pop(key, None)


@pytest.fixture(scope="session")
def feature_database():
    if os.getenv("RUN_FEATURE_DB_TESTS") != "1":
        pytest.skip("Set RUN_FEATURE_DB_TESTS=1 for isolated PostgreSQL/PostgREST integration")
    from psycopg import sql
    name = "intra_feature_test_" + uuid4().hex
    base = os.getenv("FEATURE_TEST_POSTGRES", "postgresql://postgres:postgres@127.0.0.1:5432/postgres")
    admin = psycopg.connect(base, autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = base.rsplit("/", 1)[0] + "/" + name
    root = Path(__file__).resolve().parents[2]
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute((root.parent / "docker/init-db/01-init.sql").read_text())
            for migration in sorted((root / "migrations").glob("*.sql")):
                connection.execute(migration.read_text())
            # Repeat migrations to catch non-idempotent DDL before API testing.
            for migration in sorted((root / "migrations").glob("20260909*.sql")):
                connection.execute(migration.read_text())
        yield dsn
    finally:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.close()


@pytest.fixture(scope="session")
def feature_sb(feature_database):
    name = feature_database.rsplit("/", 1)[1]
    container = name + "_rest"
    secret = "intra-feature-test-only-secret-32-chars!"
    pg_port = urlsplit(feature_database).port or 5432
    subprocess.run(["docker", "run", "--rm", "-d", "--name", container,
        "-p", "127.0.0.1::3000", "-e", f"PGRST_DB_URI=postgres://authenticator:postgres@host.docker.internal:{pg_port}/{name}",
        "-e", "PGRST_DB_SCHEMAS=public", "-e", "PGRST_DB_ANON_ROLE=anon", "-e", f"PGRST_JWT_SECRET={secret}",
        "postgrest/postgrest:v12.2.0"], check=True, capture_output=True, timeout=30)
    try:
        port = subprocess.check_output(["docker", "port", container, "3000/tcp"], text=True, timeout=10).strip().rsplit(":", 1)[1]
        url = "http://127.0.0.1:" + port
        for _ in range(100):
            try:
                if httpx.get(url, timeout=1).status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(.1)
        else: pytest.fail("Isolated PostgREST did not become ready")
        token = jwt.encode({"role": "service_role", "exp": int(time.time()) + 3600}, secret)
        client = SyncPostgrestClient(url, headers={"Authorization": "Bearer " + token})
        yield SimpleNamespace(table=client.from_, rpc=client.rpc, storage=MemoryStorage(),
                              rest_url=url, service_token=token)
        client.session.close()
    finally:
        subprocess.run(["docker", "stop", container], check=False, capture_output=True, timeout=20)


@pytest.fixture
def feature_actors(feature_database):
    from app.voice.authorization import Actor
    key = uuid4().hex
    recruiter = Actor("r-" + key, "recruiter", key + "@hr.test", "Recruiter")
    candidate = Actor("u-" + key, "candidate", key + "@candidate.test", "Candidate", candidate_id="c-" + key)
    peer = Actor("p-" + key, "candidate", key + "@peer.test", "Peer", candidate_id="pc-" + key)
    with psycopg.connect(feature_database, autocommit=True) as conn:
        for actor in [recruiter, candidate, peer]:
            conn.execute("INSERT INTO users(id,email,name,role,password_hash) VALUES(%s,%s,%s,%s,'test')", (actor.user_id, actor.email, actor.name, actor.role))
            if actor.candidate_id:
                conn.execute("INSERT INTO candidates(id,email,name) VALUES(%s,%s,%s)", (actor.candidate_id, actor.email, actor.name))
    return recruiter, candidate, peer
