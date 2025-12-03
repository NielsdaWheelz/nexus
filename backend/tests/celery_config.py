"""Celery test configuration fixtures.

Provides two modes of Celery execution for tests:
1. Eager mode (unit tests): Tasks execute synchronously in the same process
2. Real mode (integration tests): Tasks execute via actual workers and Redis

Usage:
- Unit tests: Use celery_app_eager fixture (or rely on autouse fixture)
- Integration tests: Use celery_app_real fixture with @pytest.mark.integration
"""

import os

import pytest
from redis import Redis

from app.celery_app import celery_app


@pytest.fixture
def celery_app_eager():
    """Sync execution for unit tests.

    Configures Celery to execute tasks immediately in the same process.
    Exceptions propagate directly to the test for easy debugging.

    Yields:
        Celery app configured for eager execution

    Example:
        def test_my_task(celery_app_eager):
            result = my_task("arg")  # Executes synchronously
            assert result == expected
    """
    app = celery_app
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    yield app
    app.conf.task_always_eager = False
    app.conf.task_eager_propagates = False


@pytest.fixture
def celery_app_real():
    """Real async execution with test Redis.

    Requires:
    - REDIS_URL environment variable set to test Redis
    - Test Redis server running (e.g., via docker compose --profile test)
    - Test Celery worker running

    Skips test if Redis is not available.

    Yields:
        Celery app configured for real async execution

    Example:
        @pytest.mark.integration
        def test_full_pipeline(celery_app_real):
            result = my_task.delay("arg")
            wait_for_task(result.id)
    """
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL not set - skipping integration test")

    try:
        client = Redis.from_url(redis_url)
        client.ping()
        client.close()
    except Exception as e:
        pytest.skip(f"Cannot connect to test Redis: {e}")

    app = celery_app
    original_broker = app.conf.broker_url
    original_backend = app.conf.result_backend
    original_eager = app.conf.task_always_eager

    app.conf.broker_url = redis_url
    app.conf.result_backend = redis_url
    app.conf.task_always_eager = False

    yield app

    # Restore original config
    app.conf.broker_url = original_broker
    app.conf.result_backend = original_backend
    app.conf.task_always_eager = original_eager


@pytest.fixture
def redis_test():
    """Redis client for test inspection.

    Provides a Redis client connected to the test Redis instance.
    Flushes the database after test completion to ensure isolation.

    Skips if REDIS_URL is not set.

    Yields:
        Redis client with decode_responses=True
    """
    url = os.getenv("REDIS_URL")
    if not url:
        pytest.skip("REDIS_URL not set")

    client = Redis.from_url(url, decode_responses=True)
    yield client
    client.flushdb()
    client.close()

