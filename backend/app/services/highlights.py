"""Highlights and annotations service layer for all domain operations.

This module implements the core business logic for highlights and annotations:
- Highlight creation with anchor validation
- Highlight retrieval with ownership/visibility checks
- Highlight listing with cursor pagination
- Annotation creation with validation
- Annotation retrieval and listing
- Soft-delete semantics

All functions enforce:
- User ownership (highlights/annotations belong to authenticated user)
- Soft delete rules (deleted_at check)
- Raw UUIDs internally (typed ID conversion happens at API layer)
- Pagination determinism (ORDER BY created_at DESC, id DESC)
- Anchor validation based on anchor_type

Spec reference:
- PR 3.2 specification (highlights and annotations service layer)
- spec/anchors.md (anchor validation rules)
- spec/acl.md (visibility rules - Phase 1: user ownership only)
- spec/api_contracts.md (typed IDs, pagination, error envelopes)
"""

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import PaginatedResponse, PaginationParams, decode_cursor, encode_cursor
from app.models.annotation import Annotation
from app.models.document import Document
from app.models.highlight import Highlight
from app.models.user import User
from app.schemas.highlights import AnnotationSummary, HighlightSummary

# ============================================================================
# ANCHOR VALIDATION
# ============================================================================


def _validate_text_anchor(
    *,
    canonical_text: str,
    text_start: int,
    text_end: int,
    quote: str,
    prefix: str,
    suffix: str,
) -> None:
    """Validate text anchor (for documents with canonical text).

    Args:
        canonical_text: The canonical text content
        text_start: Byte offset start (inclusive)
        text_end: Byte offset end (exclusive)
        quote: The quoted text (must match canonical_text[text_start:text_end])
        prefix: Context before quote (must match canonical_text[max(0, text_start-64):text_start])
        suffix: Context after quote (must match canonical_text[text_end:min(len, text_end+64)])

    Raises:
        ValidationAppError: If anchor is invalid
    """
    # Check offset bounds
    if text_start < 0:
        raise ValidationAppError(
            message="text_start must be non-negative",
            details={"field": "text_start", "value": text_start},
        )

    if text_end <= text_start:
        raise ValidationAppError(
            message="text_end must be greater than text_start",
            details={"field": "text_end", "value": text_end, "text_start": text_start},
        )

    canonical_bytes = canonical_text.encode("utf-8")
    if text_end > len(canonical_bytes):
        raise ValidationAppError(
            message=f"text_end ({text_end}) exceeds canonical_text length ({len(canonical_bytes)})",
            details={
                "field": "text_end",
                "value": text_end,
                "canonical_length": len(canonical_bytes),
            },
        )

    # Validate quote matches
    actual_quote = canonical_bytes[text_start:text_end].decode("utf-8", errors="replace")
    if actual_quote != quote:
        raise ValidationAppError(
            message="quote does not match canonical_text at given offsets",
            details={
                "expected": actual_quote[:100],
                "got": quote[:100],
            },
        )

    # Validate prefix matches (up to 64 bytes before start)
    prefix_start = max(0, text_start - 64)
    actual_prefix = canonical_bytes[prefix_start:text_start].decode("utf-8", errors="replace")
    if actual_prefix != prefix:
        raise ValidationAppError(
            message="prefix does not match text before quote",
            details={
                "expected": actual_prefix[:100],
                "got": prefix[:100],
            },
        )

    # Validate suffix matches (up to 64 bytes after end)
    suffix_end = min(len(canonical_bytes), text_end + 64)
    actual_suffix = canonical_bytes[text_end:suffix_end].decode("utf-8", errors="replace")
    if actual_suffix != suffix:
        raise ValidationAppError(
            message="suffix does not match text after quote",
            details={
                "expected": actual_suffix[:100],
                "got": suffix[:100],
            },
        )


