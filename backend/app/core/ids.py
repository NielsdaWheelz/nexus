"""Typed ID utilities for converting between database UUIDs and API format.

This module provides helpers to convert between:
- Internal: Raw UUID (e.g., 11111111-2222-3333-4444-555555555555)
- External API: Typed ID (e.g., doc_11111111-2222-3333-4444-555555555555)

All IDs stored in the database are raw UUIDs. API responses use typed IDs.
Typed ID format: <prefix>_<uuid>

Prefix registry:
- doc: Document
- usr: User
- hlght: Highlight
- ann: Annotation
- conv: Conversation
- msg: Message
- lib: Library
- lnk: Link
- chunk: Chunk (ContentChunk)
"""

from typing import Literal
from uuid import UUID

# Type for object types
ObjectType = Literal[
    "document",
    "user",
    "highlight",
    "annotation",
    "conversation",
    "message",
    "library",
    "link",
    "chunk",
]

# Mapping from object type to prefix
TYPE_TO_PREFIX: dict[ObjectType, str] = {
    "document": "doc",
    "user": "usr",
    "highlight": "hlght",
    "annotation": "ann",
    "conversation": "conv",
    "message": "msg",
    "library": "lib",
    "link": "lnk",
    "chunk": "chunk",
}

# Reverse mapping from prefix to object type
PREFIX_TO_TYPE: dict[str, ObjectType] = {v: k for k, v in TYPE_TO_PREFIX.items()}


def to_api_id(object_type: ObjectType, db_uuid: UUID) -> str:
    """Convert database UUID to typed API ID.

    Args:
        object_type: Type of object (e.g., "document", "user")
        db_uuid: Raw UUID from database

    Returns:
        Typed ID string (e.g., "doc_11111111-2222-3333-4444-555555555555")

    Raises:
        ValueError: If object_type is not recognized

    Example:
        >>> to_api_id("document", UUID("11111111-2222-3333-4444-555555555555"))
        'doc_11111111-2222-3333-4444-555555555555'
    """
    if object_type not in TYPE_TO_PREFIX:
        raise ValueError(f"Unknown object type: {object_type}")

    prefix = TYPE_TO_PREFIX[object_type]
    return f"{prefix}_{db_uuid}"


def from_api_id(api_id: str) -> tuple[ObjectType, UUID]:
    """Parse typed API ID to (type, uuid).

    Args:
        api_id: Typed ID string (e.g., "doc_11111111-2222-3333-4444-555555555555")

    Returns:
        Tuple of (object_type, uuid)

    Raises:
        ValueError: If API ID format is invalid, unknown prefix, or invalid UUID

    Example:
        >>> from_api_id("doc_11111111-2222-3333-4444-555555555555")
        ('document', UUID('11111111-2222-3333-4444-555555555555'))
    """
    parts = api_id.split("_", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid API ID format: {api_id}")

    prefix, uuid_str = parts

    if prefix not in PREFIX_TO_TYPE:
        raise ValueError(f"Unknown prefix: {prefix}")

    try:
        uuid_obj = UUID(uuid_str)
    except ValueError as e:
        raise ValueError(f"Invalid UUID: {uuid_str}") from e

    object_type = PREFIX_TO_TYPE[prefix]
    return object_type, uuid_obj
