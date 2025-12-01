"""Document processing Celery tasks.

This module implements Celery tasks for document ingestion, chunking, and embedding:
- ingest_document: Extract canonical text from uploaded documents
- chunk_document: Split canonical text into content chunks
- embed_document: Generate vector embeddings for chunks (PR 6.3)

Core business logic is in app.services for testability.

Spec reference:
- spec/ingestion.md (ingestion pipeline, job specifications)
- spec/jobs.md (Celery configuration, idempotency, retries)
"""

import logging
from uuid import UUID

from app.celery_app import celery_app
from app.core.errors import ExternalDependencyError
from app.db.session import get_sync_session_maker
from app.services.chunking import run_chunk_document
from app.services.embeddings import run_embed_document
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

        # Wire embedding task in pipeline: chunk → embed
        if chunks_created > 0:
            embed_document.delay(document_id)
            logger.info(f"Enqueued embedding task for document {document_id}")

        return {
            "document_id": document_id,
            "chunks_created": chunks_created,
        }


@celery_app.task(
    queue="embeddings",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute
    autoretry_for=(ExternalDependencyError,),
    retry_backoff=True,  # Use exponential backoff: 1m, 2m, 4m
)
def embed_document(self, document_id: str) -> dict:
    """Celery task: Embed all content chunks for a document (PR 6.3).

    This is a thin wrapper that:
    1. Opens a database session
    2. Calls run_embed_document with the session
    3. Returns the result

    The actual business logic is in run_embed_document.

    Retries automatically on ExternalDependencyError (OpenAI API errors).
    Domain validation errors (bad status, no chunks, etc.) fail immediately.

    Args:
        document_id: Document UUID (as string)

    Returns:
        Dict with result metadata (document_id, total_chunks, newly_embedded_chunks)

    Raises:
        ExternalDependencyError: On OpenAI API failure (triggers Celery retry)
        ValidationAppError: On domain validation failure (no retry)
    """
    session_maker = get_sync_session_maker()
    with session_maker() as session:
        doc_uuid = UUID(document_id)
        result = run_embed_document(session, doc_uuid)

        logger.info(
            f"Embedded document {document_id}: "
            f"{result.newly_embedded_chunks}/{result.total_chunks} chunks newly embedded",
            extra={
                "document_id": document_id,
                "newly_embedded": result.newly_embedded_chunks,
                "total_chunks": result.total_chunks,
            },
        )

        return {
            "document_id": document_id,
            "total_chunks": result.total_chunks,
            "newly_embedded_chunks": result.newly_embedded_chunks,
        }
