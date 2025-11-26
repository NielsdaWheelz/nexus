"""Comprehensive tests for conversation API (PR 5.1).

Tests cover:
- POST /conversations: Create conversation (with & without document)
- GET /conversations: List conversations with pagination
- GET /conversations/{id}: Get conversation detail with ACL
- GET /conversations/{id}/messages: List messages with pagination
- POST /conversations/{id}/messages: Append user message with ACL
- Error cases: Invalid IDs, non-existent resources, ACL violations, unauthenticated
- Typed ID validation

All tests use real database transactions with auto-rollback.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.models.user import User
from app.services.conversations import create_conversation_for_user
from app.services.documents import create_document_placeholder

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def authenticated_user(db_session: Session) -> User:
    """Create an authenticated test user."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_test_user",
        email="testuser@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def other_user(db_session: Session) -> User:
    """Create another test user (for ACL testing)."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_other_user",
        email="otheruser@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def app_with_auth(app: FastAPI, db_session: Session, authenticated_user: User):
    """Extend app fixture with authentication mocking."""
    from app.core.auth.deps import get_current_user

    async def override_get_current_user() -> User:
        return authenticated_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    yield app

    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]


@pytest.fixture
def client_authenticated(app_with_auth: FastAPI):
    """Test client with authenticated user."""
    return TestClient(app_with_auth)


@pytest.fixture
def app_with_other_user_auth(app: FastAPI, db_session: Session, other_user: User):
    """Extend app fixture with authentication for other_user."""
    from app.core.auth.deps import get_current_user

    async def override_get_current_user() -> User:
        return other_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    yield app

    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]


@pytest.fixture
def client_other_user(app_with_other_user_auth: FastAPI):
    """Test client with other_user."""
    return TestClient(app_with_other_user_auth)


# ============================================================================
# POST /conversations TESTS
# ============================================================================


class TestCreateConversation:
    """Tests for POST /conversations endpoint."""

    def test_create_happy_path(self, client_authenticated: TestClient, authenticated_user: User):
        """Test successful conversation creation."""
        response = client_authenticated.post(
            "/conversations",
            json={
                "title": "Test Conversation",
                "root_document_id": None,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("conv_")
        assert data["title"] == "Test Conversation"
        assert data["root_document_id"] is None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None
        assert data["last_message_at"] is None

    def test_create_without_title(self, client_authenticated: TestClient):
        """Test creating conversation without title."""
        response = client_authenticated.post(
            "/conversations",
            json={"root_document_id": None},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("conv_")
        assert data["title"] is None

    def test_create_with_document(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test creating conversation tied to a document."""
        # Create a document
        doc = create_document_placeholder(
            session=db_session,
            user=authenticated_user,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1024,
            source_url=None,
        )

        from app.core.ids import to_api_id

        doc_api_id = to_api_id("document", doc.id)

        response = client_authenticated.post(
            "/conversations",
            json={
                "title": "Discussion",
                "root_document_id": doc_api_id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("conv_")
        assert data["root_document_id"] == doc_api_id

    def test_create_with_nonexistent_document(self, client_authenticated: TestClient):
        """Test creating conversation with non-existent document (404)."""
        fake_doc_id = f"doc_{uuid4()}"

        response = client_authenticated.post(
            "/conversations",
            json={
                "title": "Discussion",
                "root_document_id": fake_doc_id,
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == ErrorCode.NOT_FOUND

    def test_create_with_other_users_document(
        self,
        client_authenticated: TestClient,
        authenticated_user: User,
        other_user: User,
        db_session: Session,
    ):
        """Test creating conversation with document owned by another user (404)."""
        # Create document owned by other_user
        doc = create_document_placeholder(
            session=db_session,
            user=other_user,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1024,
            source_url=None,
        )

        from app.core.ids import to_api_id

        doc_api_id = to_api_id("document", doc.id)

        response = client_authenticated.post(
            "/conversations",
            json={
                "title": "Discussion",
                "root_document_id": doc_api_id,
            },
        )

        assert response.status_code == 404

    def test_create_invalid_document_id_format(self, client_authenticated: TestClient):
        """Test creating conversation with invalid document ID format (422)."""
        response = client_authenticated.post(
            "/conversations",
            json={
                "title": "Discussion",
                "root_document_id": "invalid_id_format",
            },
        )

        assert response.status_code == 422

    def test_create_unauthenticated(self, client: TestClient):
        """Test creating conversation without authentication (401)."""
        response = client.post(
            "/conversations",
            json={"title": "Test"},
        )

        assert response.status_code == 401


# ============================================================================
# GET /conversations TESTS
# ============================================================================


class TestListConversations:
    """Tests for GET /conversations endpoint."""

    def test_list_empty(self, client_authenticated: TestClient):
        """Test listing when user has no conversations."""
        response = client_authenticated.get("/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    def test_list_single(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test listing with one conversation."""
        create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Test",
            root_document_id=None,
        )

        response = client_authenticated.get("/conversations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["id"].startswith("conv_")
        assert data["items"][0]["title"] == "Test"

    def test_list_multiple(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test listing with multiple conversations."""
        for i in range(5):
            create_conversation_for_user(
                session=db_session,
                user_id=authenticated_user.id,
                title=f"Conv {i}",
                root_document_id=None,
            )

        response = client_authenticated.get("/conversations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5

    def test_list_excludes_other_users(
        self,
        client_authenticated: TestClient,
        authenticated_user: User,
        other_user: User,
        db_session: Session,
    ):
        """Test ACL: user only sees their own conversations."""
        # authenticated_user creates conversation
        create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="User1 Conv",
            root_document_id=None,
        )

        # other_user creates conversation
        create_conversation_for_user(
            session=db_session,
            user_id=other_user.id,
            title="User2 Conv",
            root_document_id=None,
        )

        response = client_authenticated.get("/conversations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "User1 Conv"

    def test_list_excludes_soft_deleted(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test soft-deleted conversations not included."""
        # Create two conversations
        create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Active",
            root_document_id=None,
        )
        conv2 = create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Deleted",
            root_document_id=None,
        )

        # Soft delete one
        conv2.deleted_at = datetime.now(timezone.utc)
        db_session.flush()

        response = client_authenticated.get("/conversations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Active"

    def test_list_pagination(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test pagination with cursor and limit."""
        for i in range(5):
            create_conversation_for_user(
                session=db_session,
                user_id=authenticated_user.id,
                title=f"Conv {i}",
                root_document_id=None,
            )

        # First page
        response = client_authenticated.get("/conversations?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

        # Second page
        response = client_authenticated.get(f"/conversations?limit=2&cursor={data['next_cursor']}")
        assert response.status_code == 200
        data2 = response.json()
        assert len(data2["items"]) == 2

    def test_list_unauthenticated(self, client: TestClient):
        """Test listing without authentication (401)."""
        response = client.get("/conversations")

        assert response.status_code == 401


# ============================================================================
# GET /conversations/{id} TESTS
# ============================================================================


class TestGetConversation:
    """Tests for GET /conversations/{conversation_id} endpoint."""

    def test_get_happy_path(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test retrieving conversation."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Test",
            root_document_id=None,
        )

        from app.core.ids import to_api_id

        conv_api_id = to_api_id("conversation", conv.id)

        response = client_authenticated.get(f"/conversations/{conv_api_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == conv_api_id
        assert data["title"] == "Test"

    def test_get_nonexistent(self, client_authenticated: TestClient):
        """Test retrieving non-existent conversation (404)."""
        fake_conv_id = f"conv_{uuid4()}"

        response = client_authenticated.get(f"/conversations/{fake_conv_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == ErrorCode.NOT_FOUND

    def test_get_other_users_conversation(
        self,
        client_authenticated: TestClient,
        other_user: User,
        db_session: Session,
    ):
        """Test ACL: cannot get other user's conversation (404)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=other_user.id,
            title="Other User's Conv",
            root_document_id=None,
        )

        from app.core.ids import to_api_id

        conv_api_id = to_api_id("conversation", conv.id)

        response = client_authenticated.get(f"/conversations/{conv_api_id}")

        assert response.status_code == 404

    def test_get_invalid_id_format(self, client_authenticated: TestClient):
        """Test retrieving with invalid ID format (422)."""
        response = client_authenticated.get("/conversations/invalid_id")

        assert response.status_code == 422

    def test_get_unauthenticated(self, client: TestClient):
        """Test retrieving without authentication (401)."""
        fake_conv_id = f"conv_{uuid4()}"

        response = client.get(f"/conversations/{fake_conv_id}")

        assert response.status_code == 401


# ============================================================================
# GET /conversations/{id}/messages TESTS
# ============================================================================


class TestListMessages:
    """Tests for GET /conversations/{conversation_id}/messages endpoint."""

    def test_list_empty(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test listing messages when conversation is empty."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Test",
            root_document_id=None,
        )

        from app.core.ids import to_api_id

        conv_api_id = to_api_id("conversation", conv.id)

        response = client_authenticated.get(f"/conversations/{conv_api_id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["has_more"] is False

    def test_list_with_messages(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test listing with messages."""
        from app.core.ids import to_api_id
        from app.services.conversations import append_user_message

        conv = create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Test",
            root_document_id=None,
        )

        # Add messages
        for i in range(3):
            append_user_message(
                session=db_session,
                user_id=authenticated_user.id,
                conversation_id=conv.id,
                content=f"Message {i}",
            )

        conv_api_id = to_api_id("conversation", conv.id)

        response = client_authenticated.get(f"/conversations/{conv_api_id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert all(item["id"].startswith("msg_") for item in data["items"])
        assert all(item["role"] == "user" for item in data["items"])

    def test_list_nonexistent_conversation(self, client_authenticated: TestClient):
        """Test listing messages from non-existent conversation (404)."""
        fake_conv_id = f"conv_{uuid4()}"

        response = client_authenticated.get(f"/conversations/{fake_conv_id}/messages")

        assert response.status_code == 404

    def test_list_other_users_conversation(
        self,
        client_authenticated: TestClient,
        other_user: User,
        db_session: Session,
    ):
        """Test ACL: cannot list messages from other user's conversation (404)."""
        conv = create_conversation_for_user(
            session=db_session,
            user_id=other_user.id,
            title="Other User's Conv",
            root_document_id=None,
        )

        from app.core.ids import to_api_id

        conv_api_id = to_api_id("conversation", conv.id)

        response = client_authenticated.get(f"/conversations/{conv_api_id}/messages")

        assert response.status_code == 404

    def test_list_pagination(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test pagination with cursor and limit."""
        from app.core.ids import to_api_id
        from app.services.conversations import append_user_message

        conv = create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Test",
            root_document_id=None,
        )

        # Add messages
        for i in range(5):
            append_user_message(
                session=db_session,
                user_id=authenticated_user.id,
                conversation_id=conv.id,
                content=f"Message {i}",
            )

        conv_api_id = to_api_id("conversation", conv.id)

        # First page
        response = client_authenticated.get(f"/conversations/{conv_api_id}/messages?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True

        # Second page
        response = client_authenticated.get(
            f"/conversations/{conv_api_id}/messages?limit=2&cursor={data['next_cursor']}"
        )
        assert response.status_code == 200
        data2 = response.json()
        assert len(data2["items"]) == 2

    def test_list_unauthenticated(self, client: TestClient):
        """Test listing without authentication (401)."""
        fake_conv_id = f"conv_{uuid4()}"

        response = client.get(f"/conversations/{fake_conv_id}/messages")

        assert response.status_code == 401


# ============================================================================
# POST /conversations/{id}/messages TESTS
# ============================================================================


class TestCreateMessage:
    """Tests for POST /conversations/{conversation_id}/messages endpoint."""

    def test_create_happy_path(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test successful message creation."""
        from app.core.ids import to_api_id

        conv = create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Test",
            root_document_id=None,
        )

        conv_api_id = to_api_id("conversation", conv.id)

        response = client_authenticated.post(
            f"/conversations/{conv_api_id}/messages",
            json={"content": "Hello, world!"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("msg_")
        assert data["role"] == "user"
        assert data["content"] == "Hello, world!"
        assert data["created_at"] is not None

    def test_create_empty_content(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test creating message with empty content (422)."""
        from app.core.ids import to_api_id

        conv = create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Test",
            root_document_id=None,
        )

        conv_api_id = to_api_id("conversation", conv.id)

        response = client_authenticated.post(
            f"/conversations/{conv_api_id}/messages",
            json={"content": ""},
        )

        assert response.status_code == 422

    def test_create_nonexistent_conversation(self, client_authenticated: TestClient):
        """Test creating message in non-existent conversation (404)."""
        fake_conv_id = f"conv_{uuid4()}"

        response = client_authenticated.post(
            f"/conversations/{fake_conv_id}/messages",
            json={"content": "Hello"},
        )

        assert response.status_code == 404

    def test_create_other_users_conversation(
        self,
        client_authenticated: TestClient,
        other_user: User,
        db_session: Session,
    ):
        """Test ACL: cannot create message in other user's conversation (404)."""
        from app.core.ids import to_api_id

        conv = create_conversation_for_user(
            session=db_session,
            user_id=other_user.id,
            title="Other User's Conv",
            root_document_id=None,
        )

        conv_api_id = to_api_id("conversation", conv.id)

        response = client_authenticated.post(
            f"/conversations/{conv_api_id}/messages",
            json={"content": "Hello"},
        )

        assert response.status_code == 404

    def test_create_unauthenticated(self, client: TestClient):
        """Test creating message without authentication (401)."""
        fake_conv_id = f"conv_{uuid4()}"

        response = client.post(
            f"/conversations/{fake_conv_id}/messages",
            json={"content": "Hello"},
        )

        assert response.status_code == 401

    def test_create_updates_conversation_timestamp(
        self, client_authenticated: TestClient, authenticated_user: User, db_session: Session
    ):
        """Test that message creation updates conversation timestamp."""
        from app.core.ids import to_api_id

        conv = create_conversation_for_user(
            session=db_session,
            user_id=authenticated_user.id,
            title="Test",
            root_document_id=None,
        )

        conv_api_id = to_api_id("conversation", conv.id)

        assert conv.last_message_at is None

        response = client_authenticated.post(
            f"/conversations/{conv_api_id}/messages",
            json={"content": "Hello"},
        )

        assert response.status_code == 201

        # Verify conversation timestamp updated
        db_session.refresh(conv)
        assert conv.last_message_at is not None
