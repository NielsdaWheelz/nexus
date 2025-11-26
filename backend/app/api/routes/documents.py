"""Document upload and management routes.

This module provides:
- POST /documents: Upload document and create placeholder

All endpoints require authentication via Clerk JWT.

Spec reference:
- PR 4.1 specification (document upload HTTP layer)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.auth.deps import rate_limit_authenticated
from app.core.errors import AppError, ErrorCode, ValidationAppError
from app.core.ids import to_api_id
from app.db.session import get_session as _get_session
from app.models.user import User
from app.schemas.documents import DocumentUploadResponse
from app.services.documents import create_document_placeholder
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
    session.commit()

    # Convert to typed ID response
    return DocumentUploadResponse(
        id=to_api_id("document", doc.id),
        title=doc.title,
        source_kind=source_kind,  # type: ignore
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )
