"""Diagnostic tasks for system health checks and testing.

This module contains utility tasks used to verify that the Celery worker
and broker are functioning correctly.
"""

from app.celery_app import celery_app


@celery_app.task(queue="documents")
def ping(x: int) -> int:
    """Simple ping task for testing worker connectivity.

    Args:
        x: An integer value to echo back.

    Returns:
        The same integer value that was passed in.

    Example:
        >>> from app.tasks.diagnostics import ping
        >>> result = ping.delay(42)
        >>> result.get()  # In async context with worker running
        42
    """
    return x
