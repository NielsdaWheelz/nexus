"""Document embedding service for PR 6.3.

Implements the core embedding pipeline for content chunks:
- run_embed_document: Generate and store embeddings for document chunks
- Idempotent semantics with status tracking
- Integration with OpenAI embeddings API
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationAppError
from app.models.chunk import ContentChunk
from app.models.document import Document
from app.services.chunking import CHUNK_VERSION_DOCUMENT
from app.services.openai_embeddings import EmbeddingClient, embed_texts_with_default_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingResult:
    """Result of embedding a document.

    Fields:
    - document_id: UUID of the embedded document
    - total_chunks: Total number of content chunks for this document
    - newly_embedded_chunks: Number of chunks newly embedded in this call
    """

    document_id: UUID
    total_chunks: int
    newly_embedded_chunks: int


def run_embed_document(
    session: Session,
    document_id: UUID,
    embedding_client: EmbeddingClient | None = None,
) -> EmbeddingResult:
    """Embed all content chunks for a document.

    Idempotent: Running with same model and chunks produces no changes on second run.
    Enforces strict preconditions on document status and chunk_version.

    Args:
        session: SQLAlchemy session (required for transaction management)
        document_id: UUID of document to embed
        embedding_client: Optional embedding client. If not provided, uses default.

    Returns:
        EmbeddingResult with counts

    Raises:
        NotFoundError: Document not found
        ValidationAppError: Document status is not "ready", or chunks don't match expected version,
                          or no chunks found, or too many chunks
        ExternalDependencyError: OpenAI API error (propagated for Celery retry)
    """
    settings = get_settings()
    embedding_model = settings.EMBEDDING_MODEL_DOCUMENT
    batch_size = settings.EMBEDDING_BATCH_SIZE
    max_chunks = settings.EMBEDDING_MAX_CHUNKS_PER_DOC

    if embedding_client is None:
        embedding_client_instance = embed_texts_with_default_client
    else:
        embedding_client_instance = embedding_client

    # 1. Load document with pessimistic lock
    doc = session.execute(
        select(Document).where(Document.id == document_id).with_for_update()
    ).scalar_one_or_none()

    if not doc:
        raise NotFoundError(
            message=f"Document not found: {document_id}",
            details={"document_id": str(document_id)},
        )

    # 2. Status guards
    if doc.status != "ready":
        raise ValidationAppError(
            message=f"Cannot embed document: status is {doc.status}, expected ready",
            details={"document_id": str(document_id), "status": doc.status},
        )

    if doc.chunk_version != CHUNK_VERSION_DOCUMENT:
        raise ValidationAppError(
            message=f"Cannot embed document: chunk_version mismatch (expected {CHUNK_VERSION_DOCUMENT}, got {doc.chunk_version}). Run rechunking first.",
            details={
                "document_id": str(document_id),
                "expected_chunk_version": CHUNK_VERSION_DOCUMENT,
                "current_chunk_version": doc.chunk_version,
            },
        )

    # 3. Find all relevant chunks
    all_chunks = (
        session.execute(
            select(ContentChunk)
            .where(
                (ContentChunk.media_type == "document")
                & (ContentChunk.media_id == document_id)
                & (ContentChunk.chunk_version == CHUNK_VERSION_DOCUMENT)
            )
            .order_by(ContentChunk.text_start)
        )
        .scalars()
        .all()
    )

    if not all_chunks:
        raise ValidationAppError(
            message="No content chunks found for document. Run chunking first.",
            details={"document_id": str(document_id)},
        )

    # 4. Safety guard: too many chunks
    if len(all_chunks) > max_chunks:
        raise ValidationAppError(
            message=f"Document has too many chunks ({len(all_chunks)} > {max_chunks}). Cannot embed.",
            details={
                "document_id": str(document_id),
                "chunk_count": len(all_chunks),
                "max_allowed": max_chunks,
            },
        )

    # 5. Partition chunks into already_embedded and to_embed
    already_embedded = [
        chunk
        for chunk in all_chunks
        if chunk.embedding is not None and chunk.embedding_model == embedding_model
    ]
    to_embed = [
        chunk
        for chunk in all_chunks
        if chunk.embedding is None or chunk.embedding_model != embedding_model
    ]

    # 6. Idempotency check
    if doc.embedding_status == "ready" and doc.embedding_model == embedding_model and not to_embed:
        logger.info(
            f"Document {document_id} already fully embedded with {embedding_model}. No-op.",
            extra={"document_id": str(document_id), "model": embedding_model},
        )
        return EmbeddingResult(
            document_id=document_id,
            total_chunks=len(all_chunks),
            newly_embedded_chunks=0,
        )

    # Note: We don't set embedding_status to "processing" because the check constraint
    # only allows ('pending', 'ready', 'failed'). The pessimistic lock (SELECT FOR UPDATE)
    # prevents concurrent embedding attempts. Status goes directly: pending -> ready/failed.

    logger.info(
        f"Starting embedding for document {document_id} with {len(to_embed)} chunks to embed",
        extra={
            "document_id": str(document_id),
            "chunks_to_embed": len(to_embed),
            "model": embedding_model,
        },
    )

    # 8. Batch embedding
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i : i + batch_size]
        texts = [chunk.text for chunk in batch]

        # Call embedding client (may raise ExternalDependencyError for Celery retry)
        embeddings = embed_texts_with_default_client(texts, embedding_model)

        # Verify order is preserved (openai.embeddings.create preserves order)
        if len(embeddings) != len(batch):
            raise ValueError(
                f"Embedding client returned {len(embeddings)} embeddings "
                f"but batch had {len(batch)} texts"
            )

        # Store embeddings
        for chunk, embedding_vec in zip(batch, embeddings):
            chunk.embedding = embedding_vec
            chunk.embedding_model = embedding_model

        session.flush()
        logger.debug(
            f"Embedded batch of {len(batch)} chunks",
            extra={"document_id": str(document_id), "batch_size": len(batch)},
        )

    # 9. Final status update
    doc.embedding_status = "ready"
    doc.embedding_model = embedding_model
    session.flush()

    logger.info(
        f"Finished embedding document {document_id}",
        extra={
            "document_id": str(document_id),
            "newly_embedded": len(to_embed),
            "total_chunks": len(all_chunks),
        },
    )

    return EmbeddingResult(
        document_id=document_id,
        total_chunks=len(all_chunks),
        newly_embedded_chunks=len(to_embed),
    )
