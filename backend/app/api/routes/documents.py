"""Document upload and management routes.

This module provides:
- POST /documents: Upload document and create placeholder
- GET /documents: List user's documents with cursor pagination

All endpoints require authentication via Clerk JWT.

Spec reference:
- PR 3.1 specification (document upload HTTP layer)
- PR 4.2 specification (document list HTTP layer)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.auth.deps import rate_limit_authenticated
from app.core.errors import AppError, ErrorCode, ValidationAppError
from app.core.ids import from_api_id, to_api_id
from app.core.pagination import PaginationParams
from app.db.session import get_session as _get_session
from app.models.user import User
from app.schemas.documents import DocumentListItem, DocumentListResponse, DocumentUploadResponse
from app.schemas.readers import ReaderListResponse, ReaderResponse
from app.services.documents import create_document_placeholder, list_documents_for_user
from app.services.readers import list_readers_for_document as list_readers_service
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=201,
    summary="Upload document",
    description="Upload a document file and create a placeholder for ingestion.",
)
async def upload_document(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    file: UploadFile = File(...),
    source_kind: str = Form(...),
    title: str | None = Form(None),
) -> DocumentUploadResponse:
    """Upload a document file and create a placeholder.

    Accepts multipart/form-data with:
    - file: UploadFile (required)
    - source_kind: str (required) - one of: pdf, epub, html
    - title: str (optional) - explicit title override

    Validates:
    - file is provided
    - file size > 0
    - source_kind ∈ {"pdf", "epub", "html"}

    Stores blob via StorageService and calls create_document_placeholder.

    Returns typed API response with doc_<uuid> ID.

    Args:
        current_user: Authenticated user (rate limited)
        file: Uploaded file
        source_kind: Type of source (pdf, epub, html)
        title: Optional explicit title

    Returns:
        DocumentUploadResponse with typed document ID

    Raises:
        ValidationAppError (422): If validation fails
            - file not provided
            - file size is 0
            - invalid source_kind
        AppError (503): If storage fails (wrapped or unexpected)

    Example:
        >>> # POST /documents
        >>> # Content-Type: multipart/form-data
        >>> # file=<pdf file>
        >>> # source_kind=pdf
        >>> # title=My Document
        >>> {
        ...     "id": "doc_11111111-2222-3333-4444-555555555555",
        ...     "title": "My Document",
        ...     "source_kind": "pdf",
        ...     "created_at": "2025-01-01T12:00:00Z",
        ...     "updated_at": "2025-01-01T12:00:00Z"
        ... }
    """
    # Validate file is provided
    if not file or not file.filename:
        raise ValidationAppError(
            message="file is required",
            details={"field": "file"},
        )

    # Validate source_kind
    valid_kinds = {"pdf", "epub", "html"}
    if source_kind not in valid_kinds:
        raise ValidationAppError(
            message=f"source_kind must be one of: {', '.join(sorted(valid_kinds))}",
            details={"field": "source_kind", "value": source_kind},
        )

    # Read file content to validate size
    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise ValidationAppError(
            message="file is empty",
            details={"field": "file", "size": 0},
        )

    # Store blob
    storage = StorageService()
    try:
        blob_key = storage.store_raw_blob(file)
    except (OSError, IOError) as e:
        logger.error(f"Storage failure: {e}")
        raise AppError(
            code=ErrorCode.UNAVAILABLE,
            http_status=503,
            message="Storage service unavailable",
            details={"error_type": type(e).__name__},
        ) from e

    # Create document placeholder via service
    # session is already injected via Depends(_get_session)
    doc = create_document_placeholder(
        session=session,
        user=current_user,
        source_kind=source_kind,  # type: ignore
        original_blob_uri=blob_key,
        original_filename=file.filename,
        original_mime_type=file.content_type,
        original_size_bytes=len(file_bytes),
        source_url=None,
        title=title,
    )

    # Convert to typed ID response
    return DocumentUploadResponse(
        id=to_api_id("document", doc.id),
        title=doc.title,
        source_kind=source_kind,  # type: ignore
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=200,
    summary="List user's documents",
    description="Retrieve paginated list of authenticated user's documents.",
)
async def list_documents(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    pagination: PaginationParams = Depends(),
    status: str | None = Query(
        default=None,
        description="Optional status filter (pending, processing, ready, failed)",
    ),
) -> DocumentListResponse:
    """List user's documents with cursor pagination and optional status filter.

    Retrieves all documents owned by the authenticated user, ordered by
    creation time (newest first). Supports cursor-based pagination and
    optional status filtering.

    Query Parameters:
    - cursor: Opaque pagination cursor (None to start from beginning)
    - limit: Results per page (default 20, max 100)
    - status: Optional status filter (pending, processing, ready, failed)

    Returns typed document IDs (doc_<uuid>) and respects all ACL rules.
    Soft-deleted documents are never returned.

    Args:
        current_user: Authenticated user (rate limited)
        session: Database session
        pagination: PaginationParams (cursor, limit)
        status: Optional status filter

    Returns:
        DocumentListResponse with:
        - items: List of DocumentListItem objects
        - next_cursor: Cursor for next page or None
        - has_more: Whether more pages exist

    Raises:
        ValidationAppError (422): If status is invalid or cursor malformed
        AppError (401): If user not authenticated

    Example:
        >>> # GET /documents?limit=20&status=ready
        >>> {
        ...     "items": [
        ...         {
        ...             "id": "doc_11111111-2222-3333-4444-555555555555",
        ...             "title": "The Myth of Sisyphus",
        ...             "source_kind": "pdf",
        ...             "processing_status": "ready",
        ...             "created_at": "2025-01-01T12:00:00Z",
        ...             "updated_at": "2025-01-01T12:00:00Z"
        ...         }
        ...     ],
        ...     "next_cursor": null,
        ...     "has_more": false
        ... }
    """
    # Call service layer with optional status filter
    result = list_documents_for_user(
        session=session,
        user=current_user,
        pagination=pagination,
        status_filter=status,
    )

    # Convert DocumentSummary objects to DocumentListItem with typed IDs
    items = [
        DocumentListItem(
            id=to_api_id("document", item.id),
            title=item.title,
            source_kind=item.source_kind,
            processing_status=item.processing_status,  # type: ignore  # str to Literal
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in result.items
    ]

    return DocumentListResponse(
        items=items,
        next_cursor=result.next_cursor,
        has_more=result.has_more,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentListItem,
    status_code=200,
    summary="Get document detail",
    description="Retrieve a single document by ID with full metadata.",
)
async def get_document(
    document_id: str,
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
) -> DocumentListItem:
    """Get a single document by ID.

    Path Parameters:
    - document_id: Typed document ID (doc_<uuid>)

    Returns full document metadata with typed ID and timestamps.
    Returns 404 if document doesn't exist or user doesn't own it.

    Args:
        document_id: Typed document ID
        current_user: Authenticated user (must own the document)
        session: Database session

    Returns:
        DocumentListItem with full metadata

    Raises:
        ValidationAppError (422): If document_id format invalid
        NotFoundError (404): If document not found or user doesn't own it

    Example:
        >>> GET /documents/doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
        >>> {
        ...     "id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ...     "title": "The Myth of Sisyphus",
        ...     "source_kind": "pdf",
        ...     "processing_status": "ready",
        ...     "created_at": "2025-01-01T12:00:00Z",
        ...     "updated_at": "2025-01-01T12:05:00Z"
        ... }
    """
    # Parse and validate document_id
    try:
        doc_type, doc_uuid = from_api_id(document_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid document_id format: {str(e)}",
            details={"field": "document_id", "value": document_id},
        ) from e

    # Verify document type
    if doc_type != "document":
        raise ValidationAppError(
            message=f"Expected document ID, got {doc_type}",
            details={"field": "document_id", "expected_type": "document", "got_type": doc_type},
        )

    # Retrieve document with ownership check (raises NotFoundError if not found/not owned/deleted)
    from app.services.documents import _mime_to_source_kind, get_document_for_user

    doc = get_document_for_user(
        session=session,
        user=current_user,
        document_id=doc_uuid,
    )

    # Convert to API response with typed ID
    return DocumentListItem(
        id=to_api_id("document", doc.id),
        title=doc.title,
        source_kind=_mime_to_source_kind(doc.original_mime_type),  # type: ignore
        processing_status=doc.status,  # type: ignore
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get(
    "/{document_id}/readers",
    response_model=ReaderListResponse,
    summary="List readers for document",
    description="List all reading sessions for a document with cursor pagination.",
)
def list_document_readers(
    document_id: str,
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    pagination: PaginationParams = Depends(),
) -> ReaderListResponse:
    """List readers for a document with pagination.

    Only the document owner can see readers for their document.
    Returns all readers for a document ordered by creation time (newest first).

    Path Parameters:
    - document_id: Typed document ID (doc_<uuid>)

    Query Parameters:
    - cursor: Opaque pagination cursor (None to start from beginning)
    - limit: Results per page (default 20, max 100)

    Returns typed reader and document IDs.

    Args:
        document_id: Typed document ID
        current_user: Authenticated user (must own the document)
        session: Database session
        pagination: PaginationParams (cursor, limit)

    Returns:
        ReaderListResponse with paginated readers

    Raises:
        ValidationAppError (422): If document_id format invalid
        NotFoundError (404): If document not found or user doesn't own it

    Example:
        >>> GET /documents/doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/readers
        >>> {
        ...     "items": [
        ...         {
        ...             "id": "rdr_11111111-2222-3333-4444-555555555555",
        ...             "document_id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ...             "current_position": 12345,
        ...             "last_read_at": "2025-01-01T12:00:00Z",
        ...             "created_at": "2025-01-01T10:00:00Z",
        ...             "updated_at": "2025-01-01T12:00:00Z"
        ...         }
        ...     ],
        ...     "next_cursor": "...",
        ...     "has_more": False
        ... }
    """
    # Parse and validate document_id
    try:
        doc_type, doc_uuid = from_api_id(document_id)
    except ValueError as e:
        raise ValidationAppError(
            message=f"Invalid document_id format: {str(e)}",
            details={"field": "document_id", "value": document_id},
        ) from e

    # Verify document type
    if doc_type != "document":
        raise ValidationAppError(
            message=f"Expected document ID, got {doc_type}",
            details={"field": "document_id", "expected_type": "document", "got_type": doc_type},
        )

    # List readers for document (enforces ACL via service)
    result = list_readers_service(
        session=session,
        owner=current_user,
        document_id=doc_uuid,
        pagination=pagination,
    )

    # Convert ReaderInternal objects to ReaderResponse with typed IDs
    items = [
        ReaderResponse(
            id=to_api_id("reader", item.id),
            document_id=to_api_id("document", item.document_id),
            current_position=item.current_position,
            last_read_at=item.last_read_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in result.items
    ]

    return ReaderListResponse(
        items=items,
        next_cursor=result.next_cursor,
        has_more=result.has_more,
    )
