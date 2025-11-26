"""Annotations API routes for creation, updating, deletion, and retrieval.

Routes (spec-aligned):
- POST /annotations: Create a new annotation on a highlight or chunk
- PATCH /annotations/{annotation_id}: Update an annotation
- DELETE /annotations/{annotation_id}: Delete an annotation (soft delete)
- GET /documents/{document_id}/annotations: List annotations for a document
- GET /highlights/{highlight_id}/annotations: List annotations for a highlight
- GET /users/{user_id}/annotations: List annotations created by a user

All endpoints require authentication via Clerk JWT and rate limiting.

Spec reference:
- PR 5.3 specification (annotations API layer)
- spec/api_contracts.md (typed IDs, pagination, error envelopes)
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
from app.models.user import User
from app.schemas.annotations import (
    AnnotationItem,
    AnnotationListResponse,
    CreateAnnotationRequest,
    UpdateAnnotationRequest,
)
from app.services.highlights import (
    create_annotation,
    list_annotations_for_document,
    list_annotations_for_user,
    soft_delete_annotation,
    update_annotation,
)

logger = logging.getLogger(__name__)

# Create base router for /annotations and nested list endpoints
router = APIRouter(tags=["annotations"])


@router.post(
    "/annotations",
    response_model=AnnotationItem,
    status_code=201,
    summary="Create annotation",
    description="Create a new annotation on a highlight or chunk.",
)
async def create_annotation_endpoint(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    request: CreateAnnotationRequest,
) -> AnnotationItem:
    """Create an annotation on a highlight or chunk.

    Accepts:
    - highlight_id: Typed highlight ID (hl_<uuid>) OR
    - chunk_id: Typed chunk ID (chunk_<uuid>)
    - content: Annotation text (non-empty after stripping)

    Validates:
    - Exactly one of highlight_id or chunk_id is provided
    - highlight_id is a valid typed ID with "highlight" type
    - chunk_id is a valid typed ID with "chunk" type
    - Highlight/chunk exists and is owned/accessible by current user
    - Content is non-empty

    Returns typed API response with ann_<uuid> ID.

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        request: CreateAnnotationRequest with highlight_id/chunk_id and content

    Returns:
        AnnotationItem with typed IDs and timestamps

    Raises:
        ValidationAppError (422): If validation fails
            - Both or neither highlight_id/chunk_id provided
            - Invalid ID format or type
            - Empty content
        NotFoundError (404): If highlight/chunk doesn't exist or is not accessible
        UnauthorizedError (401): If not authenticated
    """
    highlight_uuid = None
    chunk_uuid = None

    # Parse and validate highlight_id if provided
    if request.highlight_id:
        try:
            hl_type, highlight_uuid = from_api_id(request.highlight_id)
        except ValueError as e:
            raise ValidationAppError(
                message=f"Invalid highlight_id format: {str(e)}",
                details={"field": "highlight_id", "reason": str(e)},
            )

        if hl_type != "highlight":
            raise ValidationAppError(
                message=f"Invalid highlight_id type: expected 'highlight', got '{hl_type}'",
                details={
                    "field": "highlight_id",
                    "expected_type": "highlight",
                    "got_type": hl_type,
                },
            )

    # Parse and validate chunk_id if provided
    if request.chunk_id:
        try:
            chunk_type, chunk_uuid = from_api_id(request.chunk_id)
        except ValueError as e:
            raise ValidationAppError(
                message=f"Invalid chunk_id format: {str(e)}",
                details={"field": "chunk_id", "reason": str(e)},
            )

        if chunk_type != "chunk":
            raise ValidationAppError(
                message=f"Invalid chunk_id type: expected 'chunk', got '{chunk_type}'",
                details={"field": "chunk_id", "expected_type": "chunk", "got_type": chunk_type},
            )

    # Create annotation using service layer
    annotation = create_annotation(
        session=session,
        user=current_user,
        highlight_id=highlight_uuid,
        chunk_id=chunk_uuid,
        content=request.content,
    )

    # Convert to API response with typed IDs
    return AnnotationItem(
        id=to_api_id("annotation", annotation.id),
        user_id=to_api_id("user", annotation.user_id),
        document_id=to_api_id("document", annotation.document_id) if annotation.document_id else "",
        highlight_id=(
            to_api_id("highlight", annotation.highlight_id) if annotation.highlight_id else None
        ),
        chunk_id=to_api_id("chunk", annotation.chunk_id) if annotation.chunk_id else None,
        content=annotation.content,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
    )


@router.patch(
    "/annotations/{annotation_id}",
    response_model=AnnotationItem,
    status_code=200,
    summary="Update annotation",
    description="Update an annotation's content.",
)
async def update_annotation_endpoint(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    annotation_id: str = Path(..., description="Typed annotation ID (ann_<uuid>)"),
    request: UpdateAnnotationRequest = None,
) -> AnnotationItem:
    """Update an annotation's content.

    Accepts:
    - content: Updated annotation text (non-empty after stripping)

    Validates:
    - annotation_id is a valid typed ID with "annotation" type
    - Annotation exists and belongs to current user
    - Annotation is not soft-deleted
    - New content is non-empty

    Returns updated AnnotationItem (200 OK).

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        annotation_id: Typed annotation ID (ann_<uuid>)
        request: UpdateAnnotationRequest with new content

    Returns:
        Updated AnnotationItem with typed IDs and timestamps

    Raises:
        ValidationAppError (422): If validation fails
            - Invalid annotation_id format or type
            - Empty content
        NotFoundError (404): If annotation doesn't exist, is not owned by user, or is deleted
        UnauthorizedError (401): If not authenticated
    """
    # Parse and validate annotation_id
    try:
        ann_type, ann_uuid = from_api_id(annotation_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid annotation_id format: {str(e)}",
            details={"field": "annotation_id", "reason": str(e)},
        )

    if ann_type != "annotation":
        raise ValidationAppError(
            message=f"Invalid annotation_id type: expected 'annotation', got '{ann_type}'",
            details={"field": "annotation_id", "expected_type": "annotation", "got_type": ann_type},
        )

    # Update annotation using service layer
    annotation = update_annotation(
        session=session,
        user=current_user,
        annotation_id=ann_uuid,
        content=request.content,
    )

    # Convert to API response with typed IDs
    return AnnotationItem(
        id=to_api_id("annotation", annotation.id),
        user_id=to_api_id("user", annotation.user_id),
        document_id=to_api_id("document", annotation.document_id) if annotation.document_id else "",
        highlight_id=(
            to_api_id("highlight", annotation.highlight_id) if annotation.highlight_id else None
        ),
        chunk_id=to_api_id("chunk", annotation.chunk_id) if annotation.chunk_id else None,
        content=annotation.content,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
    )


@router.delete(
    "/annotations/{annotation_id}",
    status_code=204,
    summary="Delete annotation",
    description="Delete an annotation (soft delete).",
)
async def delete_annotation_endpoint(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    annotation_id: str = Path(..., description="Typed annotation ID (ann_<uuid>)"),
) -> None:
    """Delete an annotation via soft delete.

    Validates:
    - annotation_id is a valid typed ID with "annotation" type
    - Annotation exists and belongs to current user
    - Annotation is not already soft-deleted

    Returns 204 No Content on success.

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        annotation_id: Typed annotation ID (ann_<uuid>)

    Raises:
        ValidationAppError (422): If annotation_id format is invalid
        NotFoundError (404): If annotation doesn't exist, is not owned by user, or is already deleted
        UnauthorizedError (401): If not authenticated
    """
    # Parse and validate annotation_id
    try:
        ann_type, ann_uuid = from_api_id(annotation_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid annotation_id format: {str(e)}",
            details={"field": "annotation_id", "reason": str(e)},
        )

    if ann_type != "annotation":
        raise ValidationAppError(
            message=f"Invalid annotation_id type: expected 'annotation', got '{ann_type}'",
            details={"field": "annotation_id", "expected_type": "annotation", "got_type": ann_type},
        )

    # Soft delete annotation using service layer
    was_deleted = soft_delete_annotation(
        session=session,
        user=current_user,
        annotation_id=ann_uuid,
    )

    if not was_deleted:
        raise NotFoundError(
            message="Annotation not found",
            details={"resource_type": "annotation"},
        )

    session.commit()


@router.get(
    "/documents/{document_id}/annotations",
    response_model=AnnotationListResponse,
    status_code=200,
    summary="List annotations for document",
    description="List all annotations on a specific document owned by current user.",
)
async def list_document_annotations(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    document_id: str = Path(..., description="Typed document ID (doc_<uuid>)"),
    limit: int = Query(default=20, ge=1, le=100, description="Results per page"),
    cursor: str | None = Query(None, description="Pagination cursor from previous response"),
) -> AnnotationListResponse:
    """List annotations for a document with cursor pagination.

    Enforces:
    - Document must exist and be owned by current user
    - Only annotations on highlights/chunks from this document are returned
    - Results ordered by creation date (newest first)

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        document_id: Typed document ID (doc_<uuid>)
        limit: Number of results per page (1-100, default 20)
        cursor: Opaque cursor from previous next_cursor response

    Returns:
        AnnotationListResponse with paginated annotations

    Raises:
        ValidationAppError (422): If document_id format is invalid
        NotFoundError (404): If document doesn't exist or is not owned by user
        UnauthorizedError (401): If not authenticated
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

    # List annotations using service layer
    paginated = list_annotations_for_document(
        session=session,
        user=current_user,
        document_id=doc_uuid,
        pagination=PaginationParams(limit=limit, cursor=cursor),
    )

    # Convert to API response (with typed IDs)
    return AnnotationListResponse(
        items=[
            AnnotationItem(
                id=to_api_id("annotation", ann.id),
                user_id=to_api_id("user", ann.user_id),
                document_id=to_api_id("document", ann.document_id) if ann.document_id else "",
                highlight_id=to_api_id("highlight", ann.highlight_id) if ann.highlight_id else None,
                chunk_id=to_api_id("chunk", ann.chunk_id) if ann.chunk_id else None,
                content=ann.content,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
            )
            for ann in paginated.items
        ],
        next_cursor=paginated.next_cursor,
        has_more=paginated.has_more,
    )


