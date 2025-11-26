"""Reader service layer for reading session management.

This module implements the core business logic for reading sessions:
- Creating or retrieving reader records for user+document pairs
- Updating reading position and last access time
- Listing readers for a document with pagination

All functions enforce:
- User ownership (readers belong to authenticated user)
- Document access control (user must own the document)
- Pagination determinism (ORDER BY created_at DESC, id DESC)

Spec reference:
- PR 5.1 specification (reading sessions)
- spec/api_contracts.md (typed IDs, pagination, error envelopes)
- spec/acl.md (visibility rules)
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.pagination import PaginatedResponse, PaginationParams, decode_cursor, encode_cursor
from app.models.document import Document
from app.models.reader import Reader
from app.models.user import User
from app.schemas.readers import ReaderInternal


def get_or_create_reader_for_user(
    *,
    session: Session,
    user: User,
    document: Document,
) -> ReaderInternal:
    """Get or create a reader for the user and document.

    Semantics:
    - Enforce that user is allowed to see this document (user owns it)
    - If reader exists: return ReaderInternal
    - If reader doesn't exist: create it with initial state and return

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (must own the document)
        document: Document to create reader for

    Returns:
        ReaderInternal object (new or existing)

    Raises:
        NotFoundError: If document is not owned by user

    Example:
        >>> reader = get_or_create_reader_for_user(
        ...     session=db,
        ...     user=current_user,
        ...     document=doc,
        ... )
        >>> reader.current_position
        None
        >>> reader.last_read_at
        datetime(...)
    """
    # Enforce ACL: document must belong to user
    if document.user_id != user.id:
        raise NotFoundError(
            message="Document not found",
            details={"resource_type": "document", "resource_id": str(document.id)},
        )

    # Try to find existing reader
    reader = (
        session.query(Reader)
        .filter(and_(Reader.user_id == user.id, Reader.document_id == document.id))
        .first()
    )

    if reader is not None:
        return ReaderInternal.model_validate(reader)

    # Create new reader
    now = datetime.now(timezone.utc)
    reader = Reader(
        user_id=user.id,
        document_id=document.id,
        current_position=None,
        last_read_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(reader)
    session.flush()

    return ReaderInternal.model_validate(reader)


def get_reader_for_user(
    *,
    session: Session,
    user: User,
    reader_id: UUID,
) -> ReaderInternal:
    """Get a reader by ID with ownership check.

    Enforces:
    1. Reader exists (by UUID)
    2. Reader belongs to user (user_id == user.id)

    If any check fails, raises NotFoundError (404) - no information leak.

    Args:
        session: SQLAlchemy database session
        user: Authenticated user
        reader_id: UUID of reader to retrieve

    Returns:
        ReaderInternal object

    Raises:
        NotFoundError: If reader not found or user doesn't own it

    Example:
        >>> reader = get_reader_for_user(
        ...     session=db,
        ...     user=current_user,
        ...     reader_id=UUID("..."),
        ... )
    """
    reader = session.query(Reader).filter(Reader.id == reader_id).first()

    if reader is None or reader.user_id != user.id:
        raise NotFoundError(
            message="Reader not found",
            details={"resource_type": "reader", "resource_id": str(reader_id)},
        )

    return ReaderInternal.model_validate(reader)


def update_reader_position(
    *,
    session: Session,
    user: User,
    reader_id: UUID,
    current_position: int,
) -> ReaderInternal:
    """Update reader's current position and last_read_at timestamp.

    Updates:
    - current_position to provided value
    - last_read_at to current UTC time
    - updated_at is auto-updated by SQLAlchemy

    Args:
        session: SQLAlchemy database session
        user: Authenticated user
        reader_id: UUID of reader to update
        current_position: New byte offset (must be >= 0)

    Returns:
        Updated ReaderInternal object

    Raises:
        NotFoundError: If reader not found or user doesn't own it

    Example:
        >>> reader = update_reader_position(
        ...     session=db,
        ...     user=current_user,
        ...     reader_id=UUID("..."),
        ...     current_position=12345,
        ... )
        >>> reader.current_position
        12345
        >>> reader.last_read_at
        datetime(...)  # current time
    """
    # Use get_reader_for_user to enforce ACL (validates existence and ownership)
    get_reader_for_user(session=session, user=user, reader_id=reader_id)

    # Fetch the ORM object for updating
    reader_orm = session.query(Reader).filter(Reader.id == reader_id).first()
    assert reader_orm is not None  # We just checked it exists above

    # Update fields
    reader_orm.current_position = current_position
    reader_orm.last_read_at = datetime.now(timezone.utc)
    session.flush()

    return ReaderInternal.model_validate(reader_orm)


def list_readers_for_document(
    *,
    session: Session,
    owner: User,
    document_id: UUID,
    pagination: PaginationParams,
) -> PaginatedResponse[ReaderInternal]:
    """List readers for a document with pagination.

    Semantics:
    - Load document; if not found or not owned by owner -> NotFoundError
    - Query readers for that document
    - Order by created_at DESC, id DESC (deterministic)
    - Apply cursor pagination with limit + 1 pattern
    - Return PaginatedResponse with ReaderInternal items

    Args:
        session: SQLAlchemy database session
        owner: Authenticated user (must own the document)
        document_id: UUID of document to list readers for
        pagination: PaginationParams (limit, cursor)

    Returns:
        PaginatedResponse[ReaderInternal] with paginated readers

    Raises:
        NotFoundError: If document not found or not owned by user

    Example:
        >>> response = list_readers_for_document(
        ...     session=db,
        ...     owner=current_user,
        ...     document_id=UUID("..."),
        ...     pagination=PaginationParams(limit=20, cursor=None),
        ... )
        >>> response.items
        [ReaderInternal(...), ...]
        >>> response.has_more
        True
    """
    # Load and verify document ownership
    doc = session.query(Document).filter(Document.id == document_id).first()
    if doc is None or doc.user_id != owner.id:
        raise NotFoundError(
            message="Document not found",
            details={"resource_type": "document", "resource_id": str(document_id)},
        )

    # Decode cursor if provided
    offset_keys = None
    if pagination.cursor:
        offset_keys = decode_cursor(pagination.cursor)

    # Build base query
    query = session.query(Reader).filter(Reader.document_id == document_id)

    # Apply cursor pagination if offset provided
    if offset_keys:
        # offset_keys contains {"created_at": "...", "id": "..."}
        # We want: (created_at, id) < (offset_created_at, offset_id) in DESC order
        # Which means: created_at < offset_created_at OR (created_at == offset_created_at AND id < offset_id)
        from sqlalchemy import or_

        offset_created_at = datetime.fromisoformat(offset_keys["created_at"])
        offset_id = UUID(offset_keys["id"])
        query = query.filter(
            or_(
                Reader.created_at < offset_created_at,
                and_(Reader.created_at == offset_created_at, Reader.id < offset_id),
            )
        )

    # Order by created_at DESC, id DESC
    query = query.order_by(desc(Reader.created_at), desc(Reader.id))

    # Fetch limit + 1 to determine has_more
    items = query.limit(pagination.limit + 1).all()
    has_more = len(items) > pagination.limit
    items = items[: pagination.limit]

    # Generate next cursor if has_more
    next_cursor = None
    if has_more and items:
        last_item = items[-1]
        next_cursor = encode_cursor(
            {"created_at": last_item.created_at.isoformat(), "id": str(last_item.id)}
        )

    # Convert to internal schema
    reader_internals = [ReaderInternal.model_validate(item) for item in items]

    return PaginatedResponse(items=reader_internals, next_cursor=next_cursor, has_more=has_more)
