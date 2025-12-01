"""Similarity search service for document content chunks (PR 6.3).

Implements semantic search over embedded content chunks using pgvector.
Respects user ACL (only searches user-owned documents).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.chunk import ContentChunk
from app.models.document import Document
from app.models.user import User
from app.services.openai_embeddings import embed_texts_with_default_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchHit:
    """Single search result from similarity search.

    Fields:
    - chunk_id: UUID of the matched chunk
    - document_id: UUID of the parent document
    - score: Similarity score (higher is more similar)
    - text: Chunk text
    - text_start: Byte offset start
    - text_end: Byte offset end
    """

    chunk_id: UUID
    document_id: UUID
    score: float
    text: str
    text_start: int
    text_end: int


def search_document_chunks_for_user(
    session: Session,
    user: User,
    query: str,
    limit: int = 20,
    document_ids: list[UUID] | None = None,
) -> list[SearchHit]:
    """Search content chunks using semantic similarity.

    Performs vector similarity search over embedded content chunks,
    respecting user ACL (only searches user-owned documents).

    Args:
        session: SQLAlchemy session
        user: Authenticated user (used for ACL)
        query: Search query text (≤2000 chars)
        limit: Max results to return (default 20, max 100)
        document_ids: Optional list of document IDs to restrict search

    Returns:
        List of SearchHit objects sorted by similarity (highest first)

    Raises:
        ExternalDependencyError: If embedding query fails (OpenAI API error)
    """
    settings = get_settings()
    embedding_model = settings.EMBEDDING_MODEL_DOCUMENT
    max_limit = 100

    # Cap limit
    if limit > max_limit:
        limit = max_limit

    # Embed query using same model as documents
    query_embeddings = embed_texts_with_default_client([query], embedding_model)
    query_vector = query_embeddings[0]

    # Build query: find similar chunks in user-owned documents
    # Cosine similarity: similarity = 1 - distance
    stmt = (
        select(ContentChunk, Document)
        .join(Document, Document.id == ContentChunk.media_id)
        .where(
            and_(
                Document.user_id == user.id,  # ACL: user-owned documents
                Document.embedding_status == "ready",  # Only search embedded documents
                ContentChunk.embedding.isnot(None),  # Must have embedding
                ContentChunk.embedding_model == embedding_model,  # Same model
                ContentChunk.media_type == "document",  # Content chunks only
            )
        )
    )

    # Optional: restrict to specific documents
    if document_ids:
        stmt = stmt.where(Document.id.in_(document_ids))

    # Execute raw similarity query using pgvector operator
    # Using <-> operator for cosine distance (lower is more similar)
    # We'll order by distance and convert to similarity score
    # Convert query_vector list to pgvector string format [x,y,z...]
    query_vector_str = f"[{','.join(str(v) for v in query_vector)}]"

    results = session.execute(
        text(
            """
            SELECT
                cc.id as chunk_id,
                d.id as document_id,
                (1 - (cc.embedding <-> CAST(:query_vector AS vector))) as score,
                cc.text,
                cc.text_start,
                cc.text_end
            FROM content_chunks cc
            JOIN documents d ON d.id = cc.media_id
            WHERE
                d.user_id = :user_id
                AND d.embedding_status = 'ready'
                AND cc.embedding IS NOT NULL
                AND cc.embedding_model = :model
                AND cc.media_type = 'document'
                AND (:document_ids_filter OR d.id = ANY(:document_ids))
            ORDER BY cc.embedding <-> CAST(:query_vector AS vector)
            LIMIT :limit
            """
        ),
        {
            "query_vector": query_vector_str,
            "user_id": user.id,
            "model": embedding_model,
            "limit": limit,
            "document_ids": document_ids if document_ids else [],
            "document_ids_filter": not document_ids,  # Skip filter if no document_ids
        },
    ).fetchall()

    # Map results to SearchHit objects
    hits = []
    for row in results:
        hit = SearchHit(
            chunk_id=row[0],  # chunk_id
            document_id=row[1],  # document_id
            score=float(row[2]),  # score (1 - distance)
            text=row[3],  # text
            text_start=row[4],  # text_start
            text_end=row[5],  # text_end
        )
        hits.append(hit)

    logger.info(
        f"Search returned {len(hits)} results for user {user.id}",
        extra={
            "user_id": str(user.id),
            "query_length": len(query),
            "result_count": len(hits),
            "document_filter_count": len(document_ids) if document_ids else None,
        },
    )

    return hits