def _validate_pdf_anchor(
    *,
    pdf_page_number: Optional[int],
    pdf_char_offset: Optional[int],
    pdf_file_hash: Optional[str],
) -> None:
    """Validate PDF anchor fields.

    For Phase 1, we perform minimal validation since we don't have direct PDF
    access in the service layer. Full validation (quote matching, etc.) would
    require PDF extraction which is deferred to API layer.

    Args:
        pdf_page_number: Page number (1-indexed)
        pdf_char_offset: Character offset within page
        pdf_file_hash: SHA256 of PDF file

    Raises:
        ValidationAppError: If anchor is invalid
    """
    if pdf_page_number is None or pdf_page_number < 1:
        raise ValidationAppError(
            message="pdf_page_number is required and must be >= 1",
            details={"field": "pdf_page_number", "value": pdf_page_number},
        )

    if pdf_char_offset is None or pdf_char_offset < 0:
        raise ValidationAppError(
            message="pdf_char_offset is required and must be >= 0",
            details={"field": "pdf_char_offset", "value": pdf_char_offset},
        )

    if not pdf_file_hash or not pdf_file_hash.strip():
        raise ValidationAppError(
            message="pdf_file_hash is required and cannot be empty",
            details={"field": "pdf_file_hash"},
        )


def _validate_transcript_anchor(
    *,
    transcript_text: str,
    text_start: int,
    text_end: int,
    quote: str,
    prefix: str,
    suffix: str,
    time_start: Optional[float],
    time_end: Optional[float],
) -> None:
    """Validate transcript anchor (for episodes/videos).

    Args:
        transcript_text: The transcript text content
        text_start: Byte offset start in transcript (inclusive)
        text_end: Byte offset end in transcript (exclusive)
        quote: The quoted text
        prefix: Context before quote
        suffix: Context after quote
        time_start: Start time in seconds
        time_end: End time in seconds

    Raises:
        ValidationAppError: If anchor is invalid
    """
    # Validate text offsets (same as text anchors)
    if text_start < 0:
        raise ValidationAppError(
            message="text_start must be non-negative",
            details={"field": "text_start", "value": text_start},
        )

    if text_end <= text_start:
        raise ValidationAppError(
            message="text_end must be greater than text_start",
            details={"field": "text_end", "value": text_end, "text_start": text_start},
        )

    transcript_bytes = transcript_text.encode("utf-8")
    if text_end > len(transcript_bytes):
        raise ValidationAppError(
            message=f"text_end ({text_end}) exceeds transcript_text length ({len(transcript_bytes)})",
            details={
                "field": "text_end",
                "value": text_end,
                "transcript_length": len(transcript_bytes),
            },
        )

    # Validate quote matches
    actual_quote = transcript_bytes[text_start:text_end].decode("utf-8", errors="replace")
    if actual_quote != quote:
        raise ValidationAppError(
            message="quote does not match transcript_text at given offsets",
            details={
                "expected": actual_quote[:100],
                "got": quote[:100],
            },
        )

    # Validate prefix and suffix
    prefix_start = max(0, text_start - 64)
    actual_prefix = transcript_bytes[prefix_start:text_start].decode("utf-8", errors="replace")
    if actual_prefix != prefix:
        raise ValidationAppError(
            message="prefix does not match text before quote",
            details={
                "expected": actual_prefix[:100],
                "got": prefix[:100],
            },
        )

    suffix_end = min(len(transcript_bytes), text_end + 64)
    actual_suffix = transcript_bytes[text_end:suffix_end].decode("utf-8", errors="replace")
    if actual_suffix != suffix:
        raise ValidationAppError(
            message="suffix does not match text after quote",
            details={
                "expected": actual_suffix[:100],
                "got": suffix[:100],
            },
        )

    # Validate time fields
    if time_start is None or time_start < 0:
        raise ValidationAppError(
            message="time_start is required and must be >= 0",
            details={"field": "time_start", "value": time_start},
        )

    if time_end is None or time_end <= time_start:
        raise ValidationAppError(
            message="time_end must be greater than time_start",
            details={"field": "time_end", "value": time_end, "time_start": time_start},
        )


# ============================================================================
# HIGHLIGHT OPERATIONS
# ============================================================================


