"""Pydantic schemas for conversation and message endpoints.

This module defines request/response schemas for all conversation-related endpoints.
All schemas use Pydantic v2 for validation and serialization.

Internal schemas (used in services) work with raw UUIDs. API response schemas
convert to typed IDs during serialization.

Spec reference:
- spec/api_contracts.md (typed IDs, response shapes)
- spec/schemas/conversations.md (conversation schema)
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# INTERNAL SCHEMAS (service layer, raw UUIDs)
# =============================================================================


class ConversationInternal(BaseModel):
    """Internal conversation representation (service layer).

    Uses raw UUIDs; API layer converts to typed ID format.
    """

    id: UUID = Field(description="Raw conversation UUID")
    user_id: UUID = Field(description="Raw user UUID (owner)")
    title: Optional[str] = Field(default=None, description="Conversation title")
    root_document_id: Optional[UUID] = Field(
        default=None, description="Raw document UUID if conversation is tied to a specific document"
    )
    last_message_at: Optional[datetime] = Field(
        default=None, description="Timestamp of last message"
    )
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")


class MessageInternal(BaseModel):
    """Internal message representation (service layer).

    Uses raw UUIDs; API layer converts to typed ID format.
    """

    id: UUID = Field(description="Raw message UUID")
    conversation_id: UUID = Field(description="Raw conversation UUID")
    role: Literal["user", "assistant"] = Field(description="Message role")
    content: str = Field(description="Message content")
    created_at: datetime = Field(description="UTC timestamp of creation")


# =============================================================================
# API SCHEMAS (response/request, typed IDs)
# =============================================================================


class ConversationListItem(BaseModel):
    """API response schema for a single conversation in list endpoint.

    All IDs are typed (conv_<uuid>), timestamps are ISO8601 UTC.
    """

    id: str = Field(description="Typed conversation ID (conv_<uuid>)")
    title: Optional[str] = Field(default=None, description="Conversation title")
    root_document_id: Optional[str] = Field(
        default=None,
        description="Typed document ID (doc_<uuid>) if conversation is tied to a specific document",
    )
    last_message_at: Optional[datetime] = Field(
        default=None, description="Timestamp of last message (for sorting)"
    )
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "conv_11111111-2222-3333-4444-555555555555",
                "title": "Discussing machine learning",
                "root_document_id": "doc_22222222-3333-4444-5555-666666666666",
                "last_message_at": "2025-01-01T12:30:00Z",
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:30:00Z",
            }
        }
    }


class ConversationDetail(BaseModel):
    """API response schema for GET /conversations/{id}.

    Same fields as ConversationListItem.
    """

    id: str = Field(description="Typed conversation ID (conv_<uuid>)")
    title: Optional[str] = Field(default=None, description="Conversation title")
    root_document_id: Optional[str] = Field(
        default=None,
        description="Typed document ID (doc_<uuid>) if conversation is tied to a specific document",
    )
    last_message_at: Optional[datetime] = Field(
        default=None, description="Timestamp of last message"
    )
    created_at: datetime = Field(description="UTC timestamp of creation")
    updated_at: datetime = Field(description="UTC timestamp of last update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "conv_11111111-2222-3333-4444-555555555555",
                "title": "Discussing machine learning",
                "root_document_id": "doc_22222222-3333-4444-5555-666666666666",
                "last_message_at": "2025-01-01T12:30:00Z",
                "created_at": "2025-01-01T12:00:00Z",
                "updated_at": "2025-01-01T12:30:00Z",
            }
        }
    }


class ConversationListResponse(BaseModel):
    """API response for GET /conversations (list conversations).

    Returns paginated list of user's conversations with cursor-based pagination.
    """

    items: list[ConversationListItem] = Field(description="List of conversations")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    has_more: bool = Field(description="Whether more pages exist")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "conv_11111111-2222-3333-4444-555555555555",
                        "title": "Discussing machine learning",
                        "root_document_id": "doc_22222222-3333-4444-5555-666666666666",
                        "last_message_at": "2025-01-01T12:30:00Z",
                        "created_at": "2025-01-01T12:00:00Z",
                        "updated_at": "2025-01-01T12:30:00Z",
                    },
                    {
                        "id": "conv_33333333-4444-5555-6666-777777777777",
                        "title": None,
                        "root_document_id": None,
                        "last_message_at": None,
                        "created_at": "2025-01-02T10:00:00Z",
                        "updated_at": "2025-01-02T10:00:00Z",
                    },
                ],
                "next_cursor": None,
                "has_more": False,
            }
        }
    }


class MessageListItem(BaseModel):
    """API response schema for a single message in list endpoint.

    All IDs are typed (msg_<uuid>), timestamps are ISO8601 UTC.
    """

    id: str = Field(description="Typed message ID (msg_<uuid>)")
    role: Literal["user", "assistant"] = Field(description="Message role")
    content: str = Field(description="Message content")
    created_at: datetime = Field(description="UTC timestamp of creation")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "msg_11111111-2222-3333-4444-555555555555",
                "role": "user",
                "content": "What is the capital of France?",
                "created_at": "2025-01-01T12:10:00Z",
            }
        }
    }


class MessageListResponse(BaseModel):
    """API response for GET /conversations/{id}/messages.

    Returns paginated list of messages in conversation with cursor-based pagination.
    """

    items: list[MessageListItem] = Field(description="List of messages")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for next page")
    has_more: bool = Field(description="Whether more pages exist")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "msg_11111111-2222-3333-4444-555555555555",
                        "role": "user",
                        "content": "What is the capital of France?",
                        "created_at": "2025-01-01T12:10:00Z",
                    },
                    {
                        "id": "msg_22222222-3333-4444-5555-666666666666",
                        "role": "assistant",
                        "content": "The capital of France is Paris.",
                        "created_at": "2025-01-01T12:10:05Z",
                    },
                ],
                "next_cursor": None,
                "has_more": False,
            }
        }
    }


# =============================================================================
# REQUEST SCHEMAS
# =============================================================================


class CreateConversationRequest(BaseModel):
    """Request schema for POST /conversations.

    Creates a new conversation optionally tied to a document.
    """

    title: Optional[str] = Field(
        default=None, description="Optional conversation title (max 512 characters)"
    )
    root_document_id: Optional[str] = Field(
        default=None,
        description="Optional typed document ID (doc_<uuid>) to tie conversation to a document",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "Discussing machine learning algorithms",
                    "root_document_id": "doc_11111111-2222-3333-4444-555555555555",
                },
                {
                    "title": "General questions",
                    "root_document_id": None,
                },
                {
                    "root_document_id": "doc_11111111-2222-3333-4444-555555555555",
                },
            ]
        }
    }


class CreateMessageRequest(BaseModel):
    """Request schema for POST /conversations/{id}/messages.

    Appends a user message to a conversation.
    """

    content: str = Field(
        ..., min_length=1, max_length=10000, description="Message content (required, non-empty)"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "content": "What is machine learning?",
            }
        }
    }
