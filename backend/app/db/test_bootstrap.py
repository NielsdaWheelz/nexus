"""Test database bootstrap and schema migration.

This module ensures that the test database exists and is migrated to Alembic head
before any DB-backed tests run. Called once per test session via pytest_sessionstart.

Responsibilities:
- Read DATABASE_URL from config (set by conftest.py for tests)
- Idempotently create test database if it doesn't exist (using psycopg directly)
- Run Alembic programmatically to migrate test DB to head
- Handle connection errors with clear, actionable messages

Note: We use psycopg directly for CREATE DATABASE (not SQLAlchemy) because
PostgreSQL requires this operation to run outside any transaction block, and
SQLAlchemy's connection model wraps operations in transactions even with
isolation_level="AUTOCOMMIT". For a simple, explicit, reliable "create DB if
missing" operation, psycopg with autocommit=True is the correct tool.
"""

from sqlalchemy import make_url

from app.core.config import get_settings


def _ensure_test_database_exists(db_url: str) -> None:
    """Idempotently ensure test database exists.

    Connects to the Postgres server using psycopg directly with autocommit=True,
    checks if the test database exists, and creates it if needed.

    Raises RuntimeError if:
    - DATABASE_URL is not set
    - Cannot connect to Postgres server
    - Database creation fails
    """
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set. For tests, conftest.py should set this "
            "before importing app modules."
        )

    url = make_url(db_url)
    db_name = url.database
    if not db_name:
        raise RuntimeError(f"DATABASE_URL must include a database name. Got: {db_url}")

    # Construct admin connection URL (same server, but connect to 'postgres' database)
    admin_url = url.set(database="postgres")

    try:
        import psycopg

        # Connect to server's admin database with autocommit=True.
        # Build DSN string from URL components (psycopg expects DSN format, not SQLAlchemy URL format).
        # Never log this string as it contains credentials.
        dsn = (
            f"postgresql://{admin_url.username}:{admin_url.password}@"
            f"{admin_url.host}:{admin_url.port}/{admin_url.database}"
        )
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Check if database already exists
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (db_name,),
                )
                exists = cur.fetchone() is not None

                if not exists:
                    # Create database with quoted name to handle special characters
                    cur.execute(f'CREATE DATABASE "{db_name}"')

        print(f"✓ Test database {db_name} is ready")

    except Exception as e:
        error_str = str(e).lower()
        if "refused" in error_str or "could not connect" in error_str:
            raise RuntimeError(
                f"Could not connect to Postgres at {url.host}:{url.port}. "
                "Is PostgreSQL running? You can start it with:\n"
                "  docker compose -f infra/docker-compose.yml --profile test up -d"
            ) from e
        raise RuntimeError(f"Failed to create test database: {e}") from e


def _run_alembic_upgrade(db_url: str) -> None:
    """Run Alembic upgrade head programmatically.

    Migrates the test database to the latest schema version using Alembic's
    Python API directly instead of subprocess.

    Raises RuntimeError if migration fails.
    """
    try:
        from pathlib import Path

        from alembic.config import Config

        from alembic import command

        # Find alembic.ini relative to this file (app/db/test_bootstrap.py)
        # Go up two levels: app/db -> app -> backend
        backend_dir = Path(__file__).parent.parent.parent
        alembic_ini = backend_dir / "alembic.ini"

        if not alembic_ini.exists():
            raise RuntimeError(f"alembic.ini not found at {alembic_ini}")

        cfg = Config(str(alembic_ini))
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")

        print("✓ Test database migrated to head")

    except Exception as e:
        raise RuntimeError(f"Alembic upgrade failed: {e}") from e


def ensure_test_database_and_schema() -> None:
    """Idempotently ensure test database exists and is migrated to head.

    This function is called once per test session (via pytest_sessionstart)
    to set up the test database and schema.

    Steps:
    1. Read DATABASE_URL from config (set by conftest.py for tests)
    2. Ensure test database exists (create if needed)
    3. Run Alembic upgrade to migrate test DB to head

    Raises RuntimeError with clear, actionable messages if:
    - DATABASE_URL is not set
    - Postgres is not running / unreachable
    - Migrations fail
    """
    settings = get_settings()
    db_url = settings.DATABASE_URL

    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set. For tests, conftest.py should set this "
            "via os.environ before importing app modules."
        )

    print("\n" + "=" * 70)
    print("TEST DATABASE BOOTSTRAP")
    print("=" * 70)

    _ensure_test_database_exists(db_url)
    _run_alembic_upgrade(db_url)

    print("=" * 70 + "\n")