def create_highlight(
    *,
    session: Session,
    user: User,
    media_type: Literal["document", "episode", "video"],
    media_id: UUID,
    anchor_type: Literal["text", "pdf", "transcript"],
    text_start: int,
    text_end: int,
    quote: str,
    prefix: str,
    suffix: str,
    transcript_hash: Optional[str] = None,
    pdf_page_number: Optional[int] = None,
    pdf_char_offset: Optional[int] = None,
    pdf_file_hash: Optional[str] = None,
    pdf_extraction_confidence: Optional[float] = None,
    time_start: Optional[float] = None,
    time_end: Optional[float] = None,
) -> HighlightSummary:
    """Create a highlight with anchor validation.

    For text anchors (documents), validates that quote/prefix/suffix match the
    canonical text at the given byte offsets. Text anchors use byte offsets and
    hash-based anchoring (no integer versions).

    For PDF anchors, performs minimal validation (field existence) as full
    validation requires PDF extraction at API layer.

    For transcript anchors (episodes/videos), validates text offsets and time fields.

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (highlight owner)
        media_type: Type of media (document, episode, video)
        media_id: UUID of the media object
        anchor_type: Type of anchor (text, pdf, transcript)
        text_start: Byte offset start in canonical/transcript text
        text_end: Byte offset end in canonical/transcript text
        quote: The exact text of the highlight
        prefix: Context before the quote (up to 64 bytes)
        suffix: Context after the quote (up to 64 bytes)
        transcript_hash: SHA256 of transcript (episodes/videos only)
        pdf_page_number: Page number in PDF (PDF anchors only)
        pdf_char_offset: Character offset within page (PDF anchors only)
        pdf_file_hash: SHA256 of PDF file (PDF anchors only)
        pdf_extraction_confidence: Confidence score (PDF anchors only)
        time_start: Start time in seconds (transcript anchors only)
        time_end: End time in seconds (transcript anchors only)

    Returns:
        HighlightSummary with the created highlight

    Raises:
        NotFoundError: If media doesn't exist or is not owned by user
        ValidationAppError: If anchor validation fails
    """
    # Verify user owns the media
    if media_type == "document":
        doc = (
            session.query(Document)
            .filter(
                and_(
                    Document.id == media_id,
                    Document.user_id == user.id,
                    Document.deleted_at.is_(None),
                )
            )
            .first()
        )
        if not doc:
            raise NotFoundError(
                message="Document not found",
                details={"resource_type": "document"},
            )

        # Validate text anchor against canonical text
        if anchor_type == "text":
            _validate_text_anchor(
                canonical_text=doc.canonical_text,
                text_start=text_start,
                text_end=text_end,
                quote=quote,
                prefix=prefix,
                suffix=suffix,
            )
    else:
        # Phase 1: episodes/videos not fully supported, but we still validate structure
        # In Phase 2+, would check episodes/videos tables
        raise ValidationAppError(
            message=f"Media type '{media_type}' is not supported in Phase 1",
            details={"field": "media_type", "value": media_type},
        )

    # Validate anchor type specific fields
    if anchor_type == "text":
        # Text anchors use byte offsets into canonical text (hash-based, no version)
        pass
    elif anchor_type == "pdf":
        _validate_pdf_anchor(
            pdf_page_number=pdf_page_number,
            pdf_char_offset=pdf_char_offset,
            pdf_file_hash=pdf_file_hash,
        )
    elif anchor_type == "transcript":
        if transcript_hash is None:
            raise ValidationAppError(
                message="transcript_hash is required for transcript anchors",
                details={"field": "transcript_hash"},
            )
        _validate_transcript_anchor(
            transcript_text="",  # Phase 1: minimal validation, full would need transcript data
            text_start=text_start,
            text_end=text_end,
            quote=quote,
            prefix=prefix,
            suffix=suffix,
            time_start=time_start,
            time_end=time_end,
        )

    # Create highlight
    now = datetime.now(timezone.utc)
    highlight = Highlight(
        user_id=user.id,
        media_type=media_type,
        media_id=media_id,
        anchor_type=anchor_type,
        text_start=text_start,
        text_end=text_end,
        quote=quote,
        prefix=prefix,
        suffix=suffix,
        transcript_hash=transcript_hash,
        pdf_page_number=pdf_page_number,
        pdf_char_offset=pdf_char_offset,
        pdf_file_hash=pdf_file_hash,
        pdf_extraction_confidence=pdf_extraction_confidence,
        time_start=time_start,
        time_end=time_end,
        color="yellow",
        is_hidden=False,
        is_detached=False,
        is_public=False,
        created_at=now,
        updated_at=now,
    )

    session.add(highlight)
    session.flush()

    return HighlightSummary(
        id=highlight.id,
        user_id=highlight.user_id,
        media_type=highlight.media_type,  # type: ignore
        media_id=highlight.media_id,
        anchor_type=highlight.anchor_type,  # type: ignore
        text_start=highlight.text_start,
        text_end=highlight.text_end,
        quote=highlight.quote,
        prefix=highlight.prefix,
        suffix=highlight.suffix,
        transcript_hash=highlight.transcript_hash,
        pdf_page_number=highlight.pdf_page_number,
        pdf_char_offset=highlight.pdf_char_offset,
        pdf_file_hash=highlight.pdf_file_hash,
        pdf_extraction_confidence=highlight.pdf_extraction_confidence,
        time_start=highlight.time_start,
        time_end=highlight.time_end,
        color=highlight.color,
        is_hidden=highlight.is_hidden,
        is_detached=highlight.is_detached,
        detached_reason=highlight.detached_reason,
        is_public=highlight.is_public,
        created_at=highlight.created_at,
        updated_at=highlight.updated_at,
    )


