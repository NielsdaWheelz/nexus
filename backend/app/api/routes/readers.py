"""Reader (reading session) API routes.

This module provides:
- POST /readers: Create or retrieve a reading session for a document
- GET /readers/{reader_id}: Get a specific reading session
- PATCH /readers/{reader_id}: Update reading position
- GET /documents/{document_id}/readers: List readers for a document

All endpoints require authentication via Clerk JWT.

Spec reference:
- PR 5.1 specification (reading sessions HTTP layer)
- spec/api_contracts.md (typed IDs, error envelopes)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth.deps import rate_limit_authenticated
from app.core.errors import ValidationAppError
from app.core.ids import from_api_id, to_api_id
from app.db.session import get_session as _get_session
from app.models.document import Document
from app.models.user import User
from app.schemas.readers import (
    CreateReaderRequest,
    ReaderResponse,
    UpdateReaderRequest,
)
from app.services.readers import (
    get_or_create_reader_for_user,
    get_reader_for_user,
    update_reader_position,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/readers", tags=["readers"])


@router.post(
    "",
    response_model=ReaderResponse,
    status_code=201,
    summary="Create or retrieve reading session",
    description="Create a new reading session for a document, or return existing session if already created.",
)
def create_reader(
    payload: CreateReaderRequest,
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
) -> ReaderResponse:
    """Create or retrieve a reading session for a document.

    Semantics:
    - Parse document_id from request
    - Load document; if not owned by user -> 404
    - Get-or-create reader for (user, document)
    - Commit transaction
    - Return ReaderResponse with typed IDs

    Args:
        payload: CreateReaderRequest with document_id
        current_user: Authenticated user (rate limited)
        session: Database session

    Returns:
        ReaderResponse with typed reader ID

    Raises:
        ValidationAppError (422): If document_id format invalid
        NotFoundError (404): If document not found or user doesn't own it

    Example:
        >>> POST /readers
        >>> { "document_id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" }
        >>> {
        ...     "id": "rdr_11111111-2222-3333-4444-555555555555",
        ...     "document_id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ...     "current_position": None,
        ...     "last_read_at": "2025-01-01T12:00:00Z",
        ...     "created_at": "2025-01-01T12:00:00Z",
        ...     "updated_at": "2025-01-01T12:00:00Z"
        ... }
    """
    # Parse and validate document_id
    try:
        doc_type, doc_uuid = from_api_id(payload.document_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid document_id format: {str(e)}",
            details={"field": "document_id", "value": payload.document_id},
        ) from e

    # Verify document type
    if doc_type != "document":
        raise ValidationAppError(
            message=f"Expected document ID, got {doc_type}",
            details={"field": "document_id", "expected_type": "document", "got_type": doc_type},
        )

    # Load document
    doc = session.query(Document).filter(Document.id == doc_uuid).first()
    if doc is None:
        raise ValidationAppError(
            message="Document not found",
            details={"field": "document_id", "resource_id": str(doc_uuid)},
        )

    # Get or create reader (enforces ACL)
    reader_internal = get_or_create_reader_for_user(
        session=session,
        user=current_user,
        document=doc,
    )
    session.commit()

    # Convert to typed ID response
    return ReaderResponse(
        id=to_api_id("reader", reader_internal.id),
        document_id=to_api_id("document", reader_internal.document_id),
        current_position=reader_internal.current_position,
        last_read_at=reader_internal.last_read_at,
        created_at=reader_internal.created_at,
        updated_at=reader_internal.updated_at,
    )


@router.get(
    "/{reader_id}",
    response_model=ReaderResponse,
    summary="Get reading session",
    description="Retrieve a reading session by ID.",
)
def get_reader(
    reader_id: str,
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
) -> ReaderResponse:
    """Get a reading session by ID.

    Enforces:
    - Reader exists
    - User owns the reader

    Args:
        reader_id: Typed reader ID (rdr_<uuid>)
        current_user: Authenticated user
        session: Database session

    Returns:
        ReaderResponse with typed IDs

    Raises:
        ValidationAppError (422): If reader_id format invalid
        NotFoundError (404): If reader not found or user doesn't own it

    Example:
        >>> GET /readers/rdr_11111111-2222-3333-4444-555555555555
        >>> {
        ...     "id": "rdr_11111111-2222-3333-4444-555555555555",
        ...     "document_id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ...     "current_position": 12345,
        ...     "last_read_at": "2025-01-01T12:00:00Z",
        ...     "created_at": "2025-01-01T12:00:00Z",
        ...     "updated_at": "2025-01-01T12:00:00Z"
        ... }
    """
    # Parse and validate reader_id
    try:
        rdr_type, rdr_uuid = from_api_id(reader_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid reader_id format: {str(e)}",
            details={"field": "reader_id", "value": reader_id},
        ) from e

    # Verify reader type
    if rdr_type != "reader":
        raise ValidationAppError(
            message=f"Expected reader ID, got {rdr_type}",
            details={"field": "reader_id", "expected_type": "reader", "got_type": rdr_type},
        )

    # Get reader with ACL enforcement
    reader_internal = get_reader_for_user(
        session=session,
        user=current_user,
        reader_id=rdr_uuid,
    )

    # Convert to typed ID response
    return ReaderResponse(
        id=to_api_id("reader", reader_internal.id),
        document_id=to_api_id("document", reader_internal.document_id),
        current_position=reader_internal.current_position,
        last_read_at=reader_internal.last_read_at,
        created_at=reader_internal.created_at,
        updated_at=reader_internal.updated_at,
    )


@router.patch(
    "/{reader_id}",
    response_model=ReaderResponse,
    summary="Update reading position",
    description="Update the current reading position in a document.",
)
def update_reader(
    reader_id: str,
    payload: UpdateReaderRequest,
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
) -> ReaderResponse:
    """Update a reader's reading position.

    Updates:
    - current_position to provided value
    - last_read_at to current UTC time

    Args:
        reader_id: Typed reader ID (rdr_<uuid>)
        payload: UpdateReaderRequest with current_position
        current_user: Authenticated user
        session: Database session

    Returns:
        Updated ReaderResponse with typed IDs

    Raises:
        ValidationAppError (422): If reader_id format invalid or current_position < 0
        NotFoundError (404): If reader not found or user doesn't own it

    Example:
        >>> PATCH /readers/rdr_11111111-2222-3333-4444-555555555555
        >>> { "current_position": 12345 }
        >>> {
        ...     "id": "rdr_11111111-2222-3333-4444-555555555555",
        ...     "document_id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ...     "current_position": 12345,
        ...     "last_read_at": "2025-01-01T12:00:01Z",
        ...     "created_at": "2025-01-01T12:00:00Z",
        ...     "updated_at": "2025-01-01T12:00:01Z"
        ... }
    """
    # Parse and validate reader_id
    try:
        rdr_type, rdr_uuid = from_api_id(reader_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid reader_id format: {str(e)}",
            details={"field": "reader_id", "value": reader_id},
        ) from e

    # Verify reader type
    if rdr_type != "reader":
        raise ValidationAppError(
            message=f"Expected reader ID, got {rdr_type}",
            details={"field": "reader_id", "expected_type": "reader", "got_type": rdr_type},
        )

    # Update reader with ACL enforcement
    reader_internal = update_reader_position(
        session=session,
        user=current_user,
        reader_id=rdr_uuid,
        current_position=payload.current_position,
    )
    session.commit()

    # Convert to typed ID response
    return ReaderResponse(
        id=to_api_id("reader", reader_internal.id),
        document_id=to_api_id("document", reader_internal.document_id),
        current_position=reader_internal.current_position,
        last_read_at=reader_internal.last_read_at,
        created_at=reader_internal.created_at,
        updated_at=reader_internal.updated_at,
    )
