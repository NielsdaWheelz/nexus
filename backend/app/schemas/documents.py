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
