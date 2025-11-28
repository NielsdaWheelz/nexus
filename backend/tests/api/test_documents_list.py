"""Comprehensive tests for document list API (GET /documents).

Tests cover:
- Happy path: authenticated list with pagination
- Correct response shape with typed IDs
- Pagination: cursor, limit, has_more
- Status filtering (pending, processing, ready, failed)
- ACL: user A cannot see user B's docs (returns empty list, not 403)
- Soft-deleted docs not returned
- Authentication (unauthenticated returns 401)
- Deterministic ordering (created_at DESC, id DESC)
- Empty list handling
- Invalid cursor and status validation

All tests use real database transactions with auto-rollback.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.db.session import get_session as _get_session
from app.main import create_app
from app.models.document import Document
from app.models.user import User

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def authenticated_user(db_session: Session) -> User:
    """Create an authenticated test user in the shared db_session."""
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
    """Create another test user in the shared db_session (for ACL testing)."""
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
    """Extend the base app fixture with authentication mocking."""
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


def create_test_document(
    db_session: Session,
    user: User,
    title: str = "Test Document",
    status: str = "ready",
    created_at: datetime | None = None,
    source_kind: str = "pdf",
) -> Document:
    """Helper to create a test document."""
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    doc = Document(
        id=uuid4(),
        user_id=user.id,
        title=title,
        original_blob_key=f"s3://bucket/{uuid4()}.pdf",
        original_mime_type="application/pdf",
        original_size_bytes=1024,
        content_hash="abc123",
        canonical_text="test content",
        canonical_hash="def456",
        text_byte_length=12,
        extractor_version="1.0",
        status=status,
        embedding_status="pending",
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(doc)
    db_session.flush()
    return doc


# ============================================================================
# HAPPY PATH TESTS
# ============================================================================


class TestListDocumentsHappyPath:
    """Test successful document list scenarios."""

    def test_list_documents_empty(self, client_authenticated: TestClient):
        """Test listing documents when user has none."""
        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        # Verify response shape
        assert "items" in result
        assert "next_cursor" in result
        assert "has_more" in result

        # Verify empty state
        assert result["items"] == []
        assert result["next_cursor"] is None
        assert result["has_more"] is False

    def test_list_documents_single(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test listing documents with single document."""
        # Create document
        create_test_document(db_session, authenticated_user, title="My Document")

        # List documents
        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        # Verify response structure
        assert len(result["items"]) == 1
        assert result["next_cursor"] is None
        assert result["has_more"] is False

        # Verify document content
        item = result["items"][0]
        assert item["id"].startswith("doc_")
        assert item["title"] == "My Document"
        assert item["source_kind"] == "pdf"
        assert item["processing_status"] == "ready"
        assert "created_at" in item
        assert "updated_at" in item

    def test_list_documents_multiple(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test listing multiple documents."""
        # Create multiple documents
        create_test_document(db_session, authenticated_user, title="Doc 1")
        create_test_document(db_session, authenticated_user, title="Doc 2")
        create_test_document(db_session, authenticated_user, title="Doc 3")

        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        # All documents returned
        assert len(result["items"]) == 3
        assert result["has_more"] is False
        assert result["next_cursor"] is None

    def test_list_documents_order_newest_first(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that documents are ordered by created_at DESC (newest first)."""
        # Create documents with different timestamps
        now = datetime.now(timezone.utc)
        create_test_document(
            db_session, authenticated_user, title="Oldest", created_at=now - timedelta(hours=2)
        )
        create_test_document(
            db_session, authenticated_user, title="Middle", created_at=now - timedelta(hours=1)
        )
        create_test_document(db_session, authenticated_user, title="Newest", created_at=now)

        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        # Verify order: newest first
        titles = [item["title"] for item in result["items"]]
        assert titles == ["Newest", "Middle", "Oldest"]

    def test_list_documents_typed_ids(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that document IDs are typed (doc_<uuid>)."""
        create_test_document(db_session, authenticated_user)

        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        item = result["items"][0]
        doc_id = item["id"]

        # Verify typed ID format
        assert doc_id.startswith("doc_")
        assert len(doc_id) > 4
        assert "_" in doc_id

    def test_list_documents_iso8601_timestamps(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that timestamps are ISO8601 UTC."""
        create_test_document(db_session, authenticated_user)

        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        item = result["items"][0]

        # Parse timestamps (should not raise)
        created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        updated = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))

        assert created is not None
        assert updated is not None
        assert created.tzinfo is not None
        assert updated.tzinfo is not None


