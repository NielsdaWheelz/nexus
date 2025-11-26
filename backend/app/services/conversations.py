"""Conversation service layer for all conversation and message operations.

This module implements the core business logic for conversation management:
- Conversation creation with optional document attachment
- Conversation retrieval with ownership/visibility checks
- Conversation listing with cursor pagination
- User message appending with conversation update

All functions enforce:
- User ownership (conversations belong to authenticated user)
- Soft delete rules (deleted_at check)
- Message immutability (messages never updated, only created)
- Pagination determinism (ORDER BY last_message_at DESC NULLS LAST, created_at DESC, id DESC)

Spec reference:
- PR 5.1 specification (conversation service layer)
- spec/api_contracts.md (typed IDs, pagination, error envelopes)
- spec/acl.md (visibility rules)
- spec/schemas/conversations.md (conversation schema)
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, desc, nulls_last, or_
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import PaginatedResponse, PaginationParams, decode_cursor, encode_cursor
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message
from app.schemas.conversations import ConversationInternal, MessageInternal


def create_conversation_for_user(
    *,
    session: Session,
    user_id: UUID,
    title: str | None = None,
    root_document_id: UUID | None = None,
) -> Conversation:
    """Create a new conversation for a user with optional document reference.

    Args:
        session: SQLAlchemy database session
        user_id: User ID (owner of conversation)
        title: Optional conversation title
        root_document_id: Optional document UUID (must belong to user if provided)

    Returns:
        Newly created Conversation ORM object

    Raises:
        NotFoundError (404): If document_id is provided but not found or doesn't belong to user
        ValidationAppError: If arguments are invalid

    Example:
        >>> conv = create_conversation_for_user(
        ...     session=db,
        ...     user_id=user_id,
        ...     title="Discussion about ML",
        ...     root_document_id=doc_uuid,
        ... )
    """
    # If root_document_id provided, validate it belongs to user and is not deleted
    if root_document_id is not None:
        doc = (
            session.query(Document)
            .filter(
                and_(
                    Document.id == root_document_id,
                    Document.user_id == user_id,
                    Document.deleted_at.is_(None),
                )
            )
            .first()
        )

        if not doc:
            raise NotFoundError(
                message="Document not found",
                details={"resource_type": "document", "resource_id": str(root_document_id)},
            )

    # Create conversation
    now = datetime.now(timezone.utc)
    conversation = Conversation(
        user_id=user_id,
        title=title,
        created_at=now,
        updated_at=now,
    )

    session.add(conversation)
    session.flush()

    return conversation


def get_conversation_for_user(
    *,
    session: Session,
    user_id: UUID,
    conversation_id: UUID,
) -> Conversation:
    """Retrieve a conversation with ACL enforcement.

    Enforces:
    - Conversation exists
    - Conversation belongs to user
    - Conversation is not soft-deleted

    Args:
        session: SQLAlchemy database session
        user_id: User ID (for ACL check)
        conversation_id: Conversation UUID

    Returns:
        Conversation ORM object

    Raises:
        NotFoundError (404): If conversation not found, belongs to another user, or is deleted

    Example:
        >>> conv = get_conversation_for_user(
        ...     session=db,
        ...     user_id=user_id,
        ...     conversation_id=conv_uuid,
        ... )
    """
    conversation = (
        session.query(Conversation)
        .filter(
            and_(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
        )
        .first()
    )

    if not conversation:
        raise NotFoundError(
            message="Conversation not found",
            details={"resource_type": "conversation", "resource_id": str(conversation_id)},
        )

    return conversation


def list_conversations_for_user(
    *,
    session: Session,
    user_id: UUID,
    pagination_params: PaginationParams,
) -> PaginatedResponse[ConversationInternal]:
    """List conversations for a user with cursor pagination.

    Enforces:
    - Only returns conversations belonging to user
    - Excludes soft-deleted conversations
    - Deterministic ordering: ORDER BY last_message_at DESC NULLS LAST, created_at DESC, id DESC

    Args:
        session: SQLAlchemy database session
        user_id: User ID to filter by
        pagination_params: Pagination parameters (limit, cursor)

    Returns:
        PaginatedResponse with list of ConversationInternal objects, next_cursor, has_more

    Example:
        >>> page = list_conversations_for_user(
        ...     session=db,
        ...     user_id=user_id,
        ...     pagination_params=PaginationParams(limit=20, cursor=None),
        ... )
    """
    # Build base query
    query = session.query(Conversation).filter(
        and_(
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
    )

    # Apply cursor if provided
    if pagination_params.cursor:
        cursor_data = decode_cursor(pagination_params.cursor)
        last_message_at = cursor_data.get("last_message_at")
        last_created_at = cursor_data.get("created_at")
        last_id = cursor_data.get("id")

        if not all([last_created_at, last_id]):
            raise ValidationAppError(
                message="Invalid cursor format",
                details={"field": "cursor"},
            )

        # Continue from keyset
        query = (
            query.filter(
                or_(
                    Conversation.last_message_at
                    < (datetime.fromisoformat(last_message_at) if last_message_at else None),
                    and_(
                        Conversation.last_message_at
                        == (datetime.fromisoformat(last_message_at) if last_message_at else None),
                        Conversation.created_at < datetime.fromisoformat(last_created_at),
                    ),
                    and_(
                        Conversation.last_message_at
                        == (datetime.fromisoformat(last_message_at) if last_message_at else None),
                        Conversation.created_at == datetime.fromisoformat(last_created_at),
                        Conversation.id < UUID(last_id),
                    ),
                )
            )
            if last_message_at
            else query.filter(
                or_(
                    and_(
                        Conversation.created_at < datetime.fromisoformat(last_created_at),
                    ),
                    and_(
                        Conversation.created_at == datetime.fromisoformat(last_created_at),
                        Conversation.id < UUID(last_id),
                    ),
                )
            )
        )

    # Apply ordering: last_message_at DESC NULLS LAST, created_at DESC, id DESC
    query = query.order_by(
        nulls_last(desc(Conversation.last_message_at)),
        desc(Conversation.created_at),
        desc(Conversation.id),
    )

    # Fetch limit + 1 to determine has_more
    limit = min(pagination_params.limit, 100)
    conversations = query.limit(limit + 1).all()

    has_more = len(conversations) > limit
    if has_more:
        conversations = conversations[:limit]

    # Build next cursor
    next_cursor = None
    if has_more and conversations:
        last_conv = conversations[-1]
        next_cursor = encode_cursor(
            {
                "last_message_at": (
                    last_conv.last_message_at.isoformat() if last_conv.last_message_at else None
                ),
                "created_at": last_conv.created_at.isoformat(),
                "id": str(last_conv.id),
            }
        )

    # Convert to internal schema
    items = [
        ConversationInternal(
            id=conv.id,
            user_id=conv.user_id,
            title=conv.title,
            root_document_id=None,  # Not populated in this PR
            last_message_at=conv.last_message_at,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )
        for conv in conversations
    ]

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


def append_user_message(
    *,
    session: Session,
    user_id: UUID,
    conversation_id: UUID,
    content: str,
) -> Message:
    """Append a user message to a conversation and update conversation timestamps.

    This function:
    1. Validates conversation exists and belongs to user (404 if not)
    2. Validates content is non-empty (422 if empty)
    3. Creates message with role='user'
    4. Updates conversation.last_message_at and updated_at
    5. Flushes to database

    Args:
        session: SQLAlchemy database session
        user_id: User ID (for ACL check)
        conversation_id: Conversation UUID
        content: Message content (required, non-empty)

    Returns:
        Newly created Message ORM object with id set

    Raises:
        NotFoundError (404): If conversation not found, belongs to another user, or is deleted
        ValidationAppError (422): If content is empty or missing

    Example:
        >>> msg = append_user_message(
        ...     session=db,
        ...     user_id=user_id,
        ...     conversation_id=conv_uuid,
        ...     content="What is machine learning?",
        ... )
    """
    # Validate content
    if not content or not content.strip():
        raise ValidationAppError(
            message="Message content cannot be empty",
            details={"field": "content"},
        )

    # Get conversation (enforces ACL via get_conversation_for_user)
    conversation = get_conversation_for_user(
        session=session,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    # Create message
    now = datetime.now(timezone.utc)
    message = Message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=content,
        created_at=now,
        updated_at=now,
    )

    session.add(message)
    session.flush()

    # Update conversation timestamps
    conversation.last_message_at = now
    conversation.updated_at = now
    session.flush()

    return message


def list_messages_for_conversation(
    *,
    session: Session,
    user_id: UUID,
    conversation_id: UUID,
    pagination_params: PaginationParams,
) -> PaginatedResponse[MessageInternal]:
    """List messages in a conversation with cursor pagination.

    Enforces:
    - Conversation belongs to user (404 otherwise)
    - Only returns non-deleted messages
    - Deterministic ordering: ORDER BY created_at ASC, id ASC

    Args:
        session: SQLAlchemy database session
        user_id: User ID (for ACL check)
        conversation_id: Conversation UUID
        pagination_params: Pagination parameters (limit, cursor)

    Returns:
        PaginatedResponse with list of MessageInternal objects, next_cursor, has_more

    Raises:
        NotFoundError (404): If conversation not found, belongs to another user, or is deleted

    Example:
        >>> page = list_messages_for_conversation(
        ...     session=db,
        ...     user_id=user_id,
        ...     conversation_id=conv_uuid,
        ...     pagination_params=PaginationParams(limit=50, cursor=None),
        ... )
    """
    # Get conversation (enforces ACL)
    get_conversation_for_user(
        session=session,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    # Build base query
    query = session.query(Message).filter(
        and_(
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
        )
    )

    # Apply cursor if provided
    if pagination_params.cursor:
        cursor_data = decode_cursor(pagination_params.cursor)
        last_created_at = cursor_data.get("created_at")
        last_id = cursor_data.get("id")

        if not all([last_created_at, last_id]):
            raise ValidationAppError(
                message="Invalid cursor format",
                details={"field": "cursor"},
            )

        # Continue from keyset (ASC, so >)
        query = query.filter(
            or_(
                Message.created_at > datetime.fromisoformat(last_created_at),
                and_(
                    Message.created_at == datetime.fromisoformat(last_created_at),
                    Message.id > UUID(last_id),
                ),
            )
        )

    # Apply ordering: created_at ASC, id ASC
    query = query.order_by(Message.created_at.asc(), Message.id.asc())

    # Fetch limit + 1 to determine has_more
    limit = min(pagination_params.limit, 100)
    messages = query.limit(limit + 1).all()

    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]

    # Build next cursor
    next_cursor = None
    if has_more and messages:
        last_msg = messages[-1]
        next_cursor = encode_cursor(
            {
                "created_at": last_msg.created_at.isoformat(),
                "id": str(last_msg.id),
            }
        )

    # Convert to internal schema
    items = [
        MessageInternal(
            id=msg.id,
            conversation_id=msg.conversation_id,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
        )
        for msg in messages
    ]

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )
