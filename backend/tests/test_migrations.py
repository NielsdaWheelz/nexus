"""Test Alembic migrations can be applied to a fresh database.

This test verifies that:
- An empty database can be migrated from base to head
- All tables are created correctly via migrations
- Migrations are the canonical source of schema (no create_all() fallback)

This is a smoke test for migration health and catches regressions where migrations
are incomplete or misconfigured.
"""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings


@pytest.fixture(scope="function")
def empty_migration_db() -> str:
    """Create a completely empty test database for migration testing.

    This database has NO tables or schema - migrations must create everything.
    We use a separate database name to avoid conflicts with the main test database.
    """
    settings = get_settings()

    # Use a different database name to avoid conflicts with normal test DB
    migration_db_name = "test_nexus_migrations"

    if not settings.DATABASE_URL_TEST:
        pytest.fail("DATABASE_URL_TEST is not set")

    base_url = settings.DATABASE_URL_TEST.rsplit("/", 1)[0]
    migration_db_url = f"{base_url}/{migration_db_name}"

    # Connect to postgres database to create migration test DB
    postgres_url = f"{base_url}/postgres"
    admin_engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")

    try:
        # Drop if exists, then create fresh
        with admin_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {migration_db_name}"))
            conn.execute(text(f"CREATE DATABASE {migration_db_name}"))

        yield migration_db_url

    finally:
        # Clean up: drop migration test database
        with admin_engine.connect() as conn:
            # Terminate any remaining connections to the test database
            conn.execute(
                text(
                    f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{migration_db_name}' AND pid <> pg_backend_pid()"
                )
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {migration_db_name}"))
        admin_engine.dispose()


def test_migrations_create_all_tables(empty_migration_db: str):
    """Test that running migrations from base to head creates all required tables.

    This verifies:
    - Migrations can run on empty database
    - All expected tables are created
    - No errors occur during migration

    If this test fails, the Alembic migration is broken and must be fixed.
    Do NOT work around this by adding Base.metadata.create_all() anywhere.
    """
    # Run Alembic upgrade head on empty database
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent
    alembic_ini = backend_dir / "alembic.ini"

    if not alembic_ini.exists():
        pytest.fail(f"alembic.ini not found at {alembic_ini}")

    cfg = Config(str(alembic_ini))

    # IMPORTANT: alembic/env.py reads DATABASE_URL_TEST from os.environ,
    # so we must set it there, not just via cfg.set_main_option()
    original_env = os.environ.get("DATABASE_URL_TEST")
    try:
        os.environ["DATABASE_URL_TEST"] = empty_migration_db

        # Run migrations
        command.upgrade(cfg, "head")

    finally:
        # Restore original environment
        if original_env is not None:
            os.environ["DATABASE_URL_TEST"] = original_env
        else:
            os.environ.pop("DATABASE_URL_TEST", None)

    # Verify tables were created
    engine = create_engine(empty_migration_db)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    # Expected tables from our models (core tables that must exist)
    expected_tables = {
        "users",
        "documents",
        "highlights",
        "annotations",
        "readers",
        "conversations",
        "messages",
        "alembic_version",  # Alembic metadata table
    }

    missing_tables = expected_tables - set(tables)

    if missing_tables:
        pytest.fail(
            f"Migration did not create expected tables: {missing_tables}. "
            f"Found tables: {tables}. "
            f"The Alembic migration 1c62073ec151_initial_schema.py is broken. "
            f"Fix the migration - do NOT add create_all() as a workaround."
        )

    # All expected tables exist
    assert set(tables) >= expected_tables

    engine.dispose()


def test_migration_is_idempotent(empty_migration_db: str):
    """Test that running migrations twice produces the same result.

    Verifies migrations are idempotent and don't fail on re-run.
    """
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent
    alembic_ini = backend_dir / "alembic.ini"

    cfg = Config(str(alembic_ini))

    # Set DATABASE_URL_TEST environment variable for alembic/env.py
    original_env = os.environ.get("DATABASE_URL_TEST")
    try:
        os.environ["DATABASE_URL_TEST"] = empty_migration_db

        # Run migrations first time
        command.upgrade(cfg, "head")

        # Run migrations second time (should be no-op)
        command.upgrade(cfg, "head")

    finally:
        # Restore original environment
        if original_env is not None:
            os.environ["DATABASE_URL_TEST"] = original_env
        else:
            os.environ.pop("DATABASE_URL_TEST", None)

    # Verify tables still exist and nothing broke
    engine = create_engine(empty_migration_db)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    # Core tables should still be there
    assert "users" in tables
    assert "documents" in tables
    assert "alembic_version" in tables
    assert len(tables) >= 8  # At least 8 core tables

    engine.dispose()
