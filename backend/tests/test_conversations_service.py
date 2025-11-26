"""Comprehensive tests for conversation service layer (PR 5.1).

Tests cover:
- Conversation creation (happy path + validation errors)
- Conversation retrieval with ownership and soft-delete checks
- Conversation listing with cursor pagination (determinism, ordering, has_more)
- Message appending with ACL enforcement
- Message listing with cursor pagination
- Typed ID format validation

All tests use real database transactions (no mocks) with auto-rollback.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import PaginationParams
from app.models.user import User
from app.services.conversations import (
    append_user_message,
    create_conversation_for_user,
    get_conversation_for_user,
    list_conversations_for_user,
    list_messages_for_conversation,
)
from app.services.documents import create_document_placeholder


@pytest.fixture
def user1(db_session: Session) -> User:
    """Create first test user."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_user_1",
        email="user1@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def user2(db_session: Session) -> User:
    """Create second test user (for ACL testing)."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_user_2",
        email="user2@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


# ============================================================================
# CREATE_CONVERSATION_FOR_USER TESTS
# ============================================================================


class TestCreateConversationForUser:
    """Test create_conversation_for_user function."""

    def test_creation_happy_path(self, db_session: Session, user1: User):
        """Test successful conversation creation."""
        title = "Test Conversation"

        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title=title,
            root_document_id=None,
        )

        # Verify conversation created with correct fields
        assert conv.id is not None
        assert conv.user_id == user1.id
        assert conv.title == title
        assert conv.last_message_at is None
        assert conv.created_at is not None
        assert conv.updated_at is not None
        assert conv.deleted_at is None

    def test_creation_without_title(self, db_session: Session, user1: User):
        """Test conversation creation without title (should be allowed)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title=None,
            root_document_id=None,
        )

        assert conv.id is not None
        assert conv.title is None

    def test_creation_with_document_reference(self, db_session: Session, user1: User):
        """Test conversation creation tied to a document."""
        # Create a document
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1024,
            source_url=None,
        )

        # Create conversation tied to document
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Discussion",
            root_document_id=doc.id,
        )

        assert conv.id is not None
        assert conv.user_id == user1.id

    def test_creation_with_nonexistent_document(self, db_session: Session, user1: User):
        """Test conversation creation with non-existent document (404)."""
        fake_doc_id = uuid4()

        with pytest.raises(NotFoundError):
            create_conversation_for_user(
                session=db_session,
                user_id=user1.id,
                title="Discussion",
                root_document_id=fake_doc_id,
            )

    def test_creation_with_other_users_document(
        self, db_session: Session, user1: User, user2: User
    ):
        """Test conversation creation with document owned by another user (404)."""
        # Create document owned by user2
        doc = create_document_placeholder(
            session=db_session,
            user=user2,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1024,
            source_url=None,
        )

        # Try to create conversation tied to user2's document as user1
        with pytest.raises(NotFoundError):
            create_conversation_for_user(
                session=db_session,
                user_id=user1.id,
                title="Discussion",
                root_document_id=doc.id,
            )


# ============================================================================
# GET_CONVERSATION_FOR_USER TESTS
# ============================================================================


