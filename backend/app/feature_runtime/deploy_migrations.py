"""Safe feature migration entry point with environment guards.

Default behavior:
- run only feature migrations from 20260909_*.sql
- perform host/suffix guard for hosted DBs
- reject Supabase transaction pooler port 6543 unless explicitly opted in
- verify expected host tables before applying
- dry-run by default
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

from app.core.config import settings
from app.feature_runtime.migrations import MigrationError, run_migrations


CORE_TABLES = [
    "jobs",
    "candidates",
    "applications",
    "interviews",
    "scheduled_interviews",
]


def _feature_paths(include_legacy: bool) -> Iterable[Path]:
    migration_dir = Path(__file__).resolve().parents[2] / "migrations"
    for path in migration_dir.glob("*.sql"):
        if include_legacy:
            yield path
        elif path.name.startswith("20260909_"):
            yield path


def _get_dsn() -> str:
    configured = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
    dsn = configured.get_secret_value() if hasattr(configured, "get_secret_value") else str(configured or "")
    if not dsn:
        raise MigrationError("DATABASE_URL is not configured")
    return dsn


def _validate_destination(dsn: str, *, allow_non_matching_host: bool = False) -> None:
    parsed = urlparse(dsn)
    if not parsed.scheme.startswith("postgres"):
        raise MigrationError("Only PostgreSQL DSNs are supported for migrations")

    if parsed.port == 6543:
        raise MigrationError("Refusing migration against Supavisor transaction pooler (port 6543)")

    if allow_non_matching_host:
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1", "postgres", "host.docker.internal"}:
            raise MigrationError("--local-test only permits a local PostgreSQL destination")
        return

    configured = str(settings.SUPABASE_URL or "").strip()
    if not configured:
        raise MigrationError("SUPABASE_URL is required to identify the migration destination")

    supabase_host = urlparse(configured).hostname
    if not supabase_host or not parsed.hostname:
        raise MigrationError("A valid Supabase project and database hostname are required")
    project = supabase_host.removesuffix(".supabase.co")
    direct = supabase_host.endswith(".supabase.co") and parsed.hostname == "db." + supabase_host
    session_pool = (parsed.hostname.endswith(".pooler.supabase.com")
                    and unquote(parsed.username or "") == "postgres." + project)
    if not (direct or session_pool) or (parsed.port or 5432) != 5432:
        raise MigrationError(
            "DATABASE_URL must identify this Supabase project's direct or session-pooler connection. "
            "Use --local-test only for a local development database."
        )


def _assert_core_schema(conn) -> None:
    present = {
        name: conn.execute(
            "SELECT to_regclass(%s) IS NOT NULL",
            (f"public.{name}",),
        ).fetchone()[0]
        for name in CORE_TABLES
    }
    missing = [name for name, ok in present.items() if not ok]
    if missing:
        raise MigrationError("Expected existing core schema before feature migrations: " + ", ".join(missing))


def _read_optional_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply feature migrations with production-safe guards")
    parser.add_argument("--apply", action="store_true", help="Apply pending migrations to target DB")
    parser.add_argument("--include-legacy", action="store_true", help="Include legacy pre-20260909 migrations")
    parser.add_argument(
        "--local-test",
        action="store_true",
        help="Allow running against a local or non-matching host for local/dev databases",
    )
    return parser.parse_args()


def run_feature_migrations(*, apply: bool, include_legacy: bool, local_test: bool) -> None:
    try:
        import psycopg
    except Exception as exc:
        raise MigrationError("Install requirements-migrations.txt before running migrations") from exc

    dsn = _get_dsn()
    _validate_destination(dsn, allow_non_matching_host=local_test)

    paths = list(_feature_paths(include_legacy))
    if not paths:
        raise MigrationError("No migration files selected")

    connection_options = {} if local_test else {"sslmode": "require"}
    with psycopg.connect(dsn, autocommit=True, connect_timeout=10, **connection_options) as conn:
        _assert_core_schema(conn)
        # A prior full deployment may have ledger entries for legacy migrations.
        # Supply those files for checksum validation without selecting new legacy DDL.
        if not include_legacy and conn.execute("SELECT to_regclass('intra_migrations.applied') IS NOT NULL").fetchone()[0]:
            applied = {row[0] for row in conn.execute("SELECT filename FROM intra_migrations.applied").fetchall()}
            selected = {path.name for path in paths}
            paths.extend(path for path in _feature_paths(True) if path.name in applied and path.name not in selected)
        for row in run_migrations(conn, paths, apply=apply):
            print(f"{row['status']}: {row['filename']}")


def main() -> None:
    args = _read_optional_args()
    try:
        run_feature_migrations(
            apply=args.apply,
            include_legacy=args.include_legacy,
            local_test=args.local_test,
        )
    except MigrationError as exc:
        raise SystemExit(f"Migration failed: {exc}") from exc
    except Exception as exc:
        raise SystemExit(f"Migration failed ({type(exc).__name__}); no credentials are logged.") from None


if __name__ == "__main__":
    main()