# ============================================================================
# PAGINATION TESTS
# ============================================================================


class TestListDocumentsPagination:
    """Test pagination behavior."""

    def test_pagination_limit_default(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that default limit is 20."""
        # Create 25 documents
        for i in range(25):
            create_test_document(db_session, authenticated_user, title=f"Doc {i}")

        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        # Should return 20 items (default limit)
        assert len(result["items"]) == 20
        assert result["has_more"] is True
        assert result["next_cursor"] is not None

    def test_pagination_limit_custom(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test custom limit parameter."""
        # Create 10 documents
        for i in range(10):
            create_test_document(db_session, authenticated_user, title=f"Doc {i}")

        response = client_authenticated.get("/documents?limit=5")

        assert response.status_code == 200
        result = response.json()["data"]

        # Should return 5 items
        assert len(result["items"]) == 5
        assert result["has_more"] is True
        assert result["next_cursor"] is not None

    def test_pagination_limit_max_capped(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that limit > 100 is rejected with validation error."""
        # Create 150 documents
        for i in range(150):
            create_test_document(db_session, authenticated_user, title=f"Doc {i}")

        response = client_authenticated.get("/documents?limit=200")

        # Limit > 100 should be rejected with validation error
        assert response.status_code == 422
        result = response.json()
        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value

    def test_pagination_cursor_roundtrip(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that cursor round-trips correctly."""
        # Create 50 documents
        for i in range(50):
            create_test_document(db_session, authenticated_user, title=f"Doc {i}")

        # First page
        response1 = client_authenticated.get("/documents?limit=10")
        assert response1.status_code == 200
        result1 = response1.json()["data"]

        assert len(result1["items"]) == 10
        assert result1["has_more"] is True

        first_page_ids = [item["id"] for item in result1["items"]]

        # Second page using cursor
        cursor = result1["next_cursor"]
        response2 = client_authenticated.get(f"/documents?limit=10&cursor={cursor}")
        assert response2.status_code == 200
        result2 = response2.json()["data"]

        assert len(result2["items"]) == 10
        second_page_ids = [item["id"] for item in result2["items"]]

        # No overlap between pages
        assert len(set(first_page_ids) & set(second_page_ids)) == 0

    def test_pagination_deterministic(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that pagination is deterministic (same query, same results)."""
        # Create documents
        for i in range(30):
            create_test_document(db_session, authenticated_user, title=f"Doc {i}")

        # First request
        response1 = client_authenticated.get("/documents?limit=10")
        result1 = response1.json()["data"]

        # Second request (same parameters)
        response2 = client_authenticated.get("/documents?limit=10")
        result2 = response2.json()["data"]

        # Should be identical
        ids1 = [item["id"] for item in result1["items"]]
        ids2 = [item["id"] for item in result2["items"]]

        assert ids1 == ids2


# ============================================================================
# STATUS FILTERING TESTS
# ============================================================================


class TestListDocumentsStatusFilter:
    """Test status filtering behavior."""

    def test_status_filter_ready(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test status=ready filter."""
        create_test_document(db_session, authenticated_user, title="Ready Doc", status="ready")
        create_test_document(db_session, authenticated_user, title="Pending Doc", status="pending")
        create_test_document(
            db_session, authenticated_user, title="Processing Doc", status="processing"
        )

        response = client_authenticated.get("/documents?status=ready")

        assert response.status_code == 200
        result = response.json()["data"]

        # Only ready documents
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Ready Doc"
        assert result["items"][0]["processing_status"] == "ready"

    def test_status_filter_pending(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test status=pending filter."""
        create_test_document(db_session, authenticated_user, title="Ready 1", status="ready")
        create_test_document(db_session, authenticated_user, title="Pending 1", status="pending")
        create_test_document(db_session, authenticated_user, title="Pending 2", status="pending")

        response = client_authenticated.get("/documents?status=pending")

        assert response.status_code == 200
        result = response.json()["data"]

        assert len(result["items"]) == 2
        titles = [item["title"] for item in result["items"]]
        assert set(titles) == {"Pending 1", "Pending 2"}

    def test_status_filter_processing(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test status=processing filter."""
        create_test_document(db_session, authenticated_user, title="Ready", status="ready")
        create_test_document(
            db_session, authenticated_user, title="Processing", status="processing"
        )

        response = client_authenticated.get("/documents?status=processing")

        assert response.status_code == 200
        result = response.json()["data"]

        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Processing"

    def test_status_filter_failed(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test status=failed filter."""
        create_test_document(db_session, authenticated_user, title="Ready", status="ready")
        create_test_document(db_session, authenticated_user, title="Failed", status="failed")

        response = client_authenticated.get("/documents?status=failed")

        assert response.status_code == 200
        result = response.json()["data"]

        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Failed"
        assert result["items"][0]["processing_status"] == "failed"

    def test_status_filter_empty_result(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test status filter with no matching results."""
        create_test_document(db_session, authenticated_user, title="Ready", status="ready")

        response = client_authenticated.get("/documents?status=failed")

        assert response.status_code == 200
        result = response.json()["data"]

        assert result["items"] == []
        assert result["has_more"] is False
        assert result["next_cursor"] is None

    def test_status_filter_invalid(self, client_authenticated: TestClient):
        """Test invalid status returns 422 ValidationAppError."""
        response = client_authenticated.get("/documents?status=invalid_status")

        assert response.status_code == 422
        result = response.json()

        assert "error" in result
        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "status" in result["error"]["message"].lower()

    def test_status_filter_with_pagination(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test status filter combined with pagination."""
        # Create 30 ready documents and 10 pending
        for i in range(30):
            create_test_document(db_session, authenticated_user, title=f"Ready {i}", status="ready")
        for i in range(10):
            create_test_document(
                db_session, authenticated_user, title=f"Pending {i}", status="pending"
            )

        # Get first page of ready documents with limit=10
        response = client_authenticated.get("/documents?status=ready&limit=10")

        assert response.status_code == 200
        result = response.json()["data"]

        # Should return 10 ready documents
        assert len(result["items"]) == 10
        assert all(item["processing_status"] == "ready" for item in result["items"])
        assert result["has_more"] is True


# ============================================================================
# ACL TESTS
# ============================================================================


class TestListDocumentsACL:
    """Test access control list enforcement."""

    def test_user_cannot_see_other_users_docs(
        self, db_session: Session, authenticated_user: User, other_user: User
    ):
        """Test that user A cannot see user B's docs (returns empty list, not 403)."""
        # Create app and clients
        app = create_app()

        def override_get_session() -> Session:
            return db_session

        app.dependency_overrides[_get_session] = override_get_session

        from app.core.auth.deps import get_current_user

        # Create documents for other_user
        create_test_document(db_session, other_user, title="Other's Doc 1")
        create_test_document(db_session, other_user, title="Other's Doc 2")

        # Create documents for authenticated_user
        create_test_document(db_session, authenticated_user, title="My Doc 1")

        # Client as authenticated_user
        async def override_auth_user() -> User:
            return authenticated_user

        app.dependency_overrides[get_current_user] = override_auth_user
        client = TestClient(app)

        response = client.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        # Should see only own documents
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "My Doc 1"

        # Should NOT see other user's documents
        titles = [item["title"] for item in result["items"]]
        assert "Other's Doc 1" not in titles
        assert "Other's Doc 2" not in titles

        app.dependency_overrides.clear()

    def test_different_users_see_own_docs_only(
        self, db_session: Session, authenticated_user: User, other_user: User
    ):
        """Test that each user sees only their own documents."""
        # Create app
        app = create_app()

        def override_get_session() -> Session:
            return db_session

        app.dependency_overrides[_get_session] = override_get_session

        from app.core.auth.deps import get_current_user

        # Create documents for each user
        create_test_document(db_session, authenticated_user, title="User1 Doc")
        create_test_document(db_session, other_user, title="User2 Doc")

        # Client 1: authenticated_user
        async def override_user1() -> User:
            return authenticated_user

        app.dependency_overrides[get_current_user] = override_user1
        client1 = TestClient(app)

        response1 = client1.get("/documents")
        assert response1.status_code == 200
        result1 = response1.json()["data"]

        assert len(result1["items"]) == 1
        assert result1["items"][0]["title"] == "User1 Doc"

        # Client 2: other_user
        async def override_user2() -> User:
            return other_user

        app.dependency_overrides[get_current_user] = override_user2
        client2 = TestClient(app)

        response2 = client2.get("/documents")
        assert response2.status_code == 200
        result2 = response2.json()["data"]

        assert len(result2["items"]) == 1
        assert result2["items"][0]["title"] == "User2 Doc"

        app.dependency_overrides.clear()


# ============================================================================
# SOFT DELETE TESTS
# ============================================================================


class TestListDocumentsSoftDelete:
    """Test soft delete enforcement."""

    def test_soft_deleted_docs_not_returned(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that soft-deleted documents are NOT returned."""
        # Create documents
        create_test_document(db_session, authenticated_user, title="Active Doc")
        deleted_doc = create_test_document(db_session, authenticated_user, title="Deleted Doc")

        # Soft-delete deleted_doc
        deleted_doc.deleted_at = datetime.now(timezone.utc)
        db_session.flush()

        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()["data"]

        # Only active document
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "Active Doc"

    def test_only_active_docs_in_pagination(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that pagination only counts active documents."""
        # Create 15 active and 10 deleted
        for i in range(15):
            create_test_document(db_session, authenticated_user, title=f"Active {i}")

        for i in range(10):
            doc = create_test_document(db_session, authenticated_user, title=f"Deleted {i}")
            doc.deleted_at = datetime.now(timezone.utc)

        db_session.flush()

        response = client_authenticated.get("/documents?limit=10")

        assert response.status_code == 200
        result = response.json()["data"]

        # Should only see active documents
        assert len(result["items"]) == 10
        titles = [item["title"] for item in result["items"]]
        for title in titles:
            assert not title.startswith("Deleted")


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================


class TestListDocumentsAuthentication:
    """Test authentication requirements."""

    def test_unauthenticated_list(self, client: TestClient):
        """Test that unauthenticated request returns 401 AUTH_REQUIRED."""
        response = client.get("/documents")

        assert response.status_code == 401
        result = response.json()
        assert result["error"]["code"] == ErrorCode.AUTH_REQUIRED.value

    def test_malformed_token_list(self, client: TestClient):
        """Test that malformed token returns 401."""
        response = client.get(
            "/documents",
            headers={"Authorization": "Foo bar"},
        )

        assert response.status_code == 401
        result = response.json()
        assert result["error"]["code"] == ErrorCode.AUTH_REQUIRED.value


# ============================================================================
# ERROR ENVELOPE TESTS
# ============================================================================


class TestListDocumentsErrorEnvelope:
    """Test error response envelope compliance."""

    def test_error_response_structure_invalid_cursor(self, client_authenticated: TestClient):
        """Test that error response has correct envelope for invalid cursor."""
        response = client_authenticated.get("/documents?cursor=invalid_cursor_here")

        assert response.status_code == 422
        result = response.json()

        # Error envelope structure
        assert "error" in result
        assert "code" in result["error"]
        assert "message" in result["error"]
        assert "trace_id" in result["error"]
        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value

    def test_success_response_no_error_field(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that success response has no error envelope (direct response)."""
        create_test_document(db_session, authenticated_user, title="Test")

        response = client_authenticated.get("/documents")

        assert response.status_code == 200
        result = response.json()

        # Should NOT have error field in success response
        assert "error" not in result

        # Should have data wrapper with required pagination fields
        assert "data" in result
        assert "items" in result["data"]
        assert "next_cursor" in result["data"]
        assert "has_more" in result["data"]


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestListDocumentsEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_limit_1(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test with limit=1."""
        for i in range(5):
            create_test_document(db_session, authenticated_user, title=f"Doc {i}")

        response = client_authenticated.get("/documents?limit=1")

        assert response.status_code == 200
        result = response.json()["data"]

        assert len(result["items"]) == 1
        assert result["has_more"] is True

    def test_cursor_at_end(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that cursor at end returns empty list."""
        for i in range(5):
            create_test_document(db_session, authenticated_user, title=f"Doc {i}")

        # Get last page
        response1 = client_authenticated.get("/documents?limit=3")
        assert response1.status_code == 200
        result1 = response1.json()["data"]

        cursor = result1["next_cursor"]

        # Get next page (should be empty since we're at end)
        response2 = client_authenticated.get(f"/documents?limit=3&cursor={cursor}")
        assert response2.status_code == 200
        result2 = response2.json()["data"]

        # Last page should be < limit or has_more=False
        assert result2["has_more"] is False
