"""Pydantic schemas for annotations API layer.

This module defines request/response schemas for all annotation operations.
All schemas use Pydantic v2 for validation and serialization.

Internal schemas (used in services) work with raw UUIDs. API response schemas
will convert to typed IDs during serialization.

Spec reference:
- spec/api_contracts.md (typed IDs, response shapes)
- PR 5.3 specification (annotations API)
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CreateAnnotationRequest(BaseModel):
    """Request body for POST /annotations.

    Accepts exactly one of highlight_id or chunk_id (mutually exclusive).

    Attributes:
        highlight_id: Optional typed highlight ID (hl_<uuid>)
        chunk_id: Optional typed chunk ID (chunk_<uuid>)
        content: The annotation text (required, non-empty after stripping)
    """

    highlight_id: Optional[str] = Field(
        default=None, description="Typed highlight ID (hl_<uuid>), mutually exclusive with chunk_id"
    )
    chunk_id: Optional[str] = Field(
        default=None,
        description="Typed chunk ID (chunk_<uuid>), mutually exclusive with highlight_id",
    )
    content: str = Field(description="Annotation text content (required, non-empty)")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is non-empty after stripping."""
        if not v or not v.strip():
            raise ValueError("content must be non-empty")
        return v.strip()

    @field_validator("chunk_id")
    @classmethod
    def validate_mutually_exclusive(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure exactly one of highlight_id or chunk_id is provided."""
        highlight_id = info.data.get("highlight_id")
        if highlight_id and v:
            raise ValueError("Cannot provide both highlight_id and chunk_id")
        if not highlight_id and not v:
            raise ValueError("Must provide either highlight_id or chunk_id")
        return v


class UpdateAnnotationRequest(BaseModel):
    """Request body for PATCH /annotations/{annotation_id}.

    Attributes:
        content: The updated annotation text (required, non-empty)
    """

    content: str = Field(description="Annotation text content (required, non-empty)")

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is non-empty after stripping."""
        if not v or not v.strip():
            raise ValueError("content must be non-empty")
        return v.strip()


class AnnotationItem(BaseModel):
    """API response item for a single annotation (used in list responses).

    All IDs are typed (e.g., ann_<uuid>, hl_<uuid>, chunk_<uuid>).

    Attributes:
        id: Typed annotation ID (ann_<uuid>)
        user_id: Typed user ID (usr_<uuid>)
        document_id: Typed document ID (doc_<uuid>)
        highlight_id: Optional typed highlight ID (hl_<uuid>)
        chunk_id: Optional typed chunk ID (chunk_<uuid>)
        content: The annotation text
        created_at: UTC timestamp of creation
        updated_at: UTC timestamp of last update
    """

    id: str = Field(description="Typed annotation ID (ann_<uuid>)")
    user_id: str = Field(description="Typed user ID (usr_<uuid>)")
    document_id: str = Field(description="Typed document ID (doc_<uuid>)")
    highlight_id: Optional[str] = Field(
        default=None, description="Typed highlight ID (hl_<uuid>), if attached to highlight"
    )
    chunk_id: Optional[str] = Field(
        default=None, description="Typed chunk ID (chunk_<uuid>), if attached to chunk"
    )
    content: str = Field(description="Annotation text content")
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")


class AnnotationListResponse(BaseModel):
    """API response for list annotations endpoints (with pagination).

    Attributes:
        items: List of AnnotationItem objects
        next_cursor: Opaque cursor for next page, or null if at end
        has_more: True if more pages exist, False otherwise
    """

    items: list[AnnotationItem] = Field(description="List of annotations")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    has_more: bool = Field(description="Whether more items exist")