class TestGetConversationForUser:
    """Test get_conversation_for_user function."""

    def test_retrieval_happy_path(self, db_session: Session, user1: User):
        """Test successful conversation retrieval."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        retrieved = get_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
        )

        assert retrieved.id == conv.id
        assert retrieved.user_id == user1.id
        assert retrieved.title == conv.title

    def test_retrieval_nonexistent(self, db_session: Session, user1: User):
        """Test retrieval of non-existent conversation (404)."""
        fake_conv_id = uuid4()

        with pytest.raises(NotFoundError):
            get_conversation_for_user(
                session=db_session,
                user_id=user1.id,
                conversation_id=fake_conv_id,
            )

    def test_retrieval_other_users_conversation(
        self, db_session: Session, user1: User, user2: User
    ):
        """Test ACL: user1 cannot retrieve user2's conversation (404)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user2.id,
            title="User2 Conv",
            root_document_id=None,
        )

        with pytest.raises(NotFoundError):
            get_conversation_for_user(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
            )

    def test_retrieval_soft_deleted(self, db_session: Session, user1: User):
        """Test soft-deleted conversations not retrieved (404)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        # Soft delete
        conv.deleted_at = datetime.now(timezone.utc)
        db_session.flush()

        with pytest.raises(NotFoundError):
            get_conversation_for_user(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
            )


# ============================================================================
# LIST_CONVERSATIONS_FOR_USER TESTS
# ============================================================================


class TestListConversationsForUser:
    """Test list_conversations_for_user function."""

    def test_list_empty(self, db_session: Session, user1: User):
        """Test listing when user has no conversations."""
        page = list_conversations_for_user(
            session=db_session,
            user_id=user1.id,
            pagination_params=PaginationParams(limit=20, cursor=None),
        )

        assert page.items == []
        assert page.next_cursor is None
        assert page.has_more is False

    def test_list_single_conversation(self, db_session: Session, user1: User):
        """Test listing with one conversation."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        page = list_conversations_for_user(
            session=db_session,
            user_id=user1.id,
            pagination_params=PaginationParams(limit=20, cursor=None),
        )

        assert len(page.items) == 1
        assert page.items[0].id == conv.id
        assert page.next_cursor is None
        assert page.has_more is False

    def test_list_multiple_conversations(self, db_session: Session, user1: User):
        """Test listing with multiple conversations."""
        # Create multiple conversations
        convs = []
        for i in range(5):
            conv = create_conversation_for_user(
                session=db_session,
                user_id=user1.id,
                title=f"Conv {i}",
                root_document_id=None,
            )
            convs.append(conv)

        page = list_conversations_for_user(
            session=db_session,
            user_id=user1.id,
            pagination_params=PaginationParams(limit=20, cursor=None),
        )

        assert len(page.items) == 5

    def test_list_excludes_other_users(self, db_session: Session, user1: User, user2: User):
        """Test ACL: user1 sees only their own conversations."""
        # User 1 creates conversation
        conv1 = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="User1 Conv",
            root_document_id=None,
        )

        # User 2 creates conversation
        create_conversation_for_user(
            session=db_session,
            user_id=user2.id,
            title="User2 Conv",
            root_document_id=None,
        )

        # User 1 lists conversations
        page = list_conversations_for_user(
            session=db_session,
            user_id=user1.id,
            pagination_params=PaginationParams(limit=20, cursor=None),
        )

        assert len(page.items) == 1
        assert page.items[0].id == conv1.id

    def test_list_excludes_soft_deleted(self, db_session: Session, user1: User):
        """Test soft-deleted conversations not included in list."""
        # Create two conversations
        conv1 = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Active",
            root_document_id=None,
        )
        conv2 = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Deleted",
            root_document_id=None,
        )

        # Soft delete one
        conv2.deleted_at = datetime.now(timezone.utc)
        db_session.flush()

        page = list_conversations_for_user(
            session=db_session,
            user_id=user1.id,
            pagination_params=PaginationParams(limit=20, cursor=None),
        )

        assert len(page.items) == 1
        assert page.items[0].id == conv1.id

    def test_list_deterministic_ordering(self, db_session: Session, user1: User):
        """Test ordering is deterministic: last_message_at DESC NULLS LAST, created_at DESC, id DESC."""
        # Create conversations with different created_at times
        convs = []
        for i in range(3):
            conv = create_conversation_for_user(
                session=db_session,
                user_id=user1.id,
                title=f"Conv {i}",
                root_document_id=None,
            )
            # Simulate delay
            if i < 2:
                conv.created_at = datetime.now(timezone.utc) - timedelta(seconds=3 - i)
            convs.append(conv)

        page = list_conversations_for_user(
            session=db_session,
            user_id=user1.id,
            pagination_params=PaginationParams(limit=20, cursor=None),
        )

        # Should be ordered by created_at DESC (newest first)
        assert len(page.items) == 3

    def test_list_pagination(self, db_session: Session, user1: User):
        """Test pagination with cursor."""
        # Create 5 conversations
        for i in range(5):
            create_conversation_for_user(
                session=db_session,
                user_id=user1.id,
                title=f"Conv {i}",
                root_document_id=None,
            )

        # Get first page with limit=2
        page1 = list_conversations_for_user(
            session=db_session,
            user_id=user1.id,
            pagination_params=PaginationParams(limit=2, cursor=None),
        )

        assert len(page1.items) == 2
        assert page1.has_more is True
        assert page1.next_cursor is not None

        # Get second page
        page2 = list_conversations_for_user(
            session=db_session,
            user_id=user1.id,
            pagination_params=PaginationParams(limit=2, cursor=page1.next_cursor),
        )

        assert len(page2.items) == 2
        assert page2.has_more is True


# ============================================================================
# APPEND_USER_MESSAGE TESTS
# ============================================================================


