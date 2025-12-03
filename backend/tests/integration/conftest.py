"""Integration test fixtures and helpers.

Provides fixtures for integration tests that require real Celery workers,
Redis, and database connections.
"""

import time
from typing import Any, Generator

import pytest
from celery.result import AsyncResult
from redis import Redis
from sqlalchemy.orm import Session

from app.models.user import User

# Import from the celery_config module
from tests.celery_config import celery_app_real, redis_test  # noqa: F401


@pytest.fixture
def celery_integration_app(celery_app_real):
    """Alias for celery_app_real for integration tests."""
    return celery_app_real


@pytest.fixture
def redis_integration(redis_test):
    """Alias for redis_test for integration tests."""
    return redis_test


def wait_for_task(task_id: str, timeout: int = 30) -> Any:
    """Poll result backend until task completes.

    Args:
        task_id: Celery task ID to wait for
        timeout: Maximum seconds to wait

    Returns:
        Task result if successful

    Raises:
        Exception: If task failed with error
        TimeoutError: If task didn't complete within timeout
    """
    result = AsyncResult(task_id)
    start = time.time()
    while time.time() - start < timeout:
        if result.ready():
            if result.successful():
                return result.result
            else:
                raise Exception(f"Task {task_id} failed: {result.info}")
        time.sleep(0.1)
    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")


@pytest.fixture
def wait_for_task_fixture():
    """Provide wait_for_task helper as a fixture."""
    return wait_for_task


@pytest.fixture
def clear_queues(redis_integration):
    """Clear Celery queues before and after test.

    Ensures test isolation by removing any pending tasks.
    """
    for queue in ["documents", "embeddings"]:
        redis_integration.delete(queue)
    yield
    for queue in ["documents", "embeddings"]:
        redis_integration.delete(queue)


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user for integration tests.

    Note: This uses the standard db_session fixture which has transaction
    rollback. For integration tests that need persisted data visible to
    workers, use committed_db_session instead.
    """
    user = User(
        id=None,
        external_user_id="integration_test_user",
        email="integration@example.com",
    )
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)
    return user


@pytest.fixture
def committed_db_session(test_engine) -> Generator[Session, None, None]:
    """Provide a database session that commits changes (visible to workers).

    Unlike the standard db_session fixture which rolls back all changes,
    this fixture commits changes so they are visible to Celery workers
    running in separate processes.

    WARNING: Use sparingly. Changes persist after the test and must be
    cleaned up manually or via test isolation strategies.

    Yields:
        Session that commits changes
    """
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def integration_test_user(committed_db_session: Session) -> User:
    """Create a test user visible to workers.

    Uses committed_db_session so the user is visible to Celery workers.
    """
    import uuid

    user = User(
        id=uuid.uuid4(),
        external_user_id=f"integration_test_{uuid.uuid4().hex[:8]}",
        email=f"integration_{uuid.uuid4().hex[:8]}@example.com",
    )
    committed_db_session.add(user)
    committed_db_session.commit()
    committed_db_session.refresh(user)
    return user