def get_highlight_for_user(
    *,
    session: Session,
    user: User,
    highlight_id: UUID,
) -> HighlightSummary:
    """Retrieve a highlight by ID with ownership and soft-delete checks.

    This function enforces:
    1. Highlight exists (by UUID)
    2. Highlight belongs to user (user_id == user.id)
    3. Highlight is not soft-deleted (deleted_at IS NULL)

    If any check fails, raises NotFoundError with generic message (no information leak).

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (must be highlight owner)
        highlight_id: Raw UUID of highlight

    Returns:
        HighlightSummary

    Raises:
        NotFoundError: If highlight doesn't exist, is not owned by user, or is deleted
    """
    hl = (
        session.query(Highlight)
        .filter(
            and_(
                Highlight.id == highlight_id,
                Highlight.user_id == user.id,
                Highlight.deleted_at.is_(None),
            )
        )
        .first()
    )

    if not hl:
        raise NotFoundError(
            message="Highlight not found",
            details={"resource_type": "highlight"},
        )

    return HighlightSummary(
        id=hl.id,
        user_id=hl.user_id,
        media_type=hl.media_type,  # type: ignore
        media_id=hl.media_id,
        anchor_type=hl.anchor_type,  # type: ignore
        text_start=hl.text_start,
        text_end=hl.text_end,
        quote=hl.quote,
        prefix=hl.prefix,
        suffix=hl.suffix,
        transcript_hash=hl.transcript_hash,
        pdf_page_number=hl.pdf_page_number,
        pdf_char_offset=hl.pdf_char_offset,
        pdf_file_hash=hl.pdf_file_hash,
        pdf_extraction_confidence=hl.pdf_extraction_confidence,
        time_start=hl.time_start,
        time_end=hl.time_end,
        color=hl.color,
        is_hidden=hl.is_hidden,
        is_detached=hl.is_detached,
        detached_reason=hl.detached_reason,
        is_public=hl.is_public,
        created_at=hl.created_at,
        updated_at=hl.updated_at,
    )


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


