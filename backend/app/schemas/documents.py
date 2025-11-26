"""Pydantic schemas for document endpoints.

This module defines request/response schemas for all document-related endpoints.
All schemas use Pydantic v2 for validation and serialization.

Spec reference:
- spec/api_contracts.md (typed IDs, response shapes)
- spec/schemas/documents.md (document schema)
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    """Summary representation of a document for list endpoints.

    This schema is used in paginated list responses and includes only essential
    metadata needed to display a document in a list. Full details (canonical_text,
    structure, metadata) are excluded.

    Attributes:
        id: Typed document ID (format: doc_<uuid>)
        title: Document title
        source_kind: Type of source (pdf, epub, html)
        processing_status: Current processing state (pending_canonicalization, ready, etc.)
        created_at: UTC timestamp when document was uploaded
        updated_at: UTC timestamp of last update

    Example:
        {
            "id": "doc_11111111-2222-3333-4444-555555555555",
            "title": "The Myth of Sisyphus",
            "source_kind": "pdf",
            "processing_status": "pending_canonicalization",
            "created_at": "2025-01-01T12:00:00Z",
            "updated_at": "2025-01-01T12:00:00Z"
        }
    """

    id: str = Field(description="Typed document ID (doc_<uuid>)")
    """Typed ID in format: doc_<uuid>"""

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
                "id": "doc_11111111-2222-3333-4444-555555555555",
                "title": "The Myth of Sisyphus",
                "source_kind": "pdf",
                "processing_status": "pending_canonicalization",
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        }
    }
