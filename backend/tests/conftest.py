"""Pytest configuration and fixtures for test suite.

This module provides:
- Database session fixtures with transaction rollback (test isolation)
- Test client with authenticated user context
- Proper teardown after each test
"""

import os
from typing import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_session as _get_session
from app.db.session import _sync_engine, _sync_session_maker
from app.main import create_app


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Get test database URL.

    Uses a separate test database to avoid interfering with development DB.
    Defaults to test_nexus if DATABASE_URL not explicitly set for testing.
    """
    # Allow override via TEST_DATABASE_URL environment variable
    if os.getenv("TEST_DATABASE_URL"):
        return os.getenv("TEST_DATABASE_URL")

    settings = get_settings()
    db_url = settings.DATABASE_URL

    # Convert to test database
    if "postgresql" in db_url:
        # Change database name to test_nexus
        if "nexus" in db_url:
            return db_url.replace("/nexus", "/test_nexus")
        else:
            return db_url + "_test"

    return db_url


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
    session = sessionmaker(bind=connection)(class_=Session)

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
