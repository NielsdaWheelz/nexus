"""Pydantic schemas for highlights and annotations domain layer.

This module defines request/response schemas for all highlight and annotation operations.
All schemas use Pydantic v2 for validation and serialization.

Internal schemas (used in services) work with raw UUIDs. API response schemas
will convert to typed IDs during serialization (not done here).

Spec reference:
- spec/api_contracts.md (typed IDs, response shapes)
- spec/schemas/annotations.md (highlight and annotation schema)
- spec/anchors.md (anchor validation rules)
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class HighlightSummary(BaseModel):
    """Internal summary representation of a highlight (service layer).

    This schema is used internally by services and represents a highlight with
    raw UUID (not typed ID). API responses will convert this to typed ID format
    during serialization.

    Attributes:
        id: Raw highlight UUID (not typed ID; conversion happens at API boundary)
        user_id: Raw user UUID (owner of the highlight)
        media_type: Type of media (document, episode, video)
        media_id: Raw media UUID
        anchor_type: Type of anchor (text, pdf, transcript)
        text_start: Byte offset start
        text_end: Byte offset end
        quote: The exact text of the highlight
        prefix: Context before the quote
        suffix: Context after the quote
        canonical_version: Version of canonical text (for documents only)
        transcript_hash: Transcript hash (for episodes/videos only)
        pdf_page_number: PDF page number (for PDF anchors only)
        pdf_char_offset: PDF character offset (for PDF anchors only)
        pdf_file_hash: PDF file hash (for PDF anchors only)
        pdf_extraction_confidence: PDF extraction confidence (for PDF anchors only)
        time_start: Start time in seconds (for transcript anchors only)
        time_end: End time in seconds (for transcript anchors only)
        color: Highlight color
        is_hidden: Whether highlight is hidden
        is_detached: Whether highlight lost its anchor
        detached_reason: Reason for detachment
        is_public: Whether highlight is shared publicly
        created_at: UTC timestamp of creation
        updated_at: UTC timestamp of last update
    """

    id: UUID = Field(description="Raw highlight UUID")
    user_id: UUID = Field(description="Raw user UUID (owner)")
    media_type: Literal["document", "episode", "video"] = Field(description="Type of media")
    media_id: UUID = Field(description="Raw media UUID")
    anchor_type: Literal["text", "pdf", "transcript"] = Field(description="Type of anchor")
    text_start: int = Field(description="Byte offset start")
    text_end: int = Field(description="Byte offset end")
    quote: str = Field(description="The exact text of the highlight")
    prefix: str = Field(description="Context before the quote")
    suffix: str = Field(description="Context after the quote")
    canonical_version: Optional[int] = Field(
        default=None, description="Canonical version (documents only)"
    )
    transcript_hash: Optional[str] = Field(
        default=None, description="Transcript hash (episodes/videos only)"
    )
    pdf_page_number: Optional[int] = Field(
        default=None, description="PDF page number (PDF anchors only)"
    )
    pdf_char_offset: Optional[int] = Field(
        default=None, description="PDF char offset (PDF anchors only)"
    )
    pdf_file_hash: Optional[str] = Field(
        default=None, description="PDF file hash (PDF anchors only)"
    )
    pdf_extraction_confidence: Optional[float] = Field(
        default=None, description="PDF extraction confidence (PDF anchors only)"
    )
    time_start: Optional[float] = Field(
        default=None, description="Start time in seconds (transcript anchors only)"
    )
    time_end: Optional[float] = Field(
        default=None, description="End time in seconds (transcript anchors only)"
    )
    color: str = Field(default="yellow", description="Highlight color")
    is_hidden: bool = Field(default=False, description="Whether highlight is hidden")
    is_detached: bool = Field(default=False, description="Whether highlight is detached")
    detached_reason: Optional[str] = Field(default=None, description="Reason for detachment")
    is_public: bool = Field(default=False, description="Whether highlight is public")
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "11111111-2222-3333-4444-555555555555",
                "user_id": "22222222-3333-4444-5555-666666666666",
                "media_type": "document",
                "media_id": "33333333-4444-5555-6666-777777777777",
                "anchor_type": "text",
                "text_start": 100,
                "text_end": 200,
                "quote": "example text",
                "prefix": "before ",
                "suffix": " after",
                "canonical_version": 1,
                "transcript_hash": None,
                "pdf_page_number": None,
                "pdf_char_offset": None,
                "pdf_file_hash": None,
                "pdf_extraction_confidence": None,
                "time_start": None,
                "time_end": None,
                "color": "yellow",
                "is_hidden": False,
                "is_detached": False,
                "detached_reason": None,
                "is_public": False,
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        }
    }


class HighlightDetail(HighlightSummary):
    """Detailed representation of a highlight (same as summary for Phase 1).

    In Phase 1, highlight detail is the same as summary. Future phases may add
    additional fields like related annotations, links, etc.
    """

    pass


class AnnotationSummary(BaseModel):
    """Internal summary representation of an annotation (service layer).

    This schema is used internally by services and represents an annotation with
    raw UUID (not typed ID). API responses will convert this to typed ID format
    during serialization.

    Attributes:
        id: Raw annotation UUID (not typed ID; conversion happens at API boundary)
        user_id: Raw user UUID (creator)
        highlight_id: Raw highlight UUID (the highlight being annotated)
        content: The annotation text content
        is_public: Whether annotation is shared publicly
        created_at: UTC timestamp of creation
        updated_at: UTC timestamp of last update
    """

    id: UUID = Field(description="Raw annotation UUID")
    user_id: UUID = Field(description="Raw user UUID (creator)")
    highlight_id: UUID = Field(description="Raw highlight UUID")
    content: str = Field(description="Annotation text content")
    is_public: bool = Field(default=False, description="Whether annotation is public")
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "44444444-5555-6666-7777-888888888888",
                "user_id": "22222222-3333-4444-5555-666666666666",
                "highlight_id": "11111111-2222-3333-4444-555555555555",
                "content": "This is an important passage.",
                "is_public": False,
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        }
    }


class AnnotationDetail(AnnotationSummary):
    """Detailed representation of an annotation (same as summary for Phase 1).

    In Phase 1, annotation detail is the same as summary. Future phases may add
    additional fields like related highlights, links, etc.
    """

    pass


# ============================================================================
# API LAYER SCHEMAS
# ============================================================================


class CreateHighlightRequest(BaseModel):
    """Request body for POST /highlights.

    Accepts a simple byte-range anchor (text_start, text_end) which will be
    validated and mapped to the richer internal anchor format by the route handler.

    Attributes:
        document_id: Typed document ID (doc_<uuid>)
        byte_start: Byte offset start in canonical_text (>= 0)
        byte_end: Byte offset end in canonical_text (> byte_start)
    """

    document_id: str = Field(description="Typed document ID (doc_<uuid>)")
    byte_start: int = Field(ge=0, description="Byte offset start (>= 0)")
    byte_end: int = Field(gt=0, description="Byte offset end (> byte_start)")

    @field_validator("byte_end")
    @classmethod
    def validate_byte_range(cls, v: int, info) -> int:
        """Ensure byte_end > byte_start."""
        if "byte_start" in info.data and v <= info.data["byte_start"]:
            raise ValueError("byte_end must be greater than byte_start")
        return v


class HighlightItem(BaseModel):
    """API response item for a single highlight (used in list responses).

    All IDs are typed (e.g., hl_<uuid>, doc_<uuid>).

    Attributes:
        id: Typed highlight ID (hl_<uuid>)
        document_id: Typed document ID (doc_<uuid>)
        byte_start: Byte offset start in canonical_text
        byte_end: Byte offset end in canonical_text
        created_at: UTC timestamp of creation
        updated_at: UTC timestamp of last update
    """

    id: str = Field(description="Typed highlight ID (hl_<uuid>)")
    document_id: str = Field(description="Typed document ID (doc_<uuid>)")
    byte_start: int = Field(description="Byte offset start")
    byte_end: int = Field(description="Byte offset end")
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: Optional[datetime] = Field(default=None, description="UTC timestamp of last update")


class HighlightListResponse(BaseModel):
    """API response for list highlights endpoints (with pagination).

    Attributes:
        items: List of HighlightItem objects
        next_cursor: Opaque cursor for next page, or null if at end
        has_more: True if more pages exist, False otherwise
    """

    items: list[HighlightItem] = Field(description="List of highlights")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    has_more: bool = Field(description="Whether more items exist")
