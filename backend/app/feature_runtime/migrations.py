"""Checksum-verified, transactional migration runner. Planning is read-only.

Usage: python -m app.feature_runtime.migrations [--apply]
Uses DATABASE_URL from the environment or the existing application settings.
Never accepts a password in command-line arguments or logs a connection URL.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re


class MigrationError(RuntimeError):
    pass


def transaction_body(sql):
    """Remove a file's outer transaction, not PL/pgSQL BEGIN/END blocks."""
    comments = r"(?:(?:\s+)|(?:--[^\n]*(?:\n|$))|(?:/\*[\s\S]*?\*/))*"
    wrapped = re.fullmatch(comments + r"BEGIN\s*;(?P<body>[\s\S]*?)COMMIT\s*;" + comments, sql, re.IGNORECASE)
    body = wrapped.group("body") if wrapped else sql
    if re.search(r"(?im)^\s*(?:BEGIN|COMMIT|ROLLBACK)\s*;", body):
        raise MigrationError("Unsupported transaction control; migrations need one outer transaction or none")
    return body


def run_migrations(conn, paths, *, apply=False):
    if not conn.autocommit:
        raise MigrationError("Migration connection must use autocommit with explicit per-file transactions")
    scripts = []
    for path in sorted(paths, key=lambda value: value.name):
        if not re.fullmatch(r"[0-9]{8}_[A-Za-z0-9_]+\.sql", path.name):
            raise MigrationError(f"Invalid migration filename: {path.name}")
        raw = path.read_bytes()
        scripts.append((path.name, hashlib.sha256(raw).hexdigest(), transaction_body(raw.decode("utf-8"))))
    if len({name for name, _, _ in scripts}) != len(scripts):
        raise MigrationError("Migration filenames must be unique")
    locked = False
    try:
        if apply:
            locked = conn.execute("SELECT pg_try_advisory_lock(hashtext('intra-ai-migrations'))").fetchone()[0]
            if not locked:
                raise MigrationError("Another migration runner holds the deployment lock")
            with conn.transaction():
                conn.execute("CREATE SCHEMA IF NOT EXISTS intra_migrations")
                conn.execute("REVOKE ALL ON SCHEMA intra_migrations FROM PUBLIC")
                conn.execute("""CREATE TABLE IF NOT EXISTS intra_migrations.applied (
                    filename text PRIMARY KEY,
                    sha256 text NOT NULL CHECK (length(sha256)=64),
                    applied_at timestamptz NOT NULL DEFAULT now()
                )""")
                conn.execute("REVOKE ALL ON intra_migrations.applied FROM PUBLIC")
        exists = conn.execute("SELECT to_regclass('intra_migrations.applied') IS NOT NULL").fetchone()[0]
        applied = dict(conn.execute("SELECT filename,sha256 FROM intra_migrations.applied").fetchall()) if exists else {}
        names = {name for name, _, _ in scripts}
        missing = set(applied) - names
        if missing:
            raise MigrationError("Applied migrations missing from checkout: " + ", ".join(sorted(missing)))
        for name, checksum, _ in scripts:
            if name in applied and applied[name] != checksum:
                raise MigrationError(f"Applied migration checksum changed: {name}")
        result = []
        for name, checksum, sql in scripts:
            status = "already_applied" if name in applied else "pending"
            if apply and status == "pending":
                with conn.transaction():
                    conn.execute("SET LOCAL lock_timeout='5s'")
                    conn.execute("SET LOCAL statement_timeout='120s'")
                    conn.execute(sql, prepare=False)
                    conn.execute("INSERT INTO intra_migrations.applied(filename,sha256) VALUES (%s,%s)", (name, checksum))
                status = "applied"
            result.append({"filename": name, "status": status})
        if apply:
            conn.execute("NOTIFY pgrst,'reload schema'")
        return result
    finally:
        if locked:
            conn.execute("SELECT pg_advisory_unlock(hashtext('intra-ai-migrations'))")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply pending migrations to the configured database")
    args = parser.parse_args()
    try:
        import psycopg
    except ImportError:
        parser.exit(2, "Install requirements-migrations.txt before running migrations.\n")
    from app.core.config import settings
    configured = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    dsn = configured.get_secret_value() if hasattr(configured, "get_secret_value") else str(configured or "")
    if not dsn:
        parser.exit(2, "DATABASE_URL is not configured.\n")
    paths = (Path(__file__).resolve().parents[2] / "migrations").glob("*.sql")
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as conn:
            for item in run_migrations(conn, paths, apply=args.apply):
                print(f"{item['status']}: {item['filename']}")
    except MigrationError as exc:
        parser.exit(2, str(exc) + "\n")
    except Exception as exc:
        parser.exit(2, f"Migration failed ({type(exc).__name__}, SQLSTATE {getattr(exc, 'sqlstate', None) or 'unavailable'}). No credentials are logged.\n")


if __name__ == "__main__":
    main()
