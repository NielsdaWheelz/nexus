"""Pydantic schemas for reader endpoints.

This module defines request/response schemas for all reader (reading session) endpoints.
All schemas use Pydantic v2 for validation and serialization.

Internal schemas (used in services) work with raw UUIDs. API response schemas
convert to typed IDs during serialization.

Spec reference:
- PR 5.1 specification (reading sessions)
- spec/api_contracts.md (typed IDs, response shapes)
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReaderInternal(BaseModel):
    """Internal representation of a reader (service layer).

    This schema is used internally by services and represents a reader with
    raw UUIDs (not typed IDs). API responses will convert to typed ID format
    during serialization.

    Attributes:
        id: Raw reader UUID
        user_id: Raw user UUID
        document_id: Raw document UUID
        current_position: Byte offset into canonical text (None = not started)
        last_read_at: Timestamp of last read activity
        created_at: UTC timestamp when reader was created
        updated_at: UTC timestamp of last update
    """

    id: UUID = Field(description="Raw reader UUID")
    user_id: UUID = Field(description="Raw user UUID")
    document_id: UUID = Field(description="Raw document UUID")
    current_position: int | None = Field(
        default=None, description="Byte offset into canonical text (None = not started)"
    )
    last_read_at: datetime | None = Field(default=None, description="Timestamp of last read")
    created_at: datetime = Field(description="UTC timestamp of reader creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")

    model_config = {"from_attributes": True}


class ReaderResponse(BaseModel):
    """API response for a reader (reading session).

    Returns a reader with typed ID format and full session state.

    Attributes:
        id: Typed reader ID (format: rdr_<uuid>)
        document_id: Typed document ID (format: doc_<uuid>)
        current_position: Byte offset into canonical text
        last_read_at: Timestamp of last read activity
        created_at: UTC timestamp of reader creation
        updated_at: UTC timestamp of last update
    """

    id: str = Field(description="Typed reader ID (rdr_<uuid>)")
    document_id: str = Field(description="Typed document ID (doc_<uuid>)")
    current_position: int | None = Field(
        default=None, description="Byte offset into canonical text"
    )
    last_read_at: datetime | None = Field(default=None, description="Timestamp of last read")
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "rdr_11111111-2222-3333-4444-555555555555",
                "document_id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "current_position": 12345,
                "last_read_at": "2025-01-01T12:00:00Z",
                "created_at": "2025-01-01T10:00:00Z",
                "updated_at": "2025-01-01T12:00:00Z",
            }
        }
    }


class ReaderListResponse(BaseModel):
    """API response for listing readers with pagination.

    Returns a paginated list of readers for a document.

    Attributes:
        items: List of ReaderResponse objects
        next_cursor: Cursor for next page (None if no more results)
        has_more: Boolean indicating if more results available
    """

    items: list[ReaderResponse] = Field(description="List of readers")
    next_cursor: str | None = Field(default=None, description="Cursor for next page")
    has_more: bool = Field(description="Whether more results are available")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "rdr_11111111-2222-3333-4444-555555555555",
                        "document_id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                        "current_position": 12345,
                        "last_read_at": "2025-01-01T12:00:00Z",
                        "created_at": "2025-01-01T10:00:00Z",
                        "updated_at": "2025-01-01T12:00:00Z",
                    }
                ],
                "next_cursor": "eyJjcmVhdGVkX2F0IjogIjIwMjUtMDEtMDFUMDk6MDA6MDBaIiwgImlkIjogIjExMTExMTExLTIyMjItMzMzMy00NDQ0LTU1NTU1NTU1NTU1NSJ9",
                "has_more": True,
            }
        }
    }


class CreateReaderRequest(BaseModel):
    """API request for creating a reader.

    Accepts a document_id and creates a reading session for the authenticated user.
    GET-or-create semantics: returns existing reader if already created.

    Attributes:
        document_id: Typed document ID (format: doc_<uuid>)
    """

    document_id: str = Field(description="Typed document ID (doc_<uuid>)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "document_id": "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            }
        }
    }


class UpdateReaderRequest(BaseModel):
    """API request for updating a reader.

    Updates the reading position and last_read_at timestamp.

    Attributes:
        current_position: Byte offset into canonical text (must be >= 0)
    """

    current_position: int = Field(ge=0, description="Byte offset into canonical text")

    model_config = {
        "json_schema_extra": {
            "example": {
                "current_position": 12345,
            }
        }
    }