def list_highlights_for_document(
    *,
    session: Session,
    user: User,
    document_id: UUID,
    pagination: PaginationParams,
) -> PaginatedResponse[HighlightSummary]:
    """List all highlights on a document owned by user with cursor pagination.

    This function returns highlights in deterministic order:
    ORDER BY created_at DESC, id DESC (newest first)

    Pagination uses cursor encoding:
    - Cursor payload: {"created_at": <iso8601>, "id": "<uuid>"}
    - Cursor opaque and base64-encoded
    - Forward-only (no backward pagination)

    Filters:
    - Only highlights on the specified document
    - Only highlights owned by user (user_id == user.id)
    - Excludes soft-deleted highlights (deleted_at IS NULL)

    Args:
        session: SQLAlchemy database session
        user: Authenticated user
        document_id: UUID of the document
        pagination: PaginationParams with limit and optional cursor

    Returns:
        PaginatedResponse[HighlightSummary] with:
        - items: List of HighlightSummary objects (0 to limit)
        - next_cursor: Opaque cursor for next page or None if end reached
        - has_more: True if more pages exist, False otherwise

    Raises:
        ValidationAppError: If cursor is invalid
    """
    # Decode cursor to get keyset values
    last_created_at, last_id = _decode_pagination_cursor(pagination.cursor)

    # Base query: highlights on document owned by user, not deleted
    query = session.query(Highlight).filter(
        and_(
            Highlight.user_id == user.id,
            Highlight.media_type == "document",
            Highlight.media_id == document_id,
            Highlight.deleted_at.is_(None),
        )
    )

    # Apply cursor filtering (keyset pagination)
    if last_created_at is not None and last_id is not None:
        query = query.filter(
            # Either earlier timestamp, or same timestamp but smaller id
            (Highlight.created_at < last_created_at)
            | (
                and_(
                    Highlight.created_at == last_created_at,
                    Highlight.id < last_id,
                )
            )
        )

    # Sort: newest first (created_at DESC), then by id DESC
    query = query.order_by(desc(Highlight.created_at), desc(Highlight.id))

    # Fetch limit+1 to determine if there are more results
    highlights = query.limit(pagination.limit + 1).all()

    has_more = len(highlights) > pagination.limit
    if has_more:
        highlights = highlights[: pagination.limit]

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

    # Convert to summaries
    items = [
        HighlightSummary(
            id=hl.id,
            user_id=hl.user_id,
            media_type=hl.media_type,  # type: ignore
            media_id=hl.media_id,
            anchor_type=hl.anchor_type,  # type: ignore
            text_start=hl.text_start,
            text_end=hl.text_end,
            quote=hl.quote,
            prefix=hl.prefix,
            suffix=hl.suffix,
            transcript_hash=hl.transcript_hash,
            pdf_page_number=hl.pdf_page_number,
            pdf_char_offset=hl.pdf_char_offset,
            pdf_file_hash=hl.pdf_file_hash,
            pdf_extraction_confidence=hl.pdf_extraction_confidence,
            time_start=hl.time_start,
            time_end=hl.time_end,
            color=hl.color,
            is_hidden=hl.is_hidden,
            is_detached=hl.is_detached,
            detached_reason=hl.detached_reason,
            is_public=hl.is_public,
            created_at=hl.created_at,
            updated_at=hl.updated_at,
        )
        for hl in highlights
    ]

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def soft_delete_highlight(
    *,
    session: Session,
    user: User,
    highlight_id: UUID,
) -> bool:
    """Mark a highlight as soft-deleted (set deleted_at timestamp).

    This function enforces:
    1. Highlight exists (by UUID)
    2. Highlight belongs to user (user_id == user.id)
    3. Highlight is not already soft-deleted

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (must be highlight owner)
        highlight_id: Raw UUID of highlight

    Returns:
        True if successfully deleted, False if already deleted

    Raises:
        NotFoundError: If highlight doesn't exist or is not owned by user
    """
    hl = (
        session.query(Highlight)
        .filter(
            and_(
                Highlight.id == highlight_id,
                Highlight.user_id == user.id,
            )
        )
        .first()
    )

    if not hl:
        raise NotFoundError(
            message="Highlight not found",
            details={"resource_type": "highlight"},
        )

    if hl.deleted_at is not None:
        return False

    hl.deleted_at = datetime.now(timezone.utc)
    hl.updated_at = datetime.now(timezone.utc)
    session.flush()

    return True


# ============================================================================
# ANNOTATION OPERATIONS
# ============================================================================


def create_annotation(
    *,
    session: Session,
    user: User,
    highlight_id: UUID,
    content: str = "",
) -> AnnotationSummary:
    """Create an annotation on a highlight.

    Annotations attach only to highlights (user-selected text spans), never to chunks.
    Chunks are purely for retrieval and embeddings; they are not annotation targets.

    This function enforces:
    1. highlight_id is provided and valid
    2. Highlight exists and belongs to user
    3. Highlight is not soft-deleted
    4. Annotation content is non-empty

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (annotation creator)
        highlight_id: Required raw UUID of the highlight
        content: The annotation text

    Returns:
        AnnotationSummary with the created annotation

    Raises:
        NotFoundError: If highlight doesn't exist, is not accessible to user, or is deleted
        ValidationAppError: If content is empty
    """
    # Validate content is non-empty
    if not content or not content.strip():
        raise ValidationAppError(
            message="Annotation content cannot be empty",
            details={"field": "content"},
        )

    document_id = None

    # Verify highlight exists and is accessible to user
    hl = (
        session.query(Highlight)
        .filter(
            and_(
                Highlight.id == highlight_id,
                Highlight.user_id == user.id,
                Highlight.deleted_at.is_(None),
            )
        )
        .first()
    )

    if not hl:
        raise NotFoundError(
            message="Highlight not found",
            details={"resource_type": "highlight"},
        )

    # Get document_id from highlight for document-level queries
    if hl.media_type == "document":
        document_id = hl.media_id

    # Create annotation
    now = datetime.now(timezone.utc)
    annotation = Annotation(
        user_id=user.id,
        highlight_id=highlight_id,
        content=content.strip(),
        is_public=False,
        created_at=now,
        updated_at=now,
    )

    session.add(annotation)
    session.flush()

    return AnnotationSummary(
        id=annotation.id,
        user_id=annotation.user_id,
        highlight_id=annotation.highlight_id,
        document_id=document_id,
        content=annotation.content,
        is_public=annotation.is_public,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
    )


