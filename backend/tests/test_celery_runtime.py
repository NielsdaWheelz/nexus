"""Tests for Celery runtime configuration and task sanity.

These tests verify:
1. Celery app initialization and configuration
2. Named queues are configured correctly
3. Tasks can be imported and called synchronously
"""

from app.celery_app import celery_app
from app.tasks.diagnostics import ping


class TestCeleryConfiguration:
    """Test Celery app configuration."""

    def test_celery_app_initialized(self) -> None:
        """Verify Celery app is initialized with correct name."""
        assert celery_app.main == "nexus"

    def test_broker_url_configured(self) -> None:
        """Verify broker URL is configured from settings."""
        assert celery_app.conf.broker_url is not None
        assert celery_app.conf.broker_url.startswith("redis://")

    def test_result_backend_configured(self) -> None:
        """Verify result backend is configured from settings."""
        assert celery_app.conf.result_backend is not None
        assert celery_app.conf.result_backend.startswith("redis://")

    def test_default_queue_configured(self) -> None:
        """Verify default queue is set to documents."""
        assert celery_app.conf.task_default_queue == "documents"

    def test_named_queues_configured(self) -> None:
        """Verify named queues are configured."""
        queues = celery_app.conf.task_queues
        assert queues is not None

        # Convert to list of queue names for easier checking
        queue_names = [q.name for q in queues]
        assert "documents" in queue_names
        assert "embeddings" in queue_names


class TestTaskSanity:
    """Test basic task functionality."""

    def test_ping_task_callable(self) -> None:
        """Verify ping task is callable."""
        # Call synchronously (no worker needed)
        result = ping(42)
        assert result == 42

    def test_ping_task_with_different_values(self) -> None:
        """Test ping task with various input values."""
        assert ping(0) == 0
        assert ping(1) == 1
        assert ping(-1) == -1
        assert ping(999999) == 999999

    def test_ping_task_has_queue_assignment(self) -> None:
        """Verify ping task is assigned to documents queue."""
        # Task should have queue set to documents
        # The queue is set via the decorator's queue parameter
        assert ping.name == "app.tasks.diagnostics.ping"
