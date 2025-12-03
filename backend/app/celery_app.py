"""Celery application factory and configuration.

This module initializes the Celery app for background job processing.
Redis is configured as both the broker and result backend.

The Celery app is configured with named queues for different job types:
- documents: Document ingestion and processing
- embeddings: Embedding generation and management

This module must be importable without importing the FastAPI app.
"""

from celery import Celery
from kombu import Queue

from app.core.config import get_settings

settings = get_settings()

# Create Celery app instance
celery_app = Celery("nexus")

# Configure broker and result backend
celery_app.conf.broker_url = settings.REDIS_URL
celery_app.conf.result_backend = settings.REDIS_URL

# Configure default queue
celery_app.conf.task_default_queue = "documents"

# Configure named queues
celery_app.conf.task_queues = (
    Queue("documents", routing_key="documents"),
    Queue("embeddings", routing_key="embeddings"),
)

# Additional Celery configuration for production readiness
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
)

# Future tuning notes:
# - For fire-and-forget ingestion/embedding tasks, consider task_ignore_result=True
#   to avoid accumulating junk results in Redis (PR 6.1+)
# - Per-queue overrides: as tasks get heavier, configure task_time_limit per queue
#   via CELERY_TASK_TIME_LIMITS={queue_name: seconds}
# - Reliability: when adding mission-critical tasks, enable:
#   - acks_late=True (acknowledge after task completes)
#   - task_reject_on_worker_lost=True (requeue if worker dies)

# Autodiscover tasks from app package (searches for app.tasks module)
celery_app.autodiscover_tasks(["app"])
