"""Deferred task publishing with after-commit guarantee.

This module provides utilities for publishing Celery tasks only after
the database transaction commits successfully. This prevents the
"publish-before-commit" race condition where a worker picks up a task
before the data it references is visible.

Usage:
    from app.core.deferred_tasks import defer_task

    def my_service(session: Session, ...):
        # Do database work
        doc.status = "ready"
        session.flush()

        # Schedule task to run AFTER commit
        defer_task(session, chunk_document, str(doc.id))

        # Task is published when session commits (not here)

The task will NOT be published if:
- The transaction rolls back (exception raised)
- The session is closed without committing

This provides at-most-once delivery semantics. For at-least-once,
use the transactional outbox pattern instead.
"""

import logging
from typing import Any, Callable

from sqlalchemy import event
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Type alias for Celery task callable
CeleryTask = Callable[..., Any]


def defer_task(session: Session, task: CeleryTask, *args: Any, **kwargs: Any) -> None:
    """Register a Celery task to be published after session commits.

    The task will only be published if the transaction commits successfully.
    If the transaction rolls back, the task is silently discarded.

    Multiple tasks can be deferred on the same session; they will all be
    published in order after commit.

    Args:
        session: SQLAlchemy Session (must not be committed yet)
        task: Celery task object (e.g., chunk_document)
        *args: Positional arguments to pass to task.delay()
        **kwargs: Keyword arguments to pass to task.delay()

    Example:
        defer_task(session, ingest_document, str(doc.id))
        defer_task(session, notify_user, user_id=user.id, message="Done")
    """
    # Initialize deferred tasks list on first use
    if not hasattr(session, "_deferred_tasks"):
        session._deferred_tasks = []
        _register_after_commit_hook(session)

    session._deferred_tasks.append((task, args, kwargs))
    logger.debug(
        f"Deferred task {task.name} with args={args}, kwargs={kwargs} "
        f"(total deferred: {len(session._deferred_tasks)})"
    )


def _register_after_commit_hook(session: Session) -> None:
    """Register the after_commit event listener on a session.

    This is called once per session, on the first defer_task() call.
    The listener fires after successful commit and publishes all deferred tasks.
    """

    @event.listens_for(session, "after_commit")
    def _publish_deferred_tasks(session: Session) -> None:
        """Publish all deferred tasks after commit."""
        tasks = getattr(session, "_deferred_tasks", [])
        if not tasks:
            return

        logger.info(f"Publishing {len(tasks)} deferred task(s) after commit")

        for task, args, kwargs in tasks:
            try:
                task.delay(*args, **kwargs)
                logger.debug(f"Published deferred task {task.name}")
            except Exception as e:
                # Log but don't raise - we're past the point of no return
                # The commit already happened, so we can't roll back
                logger.error(
                    f"Failed to publish deferred task {task.name}: {e}",
                    exc_info=True,
                )

        # Clear the list (session might be reused in some edge cases)
        session._deferred_tasks = []

    @event.listens_for(session, "after_rollback")
    def _discard_deferred_tasks(session: Session) -> None:
        """Discard deferred tasks on rollback."""
        tasks = getattr(session, "_deferred_tasks", [])
        if tasks:
            logger.debug(f"Discarding {len(tasks)} deferred task(s) due to rollback")
            session._deferred_tasks = []


def flush_deferred_tasks(session: Session) -> list[tuple[CeleryTask, tuple, dict]]:
    """Manually flush deferred tasks (for testing).

    This simulates what happens on commit - it publishes all deferred tasks
    and clears the list. Use this in tests where you can't commit (rollback
    isolation) but need to verify tasks would be published.

    Args:
        session: SQLAlchemy Session with deferred tasks

    Returns:
        List of (task, args, kwargs) tuples that were published

    Example (in tests):
        run_ingest_document(session, doc_id)
        tasks = flush_deferred_tasks(session)
        assert len(tasks) == 1
        assert tasks[0][0] == chunk_document
    """
    tasks = getattr(session, "_deferred_tasks", [])
    published = []

    for task, args, kwargs in tasks:
        try:
            task.delay(*args, **kwargs)
            published.append((task, args, kwargs))
            logger.debug(f"Flushed deferred task {task.name}")
        except Exception as e:
            logger.error(f"Failed to flush deferred task {task.name}: {e}")

    session._deferred_tasks = []
    return published


def get_deferred_tasks(session: Session) -> list[tuple[CeleryTask, tuple, dict]]:
    """Get pending deferred tasks without publishing them (for testing).

    This allows tests to inspect what tasks would be published without
    actually calling .delay().

    Args:
        session: SQLAlchemy Session with deferred tasks

    Returns:
        List of (task, args, kwargs) tuples that are pending

    Example (in tests with mocked tasks):
        run_ingest_document(session, doc_id)
        tasks = get_deferred_tasks(session)
        assert len(tasks) == 1
        assert tasks[0][0] == chunk_document
        assert tasks[0][1] == (str(doc_id),)
    """
    return list(getattr(session, "_deferred_tasks", []))