def list_annotations_for_highlight(
    *,
    session: Session,
    user: User,
    highlight_id: UUID,
    pagination: PaginationParams,
) -> PaginatedResponse[AnnotationSummary]:
    """List all annotations on a highlight owned by user with cursor pagination.

    This function returns annotations in deterministic order:
    ORDER BY created_at DESC, id DESC (newest first)

    Pagination uses cursor encoding:
    - Cursor payload: {"created_at": <iso8601>, "id": "<uuid>"}

    Filters:
    - Only annotations on the specified highlight
    - Only highlights owned by user (enforced implicitly via FK)
    - Excludes soft-deleted annotations (deleted_at IS NULL)

    Args:
        session: SQLAlchemy database session
        user: Authenticated user
        highlight_id: UUID of the highlight
        pagination: PaginationParams with limit and optional cursor

    Returns:
        PaginatedResponse[AnnotationSummary]

    Raises:
        NotFoundError: If highlight doesn't exist or is not owned by user
        ValidationAppError: If cursor is invalid
    """
    # Verify highlight exists and is owned by user
    hl = (
        session.query(Highlight)
        .filter(
            and_(
                Highlight.id == highlight_id,
                Highlight.user_id == user.id,
                Highlight.deleted_at.is_(None),
            )
        )
        .first()
    )

    if not hl:
        raise NotFoundError(
            message="Highlight not found",
            details={"resource_type": "highlight"},
        )

    # Decode cursor to get keyset values
    last_created_at, last_id = _decode_pagination_cursor(pagination.cursor)

    # Base query: annotations on highlight, not deleted
    query = session.query(Annotation).filter(
        and_(
            Annotation.highlight_id == highlight_id,
            Annotation.deleted_at.is_(None),
        )
    )

    # Apply cursor filtering (keyset pagination)
    if last_created_at is not None and last_id is not None:
        query = query.filter(
            (Annotation.created_at < last_created_at)
            | (
                and_(
                    Annotation.created_at == last_created_at,
                    Annotation.id < last_id,
                )
            )
        )

    # Sort: newest first (created_at DESC), then by id DESC
    query = query.order_by(desc(Annotation.created_at), desc(Annotation.id))

    # Fetch limit+1 to determine if there are more results
    annotations = query.limit(pagination.limit + 1).all()

    has_more = len(annotations) > pagination.limit
    if has_more:
        annotations = annotations[: pagination.limit]

    # Build next cursor
    next_cursor = None
    if has_more and annotations:
        last_ann = annotations[-1]
        next_cursor = encode_cursor(
            {
                "created_at": last_ann.created_at.isoformat(),
                "id": str(last_ann.id),
            }
        )

    # Convert to summaries
    items = [
        AnnotationSummary(
            id=ann.id,
            user_id=ann.user_id,
            highlight_id=ann.highlight_id,
            content=ann.content,
            is_public=ann.is_public,
            created_at=ann.created_at,
            updated_at=ann.updated_at,
        )
        for ann in annotations
    ]

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def get_annotation_for_user(
    *,
    session: Session,
    user: User,
    annotation_id: UUID,
) -> AnnotationSummary:
    """Retrieve an annotation by ID with ownership and soft-delete checks.

    This function enforces:
    1. Annotation exists (by UUID)
    2. Annotation belongs to user (user_id == user.id)
    3. Annotation is not soft-deleted (deleted_at IS NULL)

    If any check fails, raises NotFoundError with generic message (no information leak).

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (must be annotation owner)
        annotation_id: Raw UUID of annotation

    Returns:
        AnnotationSummary

    Raises:
        NotFoundError: If annotation doesn't exist, is not owned by user, or is deleted
    """
    ann = (
        session.query(Annotation)
        .filter(
            and_(
                Annotation.id == annotation_id,
                Annotation.user_id == user.id,
                Annotation.deleted_at.is_(None),
            )
        )
        .first()
    )

    if not ann:
        raise NotFoundError(
            message="Annotation not found",
            details={"resource_type": "annotation"},
        )

    # Determine document_id from highlight or chunk
    document_id = None
    if ann.highlight_id is not None:
        hl = session.query(Highlight).filter(Highlight.id == ann.highlight_id).first()
        if hl and hl.media_type == "document":
            document_id = hl.media_id

    return AnnotationSummary(
        id=ann.id,
        user_id=ann.user_id,
        highlight_id=ann.highlight_id,
        document_id=document_id,
        content=ann.content,
        is_public=ann.is_public,
        created_at=ann.created_at,
        updated_at=ann.updated_at,
    )


