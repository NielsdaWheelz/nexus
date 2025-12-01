"""Semantic search routes for document chunks (PR 6.3).

This module provides:
- POST /search/chunks: Similarity search over document content chunks

All endpoints require authentication via Clerk JWT.

Spec reference:
- PR 6.3 specification (embeddings and search)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.auth.deps import rate_limit_authenticated
from app.core.ids import from_api_id, to_api_id
from app.db.session import get_session as _get_session
from app.models.user import User
from app.schemas.common import DataEnvelope
from app.schemas.search import ChunkSearchHit, ChunkSearchRequest, ChunkSearchResponse
from app.services.search import search_document_chunks_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post(
    "/chunks",
    response_model=DataEnvelope[ChunkSearchResponse],
    status_code=200,
    summary="Search document chunks",
    description="Search document content chunks by semantic similarity.",
)
def search_chunks(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    request: Annotated[ChunkSearchRequest, Body(...)],
) -> DataEnvelope[ChunkSearchResponse]:
    """Search for content chunks similar to the query.

    Performs semantic similarity search over document content chunks using pgvector.
    Results are restricted to documents owned by the authenticated user (ACL).

    Request body:
        query: Search query (required, 1-2000 chars)
        limit: Max results (optional, 1-100, default 20)
        document_ids: Optional list of document IDs to restrict search

    Returns:
        List of matching chunks with similarity scores, sorted by similarity (highest first)

    Args:
        current_user: Authenticated user (rate limited, used for ACL)
        session: Database session
        request: ChunkSearchRequest with query and optional filters

    Returns:
        DataEnvelope[ChunkSearchResponse] with search results

    Raises:
        ValidationAppError (422): If query validation fails
        ExternalDependencyError (503): If embedding query fails (OpenAI API error)
    """
    # Parse document_ids from typed IDs (doc_<uuid>) to raw UUIDs
    document_ids = None
    if request.document_ids:
        from app.core.errors import ValidationAppError

        parsed_ids = []
        for doc_id in request.document_ids:
            try:
                obj_type, uuid_val = from_api_id(doc_id)
            except ValueError as e:
                raise ValidationAppError(
                    message=f"Invalid document ID format: {str(e)}",
                    details={"field": "document_ids"},
                )

            # Validate that it's actually a document ID
            if obj_type != "document":
                raise ValidationAppError(
                    message=f"Expected document ID, got {obj_type} ID: {doc_id}",
                    details={"field": "document_ids", "expected_type": "document"},
                )

            parsed_ids.append(uuid_val)

        document_ids = parsed_ids

    # Perform search
    hits = search_document_chunks_for_user(
        session=session,
        user=current_user,
        query=request.query,
        limit=request.limit,
        document_ids=document_ids,
    )

    # Convert SearchHit to ChunkSearchHit with typed IDs
    items = [
        ChunkSearchHit(
            chunk_id=to_api_id("chunk", hit.chunk_id),
            document_id=to_api_id("document", hit.document_id),
            score=hit.score,
            text=hit.text,
            text_start=hit.text_start,
            text_end=hit.text_end,
        )
        for hit in hits
    ]

    response = ChunkSearchResponse(
        items=items,
        next_cursor=None,  # Pagination not implemented yet
        has_more=False,  # No pagination
    )

    return DataEnvelope(data=response)
