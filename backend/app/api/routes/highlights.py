"""Highlights API routes for creation and retrieval.

Routes (spec-aligned):
- POST /highlights: Create a new highlight with byte-range anchor
- GET /documents/{document_id}/highlights: List highlights on a document
- GET /users/{user_id}/highlights: List highlights created by a user

All endpoints require authentication via Clerk JWT and rate limiting.

Spec reference:
- PR 5.2 specification (highlights API layer)
- spec/api_contracts.md (typed IDs, pagination, error envelopes)
- spec/anchors.md (anchor validation rules)
- spec/acl.md (visibility and ownership rules)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.auth.deps import rate_limit_authenticated
from app.core.errors import NotFoundError, ValidationAppError
from app.core.ids import from_api_id, to_api_id
from app.core.pagination import PaginationParams
from app.db.session import get_session as _get_session
from app.models.document import Document
from app.models.user import User
from app.schemas.common import DataEnvelope
from app.schemas.highlights import (
    CreateHighlightRequest,
    HighlightItem,
    HighlightListResponse,
)
from app.services.highlights import (
    create_highlight,
    list_highlights_for_document,
)

logger = logging.getLogger(__name__)

# Create base router for /highlights endpoints
router = APIRouter(tags=["highlights"])


@router.post(
    "/highlights",
    response_model=DataEnvelope[HighlightItem],
    status_code=201,
    summary="Create highlight",
    description="Create a new highlight with character-range anchor on media.",
)
async def create_highlight_endpoint(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    request: CreateHighlightRequest,
) -> DataEnvelope[HighlightItem]:
    """Create a highlight with character-range anchor.

    Offset Semantics (v1):
        text_start and text_end are zero-indexed positions into canonical_text
        treated as a sequence of Unicode code points. For practical purposes,
        treat them as Python/JS string indices.

    Accepts:
    - media_type: Type of media ("document" only in v1)
    - media_id: Typed media ID (e.g., doc_<uuid>)
    - anchor_type: Type of anchor ("text" only for html/epub in v1)
    - text_start: Character offset start (>= 0)
    - text_end: Character offset end (> text_start)

    Validates:
    - media_id is a valid typed ID matching media_type
    - Media exists and is owned by current user
    - text_start and text_end are valid (text_start < text_end, within canonical_text)
    - Quote, prefix, suffix can be computed from canonical_text

    Returns typed API response with hl_<uuid> ID and character offsets.

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        request: CreateHighlightRequest with media_type, media_id, anchor_type, offsets

    Returns:
        HighlightItem with typed IDs, offsets, quote, and timestamps

    Raises:
        ValidationAppError (422): If validation fails
            - Invalid media_id format or type mismatch
            - Unsupported media_type or anchor_type
            - text_start >= text_end or text_start < 0
            - text_end > canonical_text length
        NotFoundError (404): If media doesn't exist or is not owned by user
    """
    # v1: Only support document media type
    if request.media_type != "document":
        raise ValidationAppError(
            message=f"Unsupported media_type: '{request.media_type}'. Only 'document' is supported in v1.",
            details={"field": "media_type", "value": request.media_type, "supported": ["document"]},
        )

    # v1: Only support text anchor type for documents
    if request.anchor_type != "text":
        raise ValidationAppError(
            message=f"Unsupported anchor_type: '{request.anchor_type}'. Only 'text' is supported for documents in v1.",
            details={"field": "anchor_type", "value": request.anchor_type, "supported": ["text"]},
        )

    # Parse and validate media_id
    try:
        id_type, doc_uuid = from_api_id(request.media_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid media_id format: {str(e)}",
            details={"field": "media_id", "reason": str(e)},
        )

    # Validate ID type matches media_type
    if id_type != "document":
        raise ValidationAppError(
            message=f"Invalid media_id type: expected 'document' for media_type='document', got '{id_type}'",
            details={"field": "media_id", "expected_type": "document", "got_type": id_type},
        )

    # Verify document exists and is owned by user
    doc = (
        session.query(Document)
        .filter(
            Document.id == doc_uuid,
            Document.user_id == current_user.id,
            Document.deleted_at.is_(None),
        )
        .first()
    )
    if not doc:
        raise NotFoundError(
            message="Document not found",
            details={"resource_type": "document"},
        )

    # Get canonical text (using codepoint/string semantics, not bytes)
    canonical_text = doc.canonical_text
    text_length = len(canonical_text)

    # Validate character range
    if request.text_start < 0:
        raise ValidationAppError(
            message="text_start must be non-negative",
            details={"field": "text_start", "value": request.text_start},
        )

    if request.text_end <= request.text_start:
        raise ValidationAppError(
            message="text_end must be greater than text_start",
            details={
                "field": "text_end",
                "value": request.text_end,
                "text_start": request.text_start,
            },
        )

    if request.text_end > text_length:
        raise ValidationAppError(
            message=f"text_end ({request.text_end}) exceeds canonical_text length ({text_length})",
            details={
                "field": "text_end",
                "value": request.text_end,
                "text_length": text_length,
            },
        )

    # Extract quote, prefix, suffix from canonical text (using string slicing)
    quote = canonical_text[request.text_start : request.text_end]

    # Prefix: up to 64 characters before start
    prefix_start = max(0, request.text_start - 64)
    prefix = canonical_text[prefix_start : request.text_start]

    # Suffix: up to 64 characters after end
    suffix_end = min(text_length, request.text_end + 64)
    suffix = canonical_text[request.text_end : suffix_end]

    # Create highlight via service layer
    highlight_summary = create_highlight(
        session=session,
        user=current_user,
        media_type=request.media_type,
        media_id=doc.id,
        anchor_type=request.anchor_type,
        text_start=request.text_start,
        text_end=request.text_end,
        quote=quote,
        prefix=prefix,
        suffix=suffix,
    )

    # Convert to API response (with typed IDs and quote)
    return DataEnvelope(
        data=HighlightItem(
            id=to_api_id("highlight", highlight_summary.id),
            document_id=to_api_id("document", highlight_summary.media_id),
            text_start=highlight_summary.text_start,
            text_end=highlight_summary.text_end,
            quote=highlight_summary.quote,
            created_at=highlight_summary.created_at,
            updated_at=highlight_summary.updated_at,
        )
    )


@router.get(
    "/documents/{document_id}/highlights",
    response_model=DataEnvelope[HighlightListResponse],
    status_code=200,
    summary="List highlights for document",
    description="List all highlights on a specific document owned by current user.",
)
async def list_document_highlights(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    document_id: str = Path(..., description="Typed document ID (doc_<uuid>)"),
    limit: int = Query(default=20, ge=1, le=100, description="Results per page"),
    cursor: str | None = Query(None, description="Pagination cursor from previous response"),
) -> DataEnvelope[HighlightListResponse]:
    """List highlights for a document with cursor pagination.

    Enforces:
    - Document must exist and be owned by current user
    - Only highlights owned by current user are returned
    - Results ordered by creation date (newest first)

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        document_id: Typed document ID (doc_<uuid>)
        limit: Number of results per page (1-100, default 20)
        cursor: Opaque cursor from previous next_cursor response

    Returns:
        HighlightListResponse with paginated highlights

    Raises:
        ValidationAppError (422): If document_id format is invalid
        NotFoundError (404): If document doesn't exist or is not owned by user
    """
    # Parse and validate document_id
    try:
        doc_type, doc_uuid = from_api_id(document_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid document_id format: {str(e)}",
            details={"field": "document_id", "reason": str(e)},
        )

    if doc_type != "document":
        raise ValidationAppError(
            message=f"Invalid document_id type: expected 'document', got '{doc_type}'",
            details={"field": "document_id", "expected_type": "document", "got_type": doc_type},
        )

    # Verify document exists and is owned by user
    doc = (
        session.query(Document)
        .filter(
            Document.id == doc_uuid,
            Document.user_id == current_user.id,
            Document.deleted_at.is_(None),
        )
        .first()
    )
    if not doc:
        raise NotFoundError(
            message="Document not found",
            details={"resource_type": "document"},
        )

    # List highlights using service layer
    paginated = list_highlights_for_document(
        session=session,
        user=current_user,
        document_id=doc_uuid,
        pagination=PaginationParams(limit=limit, cursor=cursor),
    )

    # Convert to API response (with typed IDs and quote)
    return DataEnvelope(
        data=HighlightListResponse(
            items=[
                HighlightItem(
                    id=to_api_id("highlight", hl.id),
                    document_id=to_api_id("document", hl.media_id),
                    text_start=hl.text_start,
                    text_end=hl.text_end,
                    quote=hl.quote,
                    created_at=hl.created_at,
                    updated_at=hl.updated_at,
                )
                for hl in paginated.items
            ],
            next_cursor=paginated.next_cursor,
            has_more=paginated.has_more,
        )
    )


@router.get(
    "/users/{user_id}/highlights",
    response_model=DataEnvelope[HighlightListResponse],
    status_code=200,
    summary="List user's highlights",
    description="List all highlights created by a user across all documents.",
)
async def list_user_highlights(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    user_id: str = Path(..., description="Typed user ID (usr_<uuid>)"),
    limit: int = Query(default=20, ge=1, le=100, description="Results per page"),
    cursor: str | None = Query(None, description="Pagination cursor from previous response"),
) -> DataEnvelope[HighlightListResponse]:
    """List all highlights created by a user with cursor pagination.

    Enforces:
    - user_id must match current_user (users can only see their own highlights)
    - Results ordered by creation date (newest first)
    - Only documents owned by user are considered (no cross-library leaks)

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        user_id: Typed user ID (usr_<uuid>)
        limit: Number of results per page (1-100, default 20)
        cursor: Opaque cursor from previous next_cursor response

    Returns:
        HighlightListResponse with paginated highlights

    Raises:
        ValidationAppError (422): If user_id format is invalid or wrong type
        NotFoundError (404): If user_id doesn't match current_user (ACL enforcement)
    """
    # Parse and validate user_id
    try:
        user_type, user_uuid = from_api_id(user_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid user_id format: {str(e)}",
            details={"field": "user_id", "reason": str(e)},
        )

    if user_type != "user":
        raise ValidationAppError(
            message=f"Invalid user_id type: expected 'user', got '{user_type}'",
            details={"field": "user_id", "expected_type": "user", "got_type": user_type},
        )

    # ACL: Only allow self (return 404 if not matching current_user)
    if user_uuid != current_user.id:
        raise NotFoundError(
            message="User not found",
            details={"resource_type": "user"},
        )

    # List all highlights for this user (across all documents they own)
    from sqlalchemy import and_, desc

    from app.core.pagination import decode_cursor, encode_cursor
    from app.models.highlight import Highlight

    # Decode cursor
    last_created_at = None
    last_id = None
    if cursor:
        try:
            cursor_payload = decode_cursor(cursor)
            created_at = cursor_payload.get("created_at")
            last_id_str = cursor_payload.get("id")
            if created_at and isinstance(created_at, str):
                from datetime import datetime

                last_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if last_id_str and isinstance(last_id_str, str):
                from uuid import UUID

                last_id = UUID(last_id_str)
        except (ValueError, KeyError):
            raise ValidationAppError(
                message="Invalid pagination cursor",
                details={"field": "cursor"},
            )

    # Base query: highlights owned by user, not deleted
    query = session.query(Highlight).filter(
        and_(
            Highlight.user_id == current_user.id,
            Highlight.deleted_at.is_(None),
        )
    )

    # Apply cursor filtering
    if last_created_at is not None and last_id is not None:
        query = query.filter(
            (Highlight.created_at < last_created_at)
            | (
                and_(
                    Highlight.created_at == last_created_at,
                    Highlight.id < last_id,
                )
            )
        )

    # Sort: newest first
    query = query.order_by(desc(Highlight.created_at), desc(Highlight.id))

    # Fetch limit+1 to determine if there are more results
    highlights = query.limit(limit + 1).all()

    has_more = len(highlights) > limit
    if has_more:
        highlights = highlights[:limit]

    # Build next cursor
    next_cursor = None
    if has_more and highlights:
        last_hl = highlights[-1]
        next_cursor = encode_cursor(
            {
                "created_at": last_hl.created_at.isoformat(),
                "id": str(last_hl.id),
            }
        )

    # Convert to API response (with typed IDs and quote)
    return DataEnvelope(
        data=HighlightListResponse(
            items=[
                HighlightItem(
                    id=to_api_id("highlight", hl.id),
                    document_id=to_api_id("document", hl.media_id),
                    text_start=hl.text_start,
                    text_end=hl.text_end,
                    quote=hl.quote,
                    created_at=hl.created_at,
                    updated_at=hl.updated_at,
                )
                for hl in highlights
            ],
            next_cursor=next_cursor,
            has_more=has_more,
        )
    )