def update_annotation(
    *,
    session: Session,
    user: User,
    annotation_id: UUID,
    content: str,
) -> AnnotationSummary:
    """Update an annotation's content.

    This function enforces:
    1. Annotation exists (by UUID)
    2. Annotation belongs to user (user_id == user.id)
    3. Annotation is not soft-deleted
    4. New content is non-empty

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (must be annotation owner)
        annotation_id: Raw UUID of annotation
        content: Updated annotation text

    Returns:
        Updated AnnotationSummary

    Raises:
        NotFoundError: If annotation doesn't exist, is not owned by user, or is deleted
        ValidationAppError: If content is empty
    """
    if not content or not content.strip():
        raise ValidationAppError(
            message="Annotation content cannot be empty",
            details={"field": "content"},
        )

    ann = (
        session.query(Annotation)
        .filter(
            and_(
                Annotation.id == annotation_id,
                Annotation.user_id == user.id,
                Annotation.deleted_at.is_(None),
            )
        )
        .first()
    )

    if not ann:
        raise NotFoundError(
            message="Annotation not found",
            details={"resource_type": "annotation"},
        )

    ann.content = content.strip()
    ann.updated_at = datetime.now(timezone.utc)
    session.flush()

    # Determine document_id from highlight or chunk
    document_id = None
    if ann.highlight_id is not None:
        hl = session.query(Highlight).filter(Highlight.id == ann.highlight_id).first()
        if hl and hl.media_type == "document":
            document_id = hl.media_id

    return AnnotationSummary(
        id=ann.id,
        user_id=ann.user_id,
        highlight_id=ann.highlight_id,
        document_id=document_id,
        content=ann.content,
        is_public=ann.is_public,
        created_at=ann.created_at,
        updated_at=ann.updated_at,
    )


def soft_delete_annotation(
    *,
    session: Session,
    user: User,
    annotation_id: UUID,
) -> bool:
    """Mark an annotation as soft-deleted (set deleted_at timestamp).

    This function enforces:
    1. Annotation exists (by UUID)
    2. Annotation belongs to user (user_id == user.id)
    3. Annotation is not already soft-deleted

    Args:
        session: SQLAlchemy database session
        user: Authenticated user (must be annotation creator)
        annotation_id: Raw UUID of annotation

    Returns:
        True if successfully deleted, False if already deleted

    Raises:
        NotFoundError: If annotation doesn't exist or is not owned by user
    """
    ann = (
        session.query(Annotation)
        .filter(
            and_(
                Annotation.id == annotation_id,
                Annotation.user_id == user.id,
            )
        )
        .first()
    )

    if not ann:
        raise NotFoundError(
            message="Annotation not found",
            details={"resource_type": "annotation"},
        )

    if ann.deleted_at is not None:
        return False

    ann.deleted_at = datetime.now(timezone.utc)
    ann.updated_at = datetime.now(timezone.utc)
    session.flush()

    return True


