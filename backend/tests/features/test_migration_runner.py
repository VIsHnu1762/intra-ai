from pathlib import Path
from uuid import uuid4

import pytest

from app.feature_runtime.migrations import MigrationError, run_migrations, transaction_body


def test_outer_transaction_does_not_strip_plpgsql_blocks():
    sql = "-- deployment\nBEGIN;\nDO $$\nBEGIN\nPERFORM 1;\nEND $$;\nCOMMIT;\n-- finished\n"
    assert "DO $$\nBEGIN\nPERFORM 1;\nEND $$;" in transaction_body(sql)
    with pytest.raises(MigrationError):
        transaction_body("BEGIN;\nSELECT 1;\nCOMMIT;\nBEGIN;\nSELECT 2;\nCOMMIT;")


def test_migration_ledger_atomicity_replay_and_checksum(feature_database, tmp_path):
    import psycopg
    table = "migration_probe_" + uuid4().hex
    good = tmp_path / "20990909_01_probe.sql"
    bad = tmp_path / "20990909_02_failure.sql"
    original = f"BEGIN;\nCREATE TABLE public.{table}(id integer PRIMARY KEY);\nCOMMIT;"
    good.write_text(original)
    with psycopg.connect(feature_database, autocommit=True) as conn:
        try:
            assert run_migrations(conn, [good])[0]["status"] == "pending"
            assert conn.execute("SELECT to_regclass(%s)", ("public." + table,)).fetchone()[0] is None
            assert run_migrations(conn, [good], apply=True)[0]["status"] == "applied"
            assert run_migrations(conn, [good], apply=True)[0]["status"] == "already_applied"
            bad.write_text(f"BEGIN;\nCREATE TABLE public.{table}_rollback(id integer);\nSELECT 1/0;\nCOMMIT;")
            with pytest.raises(psycopg.errors.DivisionByZero):
                run_migrations(conn, [good, bad], apply=True)
            assert conn.execute("SELECT to_regclass(%s)", ("public." + table + "_rollback",)).fetchone()[0] is None
            assert conn.execute("SELECT count(*) FROM intra_migrations.applied WHERE filename=%s", (bad.name,)).fetchone()[0] == 0
            good.write_text(original + "\n-- changed after deployment\n")
            with pytest.raises(MigrationError, match="checksum changed"):
                run_migrations(conn, [good, bad], apply=True)
        finally:
            conn.execute(f"DROP TABLE IF EXISTS public.{table}")
            conn.execute("DELETE FROM intra_migrations.applied WHERE filename=ANY(%s)", ([good.name, bad.name],))


def test_all_checked_in_migrations_have_supported_transaction_boundaries():
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    paths = list(migrations.glob("*.sql"))
    assert paths, "The migration-file check must inspect real migration files"
    for path in paths:
        assert transaction_body(path.read_text()).strip(), path.name
