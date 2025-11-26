"""Conversation and message management routes.

This module provides:
- POST /conversations: Create conversation
- GET /conversations: List conversations with pagination
- GET /conversations/{conversation_id}: Get conversation detail
- GET /conversations/{conversation_id}/messages: List messages with pagination
- POST /conversations/{conversation_id}/messages: Append user message

All endpoints require authentication via Clerk JWT.

Spec reference:
- PR 5.1 specification (conversation HTTP layer)
- spec/api_contracts.md (typed IDs, pagination, error envelopes)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth.deps import rate_limit_authenticated
from app.core.ids import from_api_id, to_api_id
from app.core.pagination import PaginationParams
from app.db.session import get_session as _get_session
from app.models.user import User
from app.schemas.conversations import (
    ConversationDetail,
    ConversationListItem,
    ConversationListResponse,
    CreateConversationRequest,
    CreateMessageRequest,
    MessageListItem,
    MessageListResponse,
)
from app.services.conversations import (
    append_user_message,
    create_conversation_for_user,
    get_conversation_for_user,
    list_conversations_for_user,
    list_messages_for_conversation,
)
from app.services.documents import get_document_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "",
    response_model=ConversationDetail,
    status_code=201,
    summary="Create conversation",
    description="Create a new conversation with optional document reference.",
)
async def create_conversation(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    body: CreateConversationRequest,
) -> ConversationDetail:
    """Create a new conversation.

    Optionally attach the conversation to a specific document. If root_document_id
    is provided, it must be owned by the authenticated user.

    Args:
        current_user: Authenticated user
        body: Request body with title and optional root_document_id

    Returns:
        ConversationDetail with typed IDs

    Raises:
        ValidationAppError (422): If title is invalid
        NotFoundError (404): If root_document_id provided but document not found or not owned

    Example:
        >>> POST /conversations
        >>> {
        ...     "title": "ML Discussion",
        ...     "root_document_id": "doc_11111111-2222-3333-4444-555555555555"
        ... }
        >>> {
        ...     "id": "conv_11111111-2222-3333-4444-555555555555",
        ...     "title": "ML Discussion",
        ...     "root_document_id": "doc_11111111-2222-3333-4444-555555555555",
        ...     "last_message_at": null,
        ...     "created_at": "2025-01-01T12:00:00Z",
        ...     "updated_at": "2025-01-01T12:00:00Z"
        ... }
    """
    # Parse and validate root_document_id if provided
    root_document_uuid = None
    if body.root_document_id:
        try:
            doc_type, doc_uuid = from_api_id(body.root_document_id)
            if doc_type != "document":
                from app.core.errors import ValidationAppError

                raise ValidationAppError(
                    message="root_document_id must be a document ID",
                    details={"field": "root_document_id"},
                )
            root_document_uuid = doc_uuid

            # Validate document ownership (this also checks it's not deleted)
            get_document_for_user(
                session=session,
                user=current_user,
                document_id=doc_uuid,
            )
        except ValueError as e:
            from app.core.errors import ValidationAppError

            raise ValidationAppError(
                message=f"Invalid root_document_id format: {str(e)}",
                details={"field": "root_document_id"},
            ) from e

    # Create conversation
    conversation = create_conversation_for_user(
        session=session,
        user_id=current_user.id,
        title=body.title,
        root_document_id=root_document_uuid,
    )

    # Convert to API response
    return ConversationDetail(
        id=to_api_id("conversation", conversation.id),
        title=conversation.title,
        root_document_id=(
            to_api_id("document", root_document_uuid) if root_document_uuid else None
        ),
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get(
    "",
    response_model=ConversationListResponse,
    status_code=200,
    summary="List conversations",
    description="List user's conversations with cursor-based pagination.",
)
async def list_conversations(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> ConversationListResponse:
    """List conversations for authenticated user.

    Returns paginated list with cursor-based pagination. Ordering is deterministic:
    ORDER BY last_message_at DESC NULLS LAST, created_at DESC, id DESC.

    Args:
        current_user: Authenticated user
        limit: Number of items per page (1-100, default 20)
        cursor: Opaque cursor for continuation (null to start from beginning)

    Returns:
        ConversationListResponse with list of conversations, next_cursor, has_more

    Example:
        >>> GET /conversations?limit=20&cursor=null
        >>> {
        ...     "items": [...],
        ...     "next_cursor": "...",
        ...     "has_more": true
        ... }
    """
    pagination_params = PaginationParams(limit=limit, cursor=cursor)

    page = list_conversations_for_user(
        session=session,
        user_id=current_user.id,
        pagination_params=pagination_params,
    )

    return ConversationListResponse(
        items=[
            ConversationListItem(
                id=to_api_id("conversation", conv.id),
                title=conv.title,
                root_document_id=None,  # Not populated in this PR
                last_message_at=conv.last_message_at,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
            for conv in page.items
        ],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    status_code=200,
    summary="Get conversation",
    description="Retrieve a single conversation by ID.",
)
async def get_conversation(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    conversation_id: str,
) -> ConversationDetail:
    """Retrieve conversation detail.

    Enforces ACL: user can only retrieve their own conversations (404 otherwise).

    Args:
        current_user: Authenticated user
        conversation_id: Typed conversation ID (conv_<uuid>)

    Returns:
        ConversationDetail with typed IDs

    Raises:
        ValidationAppError (422): If conversation_id format is invalid
        NotFoundError (404): If conversation not found, belongs to another user, or is deleted

    Example:
        >>> GET /conversations/conv_11111111-2222-3333-4444-555555555555
        >>> {
        ...     "id": "conv_11111111-2222-3333-4444-555555555555",
        ...     "title": "ML Discussion",
        ...     "root_document_id": null,
        ...     "last_message_at": null,
        ...     "created_at": "2025-01-01T12:00:00Z",
        ...     "updated_at": "2025-01-01T12:00:00Z"
        ... }
    """
    # Parse conversation_id
    try:
        conv_type, conv_uuid = from_api_id(conversation_id)
        if conv_type != "conversation":
            from app.core.errors import ValidationAppError

            raise ValidationAppError(
                message="conversation_id must be a conversation ID",
                details={"field": "conversation_id"},
            )
    except ValueError as e:
        from app.core.errors import ValidationAppError

        raise ValidationAppError(
            message=f"Invalid conversation_id format: {str(e)}",
            details={"field": "conversation_id"},
        ) from e

    # Get conversation (enforces ACL)
    conversation = get_conversation_for_user(
        session=session,
        user_id=current_user.id,
        conversation_id=conv_uuid,
    )

    return ConversationDetail(
        id=to_api_id("conversation", conversation.id),
        title=conversation.title,
        root_document_id=None,  # Not populated in this PR
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    status_code=200,
    summary="List messages",
    description="List messages in a conversation with cursor-based pagination.",
)
async def list_messages(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> MessageListResponse:
    """List messages in a conversation.

    Enforces ACL: user can only list messages from their own conversations.
    Ordering is deterministic: ORDER BY created_at ASC, id ASC.

    Args:
        current_user: Authenticated user
        conversation_id: Typed conversation ID (conv_<uuid>)
        limit: Number of items per page (1-100, default 50)
        cursor: Opaque cursor for continuation (null to start from beginning)

    Returns:
        MessageListResponse with list of messages, next_cursor, has_more

    Raises:
        ValidationAppError (422): If conversation_id or cursor format is invalid
        NotFoundError (404): If conversation not found, belongs to another user, or is deleted

    Example:
        >>> GET /conversations/conv_11111111-2222-3333-4444-555555555555/messages?limit=50
        >>> {
        ...     "items": [...],
        ...     "next_cursor": null,
        ...     "has_more": false
        ... }
    """
    # Parse conversation_id
    try:
        conv_type, conv_uuid = from_api_id(conversation_id)
        if conv_type != "conversation":
            from app.core.errors import ValidationAppError

            raise ValidationAppError(
                message="conversation_id must be a conversation ID",
                details={"field": "conversation_id"},
            )
    except ValueError as e:
        from app.core.errors import ValidationAppError

        raise ValidationAppError(
            message=f"Invalid conversation_id format: {str(e)}",
            details={"field": "conversation_id"},
        ) from e

    pagination_params = PaginationParams(limit=limit, cursor=cursor)

    # List messages (enforces ACL via get_conversation_for_user)
    page = list_messages_for_conversation(
        session=session,
        user_id=current_user.id,
        conversation_id=conv_uuid,
        pagination_params=pagination_params,
    )

    return MessageListResponse(
        items=[
            MessageListItem(
                id=to_api_id("message", msg.id),
                role=msg.role,
                content=msg.content,
                created_at=msg.created_at,
            )
            for msg in page.items
        ],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageListItem,
    status_code=201,
    summary="Append user message",
    description="Append a user message to a conversation.",
)
async def create_message(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
    session: Annotated[Session, Depends(_get_session)],
    conversation_id: str,
    body: CreateMessageRequest,
) -> MessageListItem:
    """Append a user message to a conversation.

    This endpoint only creates user messages. Assistant messages are created
    separately by LLM integration (not in PR 5.1 scope).

    Args:
        current_user: Authenticated user
        conversation_id: Typed conversation ID (conv_<uuid>)
        body: Request body with message content

    Returns:
        MessageListItem with typed message ID

    Raises:
        ValidationAppError (422): If conversation_id format or content is invalid
        NotFoundError (404): If conversation not found, belongs to another user, or is deleted

    Example:
        >>> POST /conversations/conv_11111111-2222-3333-4444-555555555555/messages
        >>> {
        ...     "content": "What is machine learning?"
        ... }
        >>> {
        ...     "id": "msg_11111111-2222-3333-4444-555555555555",
        ...     "role": "user",
        ...     "content": "What is machine learning?",
        ...     "created_at": "2025-01-01T12:10:00Z"
        ... }
    """
    # Parse conversation_id
    try:
        conv_type, conv_uuid = from_api_id(conversation_id)
        if conv_type != "conversation":
            from app.core.errors import ValidationAppError

            raise ValidationAppError(
                message="conversation_id must be a conversation ID",
                details={"field": "conversation_id"},
            )
    except ValueError as e:
        from app.core.errors import ValidationAppError

        raise ValidationAppError(
            message=f"Invalid conversation_id format: {str(e)}",
            details={"field": "conversation_id"},
        ) from e

    # Create message (enforces ACL via get_conversation_for_user)
    message = append_user_message(
        session=session,
        user_id=current_user.id,
        conversation_id=conv_uuid,
        content=body.content,
    )

    return MessageListItem(
        id=to_api_id("message", message.id),
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )
