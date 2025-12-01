"""Document processing Celery tasks.

This module implements Celery tasks for document ingestion:
- ingest_document: Thin wrapper that opens a session and calls run_ingest_document

Core business logic is in app.services.ingestion.run_ingest_document for testability.

Spec reference:
- spec/ingestion.md (ingestion pipeline, job specifications)
- spec/jobs.md (Celery configuration, idempotency, retries)
"""

import logging
from uuid import UUID

from app.celery_app import celery_app
from app.db.session import get_sync_session_maker
from app.services.chunking import run_chunk_document
from app.services.ingestion import run_ingest_document

logger = logging.getLogger(__name__)


@celery_app.task(
    queue="documents",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute
    autoretry_for=(Exception,),
    retry_backoff=True,  # Use exponential backoff: 1m, 2m, 4m
)
def ingest_document(self, document_id: str) -> dict:
    """Celery task: Ingest a document by ID.

    This is a thin wrapper that:
    1. Opens a database session
    2. Calls run_ingest_document with the session
    3. Returns the result

    The actual business logic is in run_ingest_document.

    Args:
        document_id: Document UUID (as string)

    Returns:
        Dict with status and result metadata

    Raises:
        Exception: On failure (triggers Celery retry)
    """
    session_maker = get_sync_session_maker()
    with session_maker() as session:
        return run_ingest_document(session, document_id)


@celery_app.task(
    queue="documents",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute
    autoretry_for=(Exception,),
    retry_backoff=True,  # Use exponential backoff: 1m, 2m, 4m
)
def chunk_document(self, document_id: str) -> dict:
    """Celery task: Chunk a document by ID.

    This is a thin wrapper that:
    1. Opens a database session
    2. Calls run_chunk_document with the session
    3. Returns the result

    The actual business logic is in run_chunk_document.

    Args:
        document_id: Document UUID (as string)

    Returns:
        Dict with status and number of chunks created

    Raises:
        Exception: On failure (triggers Celery retry)
    """
    session_maker = get_sync_session_maker()
    with session_maker() as session:
        doc_uuid = UUID(document_id)
        chunks_created = run_chunk_document(session, doc_uuid)
        logger.info(f"Chunked document {document_id}: {chunks_created} chunks created")
        return {
            "document_id": document_id,
            "chunks_created": chunks_created,
        }