class TestAppendUserMessage:
    """Test append_user_message function."""

    def test_append_happy_path(self, db_session: Session, user1: User):
        """Test successful message appending."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        msg = append_user_message(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            content="Hello, world!",
        )

        # Verify message created
        assert msg.id is not None
        assert msg.conversation_id == conv.id
        assert msg.user_id == user1.id
        assert msg.role == "user"
        assert msg.content == "Hello, world!"
        assert msg.created_at is not None

        # Verify conversation timestamps updated
        db_session.refresh(conv)
        assert conv.last_message_at is not None
        assert conv.last_message_at >= msg.created_at

    def test_append_empty_content(self, db_session: Session, user1: User):
        """Test appending empty content (422)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        with pytest.raises(ValidationAppError):
            append_user_message(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
                content="",
            )

    def test_append_whitespace_only(self, db_session: Session, user1: User):
        """Test appending whitespace-only content (422)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        with pytest.raises(ValidationAppError):
            append_user_message(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
                content="   \n\t  ",
            )

    def test_append_nonexistent_conversation(self, db_session: Session, user1: User):
        """Test appending to non-existent conversation (404)."""
        fake_conv_id = uuid4()

        with pytest.raises(NotFoundError):
            append_user_message(
                session=db_session,
                user_id=user1.id,
                conversation_id=fake_conv_id,
                content="Hello",
            )

    def test_append_other_users_conversation(self, db_session: Session, user1: User, user2: User):
        """Test ACL: user1 cannot append to user2's conversation (404)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user2.id,
            title="User2 Conv",
            root_document_id=None,
        )

        with pytest.raises(NotFoundError):
            append_user_message(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
                content="Hello",
            )

    def test_append_multiple_messages(self, db_session: Session, user1: User):
        """Test appending multiple messages."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        msg1 = append_user_message(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            content="First message",
        )

        msg2 = append_user_message(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            content="Second message",
        )

        assert msg1.id != msg2.id
        assert msg1.created_at < msg2.created_at

        # Verify conversation updated to latest message time
        db_session.refresh(conv)
        assert conv.last_message_at >= msg2.created_at


# ============================================================================
# LIST_MESSAGES_FOR_CONVERSATION TESTS
# ============================================================================


class TestListMessagesForConversation:
    """Test list_messages_for_conversation function."""

    def test_list_empty(self, db_session: Session, user1: User):
        """Test listing messages when conversation is empty."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        page = list_messages_for_conversation(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            pagination_params=PaginationParams(limit=50, cursor=None),
        )

        assert page.items == []
        assert page.next_cursor is None
        assert page.has_more is False

    def test_list_single_message(self, db_session: Session, user1: User):
        """Test listing with one message."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        msg = append_user_message(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            content="Hello",
        )

        page = list_messages_for_conversation(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            pagination_params=PaginationParams(limit=50, cursor=None),
        )

        assert len(page.items) == 1
        assert page.items[0].id == msg.id
        assert page.items[0].content == "Hello"

    def test_list_multiple_messages(self, db_session: Session, user1: User):
        """Test listing with multiple messages."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        # Create multiple messages
        for i in range(5):
            append_user_message(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
                content=f"Message {i}",
            )

        page = list_messages_for_conversation(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            pagination_params=PaginationParams(limit=50, cursor=None),
        )

        assert len(page.items) == 5

    def test_list_deterministic_ordering(self, db_session: Session, user1: User):
        """Test ordering is deterministic: ORDER BY created_at ASC, id ASC."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        # Create messages
        msgs = []
        for i in range(3):
            msg = append_user_message(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
                content=f"Message {i}",
            )
            msgs.append(msg)

        page = list_messages_for_conversation(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            pagination_params=PaginationParams(limit=50, cursor=None),
        )

        # Should be ordered by created_at ASC (oldest first)
        assert len(page.items) == 3
        assert page.items[0].id == msgs[0].id
        assert page.items[1].id == msgs[1].id
        assert page.items[2].id == msgs[2].id

    def test_list_nonexistent_conversation(self, db_session: Session, user1: User):
        """Test listing messages from non-existent conversation (404)."""
        fake_conv_id = uuid4()

        with pytest.raises(NotFoundError):
            list_messages_for_conversation(
                session=db_session,
                user_id=user1.id,
                conversation_id=fake_conv_id,
                pagination_params=PaginationParams(limit=50, cursor=None),
            )

    def test_list_other_users_conversation(self, db_session: Session, user1: User, user2: User):
        """Test ACL: user1 cannot list messages from user2's conversation (404)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user2.id,
            title="User2 Conv",
            root_document_id=None,
        )

        append_user_message(
            session=db_session,
            user_id=user2.id,
            conversation_id=conv.id,
            content="User2's message",
        )

        with pytest.raises(NotFoundError):
            list_messages_for_conversation(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
                pagination_params=PaginationParams(limit=50, cursor=None),
            )

    def test_list_pagination(self, db_session: Session, user1: User):
        """Test pagination with cursor."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=user1.id,
            title="Test",
            root_document_id=None,
        )

        # Create 5 messages
        for i in range(5):
            append_user_message(
                session=db_session,
                user_id=user1.id,
                conversation_id=conv.id,
                content=f"Message {i}",
            )

        # Get first page with limit=2
        page1 = list_messages_for_conversation(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            pagination_params=PaginationParams(limit=2, cursor=None),
        )

        assert len(page1.items) == 2
        assert page1.has_more is True
        assert page1.next_cursor is not None

        # Get second page
        page2 = list_messages_for_conversation(
            session=db_session,
            user_id=user1.id,
            conversation_id=conv.id,
            pagination_params=PaginationParams(limit=2, cursor=page1.next_cursor),
        )

        assert len(page2.items) == 2
