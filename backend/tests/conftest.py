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
    """
    engine = create_engine(test_db_url, echo=False)

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Teardown: drop all tables after all tests
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a database session for each test with transaction rollback.

    This fixture:
    1. Creates a new connection for each test
    2. Begins a transaction
    3. Yields the session for use in the test
    4. Rolls back the transaction after the test (cleaning up all changes)

    This pattern ensures:
    - Tests are isolated (changes don't persist between tests)
    - No need to manually delete test data
    - Real database operations are tested (not mocked)
    - Fast test execution (no fixture cleanup overhead)
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, class_=Session)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def app(db_session: Session):
    """Create test FastAPI app with test database session.

    The app is configured to use the test database session fixture
    instead of the default production session.
    """
    app = create_app()

    # Override the session dependency to use test session
    def override_get_session() -> Session:
        return db_session

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
