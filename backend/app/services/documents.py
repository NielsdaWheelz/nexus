"""Document service layer for all document operations.

This module implements the core business logic for document management:
- Document placeholder creation (for later ingestion)
- Document retrieval with ownership/visibility checks
- Document listing with cursor pagination

All functions enforce:
- User ownership (documents belong to authenticated user)
- Soft delete rules (deleted_at check)
- Typed ID generation for API responses
- Pagination determinism (ORDER BY created_at DESC, id DESC)

Spec reference:
- PR 3.1 specification (document service layer)
- spec/api_contracts.md (typed IDs, pagination, error envelopes)
- spec/acl.md (visibility rules)
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.ids import to_api_id
from app.core.pagination import PaginatedResponse, PaginationParams, decode_cursor, encode_cursor
from app.models.document import Document
from app.models.user import User
from app.schemas.documents import DocumentSummary


def create_document_placeholder(
    *,
    session: Session,
    user: User,
    source_kind: Literal["pdf", "epub", "html"],
    original_blob_uri: str,
    original_filename: str | None,
    original_mime_type: str | None,
    original_size_bytes: int | None,
    source_url: str | None,
    title: str | None = None,
) -> Document:
    """Create a placeholder document for later ingestion and canonical text extraction.

    This function creates a Document row in pending state. It does NOT:
    - Extract canonical text
    - Enqueue ingestion jobs
    - Upload files to storage

    The document is created with minimal metadata. Later, async jobs will:
    1. Download/fetch the original blob
    2. Extract canonical text
    3. Update status to 'ready' or 'failed'

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (document owner)
        source_kind: Type of source (pdf, epub, html)
        original_blob_uri: URI/path to original blob (for later retrieval)
        original_filename: Original filename (optional, for reference)
        original_mime_type: MIME type of original file
        original_size_bytes: File size in bytes
        source_url: Optional URL where document was sourced from
        title: Optional explicit title (overrides filename)

    Returns:
        Newly created Document ORM object (with id set)

    Raises:
        ValidationAppError: If required arguments are missing/malformed
            - Invalid source_kind
            - Negative size_bytes

    Example:
        >>> doc = create_document_placeholder(
        ...     session=db,
        ...     user=current_user,
        ...     source_kind="pdf",
        ...     original_blob_uri="s3://bucket/file.pdf",
        ...     original_filename="document.pdf",
        ...     original_mime_type="application/pdf",
        ...     original_size_bytes=12345,
        ...     source_url="https://example.com/doc.pdf",
        ...     title="My Document Title"
        ... )
    """
    # Validate required arguments
    if source_kind not in ("pdf", "epub", "html"):
        raise ValidationAppError(
            message=f"source_kind must be one of: pdf, epub, html (got {source_kind})",
            details={"field": "source_kind", "value": source_kind},
        )

    if original_size_bytes is not None and original_size_bytes < 0:
        raise ValidationAppError(
            message="original_size_bytes cannot be negative",
            details={"field": "original_size_bytes", "value": original_size_bytes},
        )

    # Create document with initial state
    now = datetime.now(timezone.utc)
    # Resolve title: explicit override > filename > default
    resolved_title = title or original_filename or "Untitled"
    doc = Document(
        user_id=user.id,
        title=resolved_title,
        source_url=source_url,
        original_blob_key=original_blob_uri,
        original_mime_type=original_mime_type or "application/octet-stream",
        original_size_bytes=original_size_bytes or 0,
        content_hash="",  # Computed during ingestion
        canonical_text="",  # Empty until extraction
        canonical_hash="",  # Empty until extraction
        canonical_version=1,
        text_byte_length=0,
        extractor_version="pending",  # Will be set during extraction
        structure={},
        doc_metadata={},
        status="pending",  # Initial state (pending_canonicalization)
        embedding_status="pending",
        created_at=now,
        updated_at=now,
    )

    # Add to session and flush to get ID
    session.add(doc)
    session.flush()

    return doc


def get_document_for_user(
    *,
    session: Session,
    user: User,
    document_id: UUID,
) -> Document:
    """Retrieve a document by ID with ownership and soft-delete checks.

    This function enforces:
    1. Document exists (by UUID)
    2. Document belongs to user (user_id == user.id)
    3. Document is not soft-deleted (deleted_at IS NULL)

    If any check fails, raises NotFoundError with generic message (no information leak).

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (must be document owner)
        document_id: Raw UUID of document

    Returns:
        Document ORM object

    Raises:
        NotFoundError: If document doesn't exist, is not owned by user, or is deleted
            - Generic message: "Document not found"
            - Details include: resource_type="document", resource_id="doc_<uuid>"

    Example:
        >>> doc = get_document_for_user(
        ...     session=db,
        ...     user=current_user,
        ...     document_id=UUID("11111111-2222-3333-4444-555555555555")
        ... )
    """
    doc = (
        session.query(Document)
        .filter(
            and_(
                Document.id == document_id,
                Document.user_id == user.id,
                Document.deleted_at.is_(None),
            )
        )
        .first()
    )

    if not doc:
        # Generic error: don't leak whether document exists or ownership status
        raise NotFoundError(
            message="Document not found",
            details={
                "resource_type": "document",
                "resource_id": to_api_id("document", document_id),
            },
        )

    return doc


def _mime_to_source_kind(mime_type: str) -> Literal["pdf", "epub", "html"]:
    """Map MIME type to source_kind (pdf, epub, html).

    Args:
        mime_type: MIME type string

    Returns:
        One of: pdf, epub, html (defaults to pdf)
    """
    mime_lower = mime_type.lower()
    if "pdf" in mime_lower:
        return "pdf"
    elif "epub" in mime_lower:
        return "epub"
    elif "html" in mime_lower or "xml" in mime_lower:
        return "html"
    else:
        return "pdf"


def _decode_pagination_cursor(
    cursor: str | None,
) -> tuple[datetime | None, UUID | None]:
    """Decode pagination cursor to extract keyset values.

    Args:
        cursor: Opaque base64-encoded cursor or None

    Returns:
        Tuple of (created_at, id) or (None, None) if no cursor

    Raises:
        ValidationAppError: If cursor is invalid
    """
    if not cursor:
        return None, None

    cursor_payload = decode_cursor(cursor)
    created_at = cursor_payload.get("created_at")
    last_id = cursor_payload.get("id")

    if last_id and isinstance(last_id, str):
        last_id = UUID(last_id)

    if created_at and isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

    return created_at, last_id


def list_documents_for_user(
    *,
    session: Session,
    user: User,
    pagination: PaginationParams,
) -> PaginatedResponse[DocumentSummary]:
    """List all documents owned by user with cursor pagination.

    This function returns documents in deterministic order:
    ORDER BY created_at DESC, id DESC (newest first)

    Pagination uses cursor encoding:
    - Cursor payload: {"created_at": <iso8601>, "id": "<uuid>"}
    - Cursor opaque and base64-encoded
    - Forward-only (no backward pagination)

    Filters:
    - Only documents owned by user (user_id == user.id)
    - Excludes soft-deleted documents (deleted_at IS NULL)

    Args:
        session: SQLAlchemy database session
        user: Authenticated user
        pagination: PaginationParams with limit and optional cursor

    Returns:
        PaginatedResponse[DocumentSummary] with:
        - items: List of DocumentSummary objects (0 to limit)
        - next_cursor: Opaque cursor for next page or None if end reached
        - has_more: True if more pages exist, False otherwise

    Raises:
        ValidationAppError: If cursor is invalid

    Example:
        >>> pagination = PaginationParams(limit=20, cursor=None)
        >>> result = list_documents_for_user(
        ...     session=db,
        ...     user=current_user,
        ...     pagination=pagination
        ... )
        >>> print(f"Got {len(result.items)} documents")
        >>> if result.has_more:
        ...     next_pagination = PaginationParams(limit=20, cursor=result.next_cursor)
    """
    # Decode cursor to get keyset values
    last_created_at, last_id = _decode_pagination_cursor(pagination.cursor)

    # Base query: documents owned by user, not deleted
    query = session.query(Document).filter(
        and_(
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
        )
    )

    # Apply cursor filtering (keyset pagination)
    if last_created_at is not None and last_id is not None:
        query = query.filter(
            # Either earlier timestamp, or same timestamp but smaller id
            (Document.created_at < last_created_at)
            | (
                and_(
                    Document.created_at == last_created_at,
                    Document.id < last_id,
                )
            )
        )

    # Sort: newest first (created_at DESC), then by id DESC
    query = query.order_by(desc(Document.created_at), desc(Document.id))

    # Fetch limit+1 to determine if there are more results
    documents = query.limit(pagination.limit + 1).all()

    has_more = len(documents) > pagination.limit
    if has_more:
        documents = documents[: pagination.limit]

    # Build next cursor
    next_cursor = None
    if has_more and documents:
        last_doc = documents[-1]
        next_cursor = encode_cursor(
            {
                "created_at": last_doc.created_at.isoformat(),
                "id": str(last_doc.id),
            }
        )

    # Convert to summaries (with raw UUIDs; API layer converts to typed IDs)
    items = [
        DocumentSummary(
            id=doc.id,
            title=doc.title,
            source_kind=_mime_to_source_kind(doc.original_mime_type),
            processing_status=doc.status,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc in documents
    ]

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