def list_annotations_for_document(
    *,
    session: Session,
    user: User,
    document_id: UUID,
    pagination: PaginationParams,
) -> PaginatedResponse[AnnotationSummary]:
    """List all annotations on a document owned by user with cursor pagination.

    This function returns annotations in deterministic order:
    ORDER BY created_at DESC, id DESC (newest first)

    Filters:
    - Only annotations on highlights/chunks from the specified document
    - Only document owned by user
    - Excludes soft-deleted annotations

    Args:
        session: SQLAlchemy database session
        user: Authenticated user
        document_id: UUID of the document
        pagination: PaginationParams with limit and optional cursor

    Returns:
        PaginatedResponse[AnnotationSummary]

    Raises:
        NotFoundError: If document doesn't exist or is not owned by user
        ValidationAppError: If cursor is invalid
    """
    # Verify document exists and is owned by user
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
        raise NotFoundError(
            message="Document not found",
            details={"resource_type": "document"},
        )

    # Decode cursor to get keyset values
    last_created_at, last_id = _decode_pagination_cursor(pagination.cursor)

    # Base query: annotations on highlights/chunks of this document, not deleted
    # Join with highlights to filter by document
    query = session.query(Annotation).filter(
        and_(
            Annotation.deleted_at.is_(None),
            # Either highlight from this document OR chunk from this document
        )
    )

    # Filter by document via highlight or chunk
    # For highlights: media_type='document' and media_id=document_id
    # For chunks: media_type='document' and media_id=document_id

    highlight_doc_filter = and_(
        Annotation.highlight_id.isnot(None),
        Highlight.media_type == "document",
        Highlight.media_id == document_id,
    )

    query = query.outerjoin(Highlight, Annotation.highlight_id == Highlight.id).filter(
        highlight_doc_filter
    )

    # Apply cursor filtering (keyset pagination)
    if last_created_at is not None and last_id is not None:
        query = query.filter(
            (Annotation.created_at < last_created_at)
            | (
                and_(
                    Annotation.created_at == last_created_at,
                    Annotation.id < last_id,
                )
            )
        )

    # Sort: newest first (created_at DESC), then by id DESC
    query = query.order_by(desc(Annotation.created_at), desc(Annotation.id))

    # Fetch limit+1 to determine if there are more results
    annotations = query.limit(pagination.limit + 1).all()

    has_more = len(annotations) > pagination.limit
    if has_more:
        annotations = annotations[: pagination.limit]

    # Build next cursor
    next_cursor = None
    if has_more and annotations:
        last_ann = annotations[-1]
        next_cursor = encode_cursor(
            {
                "created_at": last_ann.created_at.isoformat(),
                "id": str(last_ann.id),
            }
        )

    # Convert to summaries
    items = [
        AnnotationSummary(
            id=ann.id,
            user_id=ann.user_id,
            highlight_id=ann.highlight_id,
            document_id=document_id,
            content=ann.content,
            is_public=ann.is_public,
            created_at=ann.created_at,
            updated_at=ann.updated_at,
        )
        for ann in annotations
    ]

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def list_annotations_for_user(
    *,
    session: Session,
    user: User,
    pagination: PaginationParams,
) -> PaginatedResponse[AnnotationSummary]:
    """List all annotations created by user with cursor pagination.

    This function returns annotations in deterministic order:
    ORDER BY created_at DESC, id DESC (newest first)

    Filters:
    - Only annotations created by user (user_id == user.id)
    - Excludes soft-deleted annotations

    Args:
        session: SQLAlchemy database session
        user: Authenticated user
        pagination: PaginationParams with limit and optional cursor

    Returns:
        PaginatedResponse[AnnotationSummary]

    Raises:
        ValidationAppError: If cursor is invalid
    """
    # Decode cursor to get keyset values
    last_created_at, last_id = _decode_pagination_cursor(pagination.cursor)

    # Base query: annotations created by user, not deleted
    query = session.query(Annotation).filter(
        and_(
            Annotation.user_id == user.id,
            Annotation.deleted_at.is_(None),
        )
    )

    # Apply cursor filtering (keyset pagination)
    if last_created_at is not None and last_id is not None:
        query = query.filter(
            (Annotation.created_at < last_created_at)
            | (
                and_(
                    Annotation.created_at == last_created_at,
                    Annotation.id < last_id,
                )
            )
        )

    # Sort: newest first (created_at DESC), then by id DESC
    query = query.order_by(desc(Annotation.created_at), desc(Annotation.id))

    # Fetch limit+1 to determine if there are more results
    annotations = query.limit(pagination.limit + 1).all()

    has_more = len(annotations) > pagination.limit
    if has_more:
        annotations = annotations[: pagination.limit]

    # Build next cursor
    next_cursor = None
    if has_more and annotations:
        last_ann = annotations[-1]
        next_cursor = encode_cursor(
            {
                "created_at": last_ann.created_at.isoformat(),
                "id": str(last_ann.id),
            }
        )

    # Convert to summaries (need to fetch document_id for each)

    items = []
    for ann in annotations:
        document_id = None
        if ann.highlight_id is not None:
            hl = session.query(Highlight).filter(Highlight.id == ann.highlight_id).first()
            if hl and hl.media_type == "document":
                document_id = hl.media_id

        items.append(
            AnnotationSummary(
                id=ann.id,
                user_id=ann.user_id,
                highlight_id=ann.highlight_id,
                document_id=document_id,
                content=ann.content,
                is_public=ann.is_public,
                created_at=ann.created_at,
                updated_at=ann.updated_at,
            )
        )

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
