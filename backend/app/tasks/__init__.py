"""Background task definitions for Celery.

This package contains all Celery task definitions organized by type:
- diagnostics: Utility tasks for system health checks and testing
- documents: Document ingestion, chunking, and embedding tasks
- remap: Highlight remapping tasks

IMPORTANT: Task modules must be imported here for Celery autodiscover to find them.
When the worker runs `celery -A app.celery_app`, autodiscover imports this __init__.py,
which must in turn import the task modules so @celery_app.task decorators execute.
"""

# Import task modules so their @celery_app.task decorators register with Celery
# Without these imports, autodiscover_tasks() finds an empty package
from app.tasks import diagnostics  # noqa: F401
from app.tasks import documents  # noqa: F401
from app.tasks import remap  # noqa: F401
