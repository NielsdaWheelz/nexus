"""Cursor-based pagination primitives and utilities.

This module provides canonical pagination infrastructure for all list endpoints:
- Cursor encoding/decoding with base64url
- PaginationParams dependency for FastAPI
- PaginatedResponse generic model
- Constants for page size limits

All cursors are opaque and unguessable, encoding only keyset values needed for
stable ordering across pages (typically created_at + id).

Spec reference:
- spec/api_contracts.md §4 (list response shape, pagination)
"""

import base64
import json
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from app.core.errors import ValidationAppError

T = TypeVar("T")

# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_PAGE_SIZE = 20
"""Default number of items returned per page."""

MAX_PAGE_SIZE = 100
"""Maximum allowed page size to prevent DoS attacks."""

# ============================================================================
# PAGINATION RESPONSE MODEL
# ============================================================================


class PaginatedResponse(BaseModel, Generic[T]):
    """Canonical paginated list response shape.

    All list endpoints MUST return this shape or a subclass.

    Attributes:
        items: Array of typed resources (0 to limit items)
        next_cursor: Opaque base64 cursor for next page, or None if end reached
        has_more: True if more pages exist, False otherwise

    Example:
        {
            "items": [...],
            "next_cursor": "eyJjcmVhdGVkX2F0IjogIjIwMjUtMDEtMDFUMTI6MDA6MDBaIiwgImlkIjogImRvY18xMjM0In0=",
            "has_more": true
        }
    """

    items: list[T]
    next_cursor: str | None = None
    has_more: bool


# ============================================================================
# PAGINATION PARAMETERS
# ============================================================================


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints.

    All list endpoints MUST accept these parameters:
    - limit: Results per page (1 to MAX_PAGE_SIZE, default DEFAULT_PAGE_SIZE)
    - cursor: Opaque cursor from previous next_cursor (null to start from beginning)

    Attributes:
        limit: Number of items per page
        cursor: Opaque cursor for continuation
    """

    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    """Number of items to return (1–100, default 20)."""

    cursor: str | None = Field(default=None)
    """Opaque cursor from previous next_cursor response (null to start)."""

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        """Ensure limit is within valid range.

        Args:
            v: Limit value from request

        Returns:
            Validated limit value

        Raises:
            ValidationAppError: If limit < 1 or limit > MAX_PAGE_SIZE
        """
        if v < 1:
            raise ValidationAppError(
                message=f"Limit must be at least 1, got {v}",
                details={"field": "limit", "min": 1, "value": v},
            )
        if v > MAX_PAGE_SIZE:
            raise ValidationAppError(
                message=f"Limit cannot exceed {MAX_PAGE_SIZE}, got {v}",
                details={"field": "limit", "max": MAX_PAGE_SIZE, "value": v},
            )
        return v


# ============================================================================
# CURSOR ENCODING / DECODING
# ============================================================================


def encode_cursor(payload: dict[str, Any]) -> str:
    """Encode opaque cursor from payload dict.

    Encoding process:
    1. Serialize payload to JSON
    2. Encode JSON to UTF-8 bytes
    3. Base64url encode (no padding)
    4. Result is opaque and unguessable

    The cursor MUST encode an ordered keyset for stable pagination:
    Typically: {"created_at": "<iso8601>", "id": "<uuid>"}

    Args:
        payload: Dict to encode (typically keyset for sorting)

    Returns:
        Opaque base64url-encoded cursor string

    Example:
        >>> cursor = encode_cursor({"created_at": "2025-01-01T12:00:00Z", "id": "doc_123"})
        >>> cursor
        'eyJjcmVhdGVkX2F0IjogIjIwMjUtMDEtMDFUMTI6MDA6MDBaIiwgImlkIjogImRvY18xMjMifQ'
    """
    try:
        # Serialize to JSON (compact, no spaces)
        json_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        # Encode to UTF-8 bytes
        json_bytes = json_str.encode("utf-8")
        # Base64url encode without padding
        b64_bytes = base64.urlsafe_b64encode(json_bytes).rstrip(b"=")
        # Decode bytes to string for return
        return b64_bytes.decode("ascii")
    except (TypeError, ValueError) as e:
        # Payload not JSON serializable (internal error, not client error)
        raise ValueError(f"Cannot encode cursor payload: {e}") from e


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode opaque cursor to payload dict.

    Decoding process:
    1. Validate base64url format
    2. Add padding if needed
    3. Base64url decode
    4. Parse JSON
    5. Validate result is dict

    Any failure (invalid base64, invalid JSON, wrong type) raises ValidationAppError.

    Args:
        cursor: Opaque base64url-encoded cursor string

    Returns:
        Decoded payload dict (typically keyset)

    Raises:
        ValidationAppError: If cursor is invalid (bad base64, bad JSON, not dict, empty)

    Example:
        >>> payload = decode_cursor('eyJjcmVhdGVkX2F0IjogIjIwMjUtMDEtMDFUMTI6MDA6MDBaIiwgImlkIjogImRvY18xMjMifQ')
        >>> payload
        {'created_at': '2025-01-01T12:00:00Z', 'id': 'doc_123'}
    """
    if not cursor:
        raise ValidationAppError(
            message="Cursor cannot be empty",
            details={"reason": "empty_cursor"},
        )

    try:
        # Add padding back (base64url should use = for padding, but we strip it)
        # Add back padding to nearest multiple of 4
        padding = (4 - len(cursor) % 4) % 4
        padded_cursor = cursor + "=" * padding

        # Base64url decode
        json_bytes = base64.urlsafe_b64decode(padded_cursor)

        # Decode UTF-8
        json_str = json_bytes.decode("utf-8")

        # Parse JSON
        payload = json.loads(json_str)

        # Validate result is dict
        if not isinstance(payload, dict):
            raise ValidationAppError(
                message="Cursor payload must be an object (dict), not array or scalar",
                details={"reason": "invalid_payload_type", "type": type(payload).__name__},
            )

        # Validate not empty
        if not payload:
            raise ValidationAppError(
                message="Cursor payload cannot be empty",
                details={"reason": "empty_payload"},
            )

        return payload

    except ValidationAppError:
        # Re-raise validation errors as-is
        raise
    except (ValueError, json.JSONDecodeError) as e:
        # Base64 or JSON decode failed
        raise ValidationAppError(
            message="Invalid cursor format (must be valid base64url-encoded JSON)",
            details={"reason": "invalid_format", "error": str(e)},
        ) from e
    except Exception as e:
        # Catch all other errors (UTF-8 decode, etc.)
        raise ValidationAppError(
            message="Failed to decode cursor",
            details={"reason": "decode_error", "error": str(e)},
        ) from e