@router.get(
    "/highlights/{highlight_id}/annotations",
    response_model=AnnotationListResponse,
    status_code=200,
    summary="List annotations for highlight",
    description="List all annotations on a specific highlight.",
)
async def list_highlight_annotations(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    highlight_id: str = Path(..., description="Typed highlight ID (hl_<uuid>)"),
    limit: int = Query(default=20, ge=1, le=100, description="Results per page"),
    cursor: str | None = Query(None, description="Pagination cursor from previous response"),
) -> AnnotationListResponse:
    """List annotations for a highlight with cursor pagination.

    Enforces:
    - Highlight must exist and be owned by current user
    - Only annotations on this highlight are returned
    - Results ordered by creation date (newest first)

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        highlight_id: Typed highlight ID (hl_<uuid>)
        limit: Number of results per page (1-100, default 20)
        cursor: Opaque cursor from previous next_cursor response

    Returns:
        AnnotationListResponse with paginated annotations

    Raises:
        ValidationAppError (422): If highlight_id format is invalid
        NotFoundError (404): If highlight doesn't exist or is not owned by user
        UnauthorizedError (401): If not authenticated
    """
    from app.models.highlight import Highlight

    # Parse and validate highlight_id
    try:
        hl_type, hl_uuid = from_api_id(highlight_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid highlight_id format: {str(e)}",
            details={"field": "highlight_id", "reason": str(e)},
        )

    if hl_type != "highlight":
        raise ValidationAppError(
            message=f"Invalid highlight_id type: expected 'highlight', got '{hl_type}'",
            details={"field": "highlight_id", "expected_type": "highlight", "got_type": hl_type},
        )

    # Verify highlight exists and is owned by user
    hl = (
        session.query(Highlight)
        .filter(
            Highlight.id == hl_uuid,
            Highlight.user_id == current_user.id,
            Highlight.deleted_at.is_(None),
        )
        .first()
    )
    if not hl:
        raise NotFoundError(
            message="Highlight not found",
            details={"resource_type": "highlight"},
        )

    # List annotations using existing function
    from app.services.highlights import list_annotations_for_highlight

    paginated = list_annotations_for_highlight(
        session=session,
        user=current_user,
        highlight_id=hl_uuid,
        pagination=PaginationParams(limit=limit, cursor=cursor),
    )

    # Convert to API response (with typed IDs)
    return AnnotationListResponse(
        items=[
            AnnotationItem(
                id=to_api_id("annotation", ann.id),
                user_id=to_api_id("user", ann.user_id),
                document_id=to_api_id("document", ann.document_id) if ann.document_id else "",
                highlight_id=to_api_id("highlight", ann.highlight_id) if ann.highlight_id else None,
                chunk_id=to_api_id("chunk", ann.chunk_id) if ann.chunk_id else None,
                content=ann.content,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
            )
            for ann in paginated.items
        ],
        next_cursor=paginated.next_cursor,
        has_more=paginated.has_more,
    )


