"""Pydantic schemas for document endpoints.

This module defines request/response schemas for all document-related endpoints.
All schemas use Pydantic v2 for validation and serialization.

Internal schemas (used in services) work with raw UUIDs. API response schemas
convert to typed IDs during serialization.

Spec reference:
- spec/api_contracts.md (typed IDs, response shapes)
- spec/schemas/documents.md (document schema)
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    """Internal summary representation of a document (service layer).

    This schema is used internally by services and represents a document with
    raw UUID (not typed ID). API responses will convert this to typed ID format
    during serialization.

    Attributes:
        id: Raw document UUID (not typed ID; conversion happens at API boundary)
        title: Document title
        source_kind: Type of source (pdf, epub, html)
        processing_status: Current processing state
        created_at: UTC timestamp when document was uploaded
        updated_at: UTC timestamp of last update
    """

    id: UUID = Field(description="Raw document UUID")
    """Raw UUID (API layer converts to doc_<uuid>)"""

    title: str | None = Field(description="Document title (may be None)")
    """Document title, may be None if not yet extracted"""

    source_kind: Literal["pdf", "epub", "html"] = Field(description="Type of source document")
    """Source document type: one of pdf, epub, html"""

    processing_status: str = Field(description="Current processing state")
    """Processing status: pending_canonicalization, ready, failed, etc."""

    created_at: datetime = Field(description="UTC timestamp of upload")
    """When the document was uploaded (ISO8601 UTC)"""

    updated_at: datetime = Field(description="UTC timestamp of last update")
    """When the document was last updated (ISO8601 UTC)"""

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "11111111-2222-3333-4444-555555555555",
                "title": "The Myth of Sisyphus",
                "source_kind": "pdf",
                "processing_status": "pending_canonicalization",
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        }
    }


class DocumentUploadResponse(BaseModel):
    """API response for successful document upload.

    Returns a newly created document placeholder with typed ID format.

    Attributes:
        id: Typed document ID (format: doc_<uuid>)
        title: Document title (resolved from explicit override or filename)
        source_kind: Type of source (pdf, epub, html)
        created_at: UTC timestamp of upload
        updated_at: UTC timestamp of creation
    """

    id: str = Field(description="Typed document ID (doc_<uuid>)")
    """Typed document ID in format: doc_<uuid>"""

    title: str = Field(description="Document title")
    """Document title (from explicit override or original filename)"""

    source_kind: Literal["pdf", "epub", "html"] = Field(description="Type of source document")
    """Source document type: one of pdf, epub, html"""

    created_at: datetime = Field(description="UTC timestamp of upload")
    """When the document was created (ISO8601 UTC)"""

    updated_at: datetime = Field(description="UTC timestamp of creation")
    """When the document was updated (ISO8601 UTC)"""

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "doc_11111111-2222-3333-4444-555555555555",
                "title": "The Myth of Sisyphus",
                "source_kind": "pdf",
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        }
    }


class DocumentListItem(BaseModel):
    """API response schema for a single document in list endpoint.

    This is the document representation returned by GET /documents.
    All IDs are typed (doc_<uuid>), timestamps are ISO8601 UTC.

    Attributes:
        id: Typed document ID (doc_<uuid>)
        title: Document title
        source_kind: Type of source (pdf, epub, html)
        processing_status: Current processing state (pending, processing, ready, failed)
        created_at: UTC timestamp when document was uploaded
        updated_at: UTC timestamp of last update
    """

    id: str = Field(description="Typed document ID (doc_<uuid>)")
    """Typed document ID in format: doc_<uuid>"""

    title: str | None = Field(description="Document title (may be None)")
    """Document title, may be None if not yet extracted"""

    source_kind: Literal["pdf", "epub", "html"] = Field(description="Type of source document")
    """Source document type: one of pdf, epub, html"""

    processing_status: Literal["pending", "processing", "ready", "failed"] = Field(
        description="Current processing state"
    )
    """Processing status: pending, processing, ready, or failed"""

    created_at: datetime = Field(description="UTC timestamp of upload")
    """When the document was uploaded (ISO8601 UTC)"""

    updated_at: datetime = Field(description="UTC timestamp of last update")
    """When the document was last updated (ISO8601 UTC)"""

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "doc_11111111-2222-3333-4444-555555555555",
                "title": "The Myth of Sisyphus",
                "source_kind": "pdf",
                "processing_status": "ready",
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        }
    }


class DocumentContentResponse(BaseModel):
    """API response for GET /documents/{id}/content.

    Returns the canonical text content of a document for rendering.
    This endpoint returns the full canonical text without pagination.

    Note: For large documents (>5MB), expect response times of 1-3s.
    Streaming or range requests are deferred to v2.

    Attributes:
        canonical_text: The full canonical text content (UTF-8)
        canonical_hash: SHA256 hash of canonical_text
        anchored_content_hash: Hash at time of most recent highlight creation (may be null)
        source_kind: Type of source (pdf, epub, html)
        text_length: Length of canonical_text in characters (codepoints)
    """

    canonical_text: str = Field(description="Full canonical text content")
    """The canonical text extracted from the document"""

    canonical_hash: str = Field(description="SHA256 of canonical_text")
    """Hash for detecting content changes"""

    anchored_content_hash: str | None = Field(
        default=None, description="Hash at time of highlight creation"
    )
    """Used for highlight remap detection; null if no highlights exist"""

    source_kind: Literal["pdf", "epub", "html"] = Field(description="Type of source document")
    """Source document type: one of pdf, epub, html"""

    text_length: int = Field(description="Length of canonical_text in characters")
    """Character count (codepoints) for validation"""

    model_config = {
        "json_schema_extra": {
            "example": {
                "canonical_text": "Chapter 1\n\nIt was a bright cold day in April...",
                "canonical_hash": "a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd",
                "anchored_content_hash": None,
                "source_kind": "epub",
                "text_length": 45,
            }
        }
    }


class DocumentListResponse(BaseModel):
    """API response for GET /documents (list documents).

    Returns paginated list of user's documents with cursor-based pagination.

    Attributes:
        items: List of DocumentListItem objects (0 to limit)
        next_cursor: Opaque cursor for next page, or None if end reached
        has_more: True if more pages exist, False otherwise
    """

    items: list[DocumentListItem] = Field(description="List of documents")
    """Array of documents for current page"""

    next_cursor: str | None = Field(default=None, description="Cursor for next page")
    """Opaque base64-encoded cursor for next page, or null if no more pages"""

    has_more: bool = Field(description="Whether more pages exist")
    """True if additional pages available, False if this is last page"""

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "doc_11111111-2222-3333-4444-555555555555",
                        "title": "The Myth of Sisyphus",
                        "source_kind": "pdf",
                        "processing_status": "ready",
                        "created_at": "2025-01-01T12:00:00Z",
                        "updated_at": "2025-01-01T12:00:00Z",
                    },
                    {
                        "id": "doc_22222222-3333-4444-5555-666666666666",
                        "title": "Crime and Punishment",
                        "source_kind": "epub",
                        "processing_status": "ready",
                        "created_at": "2025-01-02T10:30:00Z",
                        "updated_at": "2025-01-02T10:32:00Z",
                    },
                ],
                "next_cursor": "eyJjcmVhdGVkX2F0IjogIjIwMjUtMDEtMDJUMTA6MzA6MDBaIiwgImlkIjogIjIyMjIyMjIyLTMzMzMtNDQ0NC01NTU1LTY2NjY2NjY2NjY2NiJ9",
                "has_more": True,
            }
        }
    }
