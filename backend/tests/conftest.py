"""Pytest configuration and fixtures for test suite.

This module provides:
- Database session fixtures with transaction rollback (test isolation)
- Test client with authenticated user context
- JWT token fixtures for authentication testing
- Proper teardown after each test
- Test database bootstrap via pytest_sessionstart (auto-creates test DB and runs migrations)
"""

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_session as _get_session
from app.db.test_bootstrap import ensure_test_database_and_schema
from app.main import create_app


def pytest_sessionstart(session: pytest.Session) -> None:
    """Pytest hook: Run before any tests.

    Ensures test database exists and is migrated to Alembic head.
    Fails fast with clear error messages if:
    - DATABASE_URL_TEST is not set
    - Postgres is unreachable
    - Migrations fail
    """
    try:
        ensure_test_database_and_schema()
    except RuntimeError as e:
        pytest.exit(f"Test database bootstrap failed: {e}", 1)


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Get test database URL from config.

    DATABASE_URL_TEST is required to run DB-backed tests.
    Must be set via environment variable or .env file before running pytest.

    This fixture assumes ensure_test_database_and_schema() has already run
    via pytest_sessionstart hook, so the test database is ready.
    """
    settings = get_settings()
    test_db_url = settings.DATABASE_URL_TEST

    if not test_db_url:
        raise RuntimeError(
            "DATABASE_URL_TEST is not set. Set it to a Postgres URL "
            "(e.g., postgresql+psycopg://app_user:password@localhost:5432/test_nexus) "
            "before running DB-backed tests."
        )

    return test_db_url


@pytest.fixture(scope="session")
def test_engine(test_db_url: str):
    """Create test database engine.

    This engine is created once per test session and shared across all tests.
    Each test uses transactions that are rolled back for isolation.

    IMPORTANT: Schema is created EXCLUSIVELY by Alembic migrations in pytest_sessionstart.
    Do NOT add Base.metadata.create_all() here - it hides migration bugs and creates
    a false sense of security. If tests fail with "relation does not exist", the
    migration is broken and must be fixed, not worked around with create_all().

    The Alembic migration ff2d3eadcd14_initial_schema.py is fully implemented and
    creates all 16 tables. It runs via ensure_test_database_and_schema() before
    any tests execute.
    """
    engine = create_engine(test_db_url, echo=False)

    # Schema already created by Alembic in pytest_sessionstart - no create_all() needed

    yield engine

    # Teardown: just dispose the engine, do NOT drop tables
    # Why no drop_all()?
    # 1. Each test uses transaction rollback for isolation - no data persists between tests
    # 2. Tables persisting between test runs is fine - Alembic upgrade is idempotent
    # 3. Dropping tables here would break subsequent test runs in CI or local dev
    # 4. If schema needs reset, drop the entire test database and recreate it
    engine.dispose()


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a database session for each test with transaction rollback.

    Simple transaction pattern:
    1. Creates a connection and begins a transaction
    2. Creates a session bound to that connection
    3. Yields the session for use in the test
    4. Rolls back the transaction after the test (cleaning up all changes)

    This pattern ensures:
    - Tests are isolated (changes don't persist between tests)
    - Real database operations are tested (not mocked)
    - Fast test execution (rollback is instant)
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, class_=Session)()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def app(db_session: Session):
    """Create test FastAPI app with test database session.

    Overrides get_session dependency to:
    - Yield the test db_session
    - NOT call commit/rollback/close (handled by test fixture)
    """
    app = create_app()

    # Override the session dependency to use test session
    def override_get_session() -> Generator[Session, None, None]:
        yield db_session
        # Note: No commit/rollback/close here - handled by db_session fixture

    app.dependency_overrides[_get_session] = override_get_session

    yield app

    # Clear dependency overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """Provide FastAPI test client connected to test database."""
    from fastapi.testclient import TestClient

    return TestClient(app)


# ============================================================================
# JWT FIXTURES FOR AUTHENTICATION TESTING
# ============================================================================


@pytest.fixture
def auth_token():
    """Provide a valid JWT token for testing authenticated endpoints.

    Token is for user_test_1.
    Note: Actual JWT verification is mocked in tests that need it.
    """
    return "mock.jwt.token.user1"


@pytest.fixture
def auth_token2():
    """Provide a second valid JWT token for testing (different user).

    Token is for user_test_2.
    Note: Actual JWT verification is mocked in tests that need it.
    """
    return "mock.jwt.token.user2"