@router.get(
    "/users/{user_id}/annotations",
    response_model=AnnotationListResponse,
    status_code=200,
    summary="List user's annotations",
    description="List all annotations created by a user.",
)
async def list_user_annotations(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    user_id: str = Path(..., description="Typed user ID (usr_<uuid>)"),
    limit: int = Query(default=20, ge=1, le=100, description="Results per page"),
    cursor: str | None = Query(None, description="Pagination cursor from previous response"),
) -> AnnotationListResponse:
    """List all annotations created by a user with cursor pagination.

    Enforces:
    - user_id must match current_user (users can only see their own annotations)
    - Results ordered by creation date (newest first)

    Args:
        current_user: Authenticated user (rate limited)
        session: SQLAlchemy database session
        user_id: Typed user ID (usr_<uuid>)
        limit: Number of results per page (1-100, default 20)
        cursor: Opaque cursor from previous next_cursor response

    Returns:
        AnnotationListResponse with paginated annotations

    Raises:
        ValidationAppError (422): If user_id format is invalid or wrong type
        NotFoundError (404): If user_id doesn't match current_user (ACL enforcement)
        UnauthorizedError (401): If not authenticated
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

    # List all annotations for this user
    paginated = list_annotations_for_user(
        session=session,
        user=current_user,
        pagination=PaginationParams(limit=limit, cursor=cursor),
    )

    # Convert to API response (with typed IDs)
    return AnnotationListResponse(
        items=[
            AnnotationItem(
                id=to_api_id("annotation", ann.id),
                user_id=to_api_id("user", ann.user_id),
                document_id=to_api_id("document", ann.document_id) if ann.document_id else "",
                highlight_id=to_api_id("highlight", ann.highlight_id) if ann.highlight_id else None,
                chunk_id=to_api_id("chunk", ann.chunk_id) if ann.chunk_id else None,
                content=ann.content,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
            )
            for ann in paginated.items
        ],
        next_cursor=paginated.next_cursor,
        has_more=paginated.has_more,
    )
