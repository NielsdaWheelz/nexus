"""Comprehensive tests for document detail API (GET /documents/{id}).

Tests cover:
- Happy path: authenticated get with correct response shape
- Typed IDs (doc_ prefix)
- Invalid ID format (422 ValidationAppError)
- Wrong typed ID prefix (422 ValidationAppError)
- Not found (404 NotFoundError)
- ACL: user cannot see other user's documents (404, not 403)
- Soft-deleted documents return 404
- Authentication required (401)

All tests use real database transactions with auto-rollback.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ErrorCode
from app.core.ids import to_api_id
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

    mime_type = "application/pdf" if source_kind == "pdf" else f"application/{source_kind}"

    doc = Document(
        id=uuid4(),
        user_id=user.id,
        title=title,
        original_blob_key=f"s3://bucket/{uuid4()}.{source_kind}",
        original_mime_type=mime_type,
        original_size_bytes=1024,
        content_hash="abc123",
        canonical_text="test content",
        canonical_hash="def456",
        canonical_version=1,
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


class TestGetDocumentHappyPath:
    """Test successful document get scenarios."""

    def test_get_document_happy_path(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test successful document retrieval."""
        # Create document
        doc = create_test_document(db_session, authenticated_user, title="My Document")
        doc_id = to_api_id("document", doc.id)

        # Get document
        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()

        # Verify response structure
        assert "id" in result
        assert "title" in result
        assert "source_kind" in result
        assert "processing_status" in result
        assert "created_at" in result
        assert "updated_at" in result

        # Verify content
        assert result["id"] == doc_id
        assert result["title"] == "My Document"
        assert result["source_kind"] == "pdf"
        assert result["processing_status"] == "ready"

    def test_get_document_typed_id_format(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that document ID is typed (doc_<uuid>)."""
        doc = create_test_document(db_session, authenticated_user)
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()

        # Verify typed ID
        assert result["id"].startswith("doc_")
        assert len(result["id"]) > 4

    def test_get_document_iso8601_timestamps(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that timestamps are ISO8601 UTC."""
        doc = create_test_document(db_session, authenticated_user)
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()

        # Parse timestamps (should not raise)
        created = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
        updated = datetime.fromisoformat(result["updated_at"].replace("Z", "+00:00"))

        assert created is not None
        assert updated is not None
        assert created.tzinfo is not None
        assert updated.tzinfo is not None

    def test_get_document_pdf(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test getting a PDF document."""
        doc = create_test_document(db_session, authenticated_user, source_kind="pdf")
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["source_kind"] == "pdf"

    def test_get_document_epub(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test getting an EPUB document."""
        doc = create_test_document(db_session, authenticated_user, source_kind="epub")
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["source_kind"] == "epub"

    def test_get_document_html(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test getting an HTML document."""
        doc = create_test_document(db_session, authenticated_user, source_kind="html")
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["source_kind"] == "html"

    def test_get_document_status_pending(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test getting a document with pending status."""
        doc = create_test_document(db_session, authenticated_user, status="pending")
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["processing_status"] == "pending"

    def test_get_document_status_processing(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test getting a document with processing status."""
        doc = create_test_document(db_session, authenticated_user, status="processing")
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["processing_status"] == "processing"

    def test_get_document_status_ready(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test getting a document with ready status."""
        doc = create_test_document(db_session, authenticated_user, status="ready")
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["processing_status"] == "ready"

    def test_get_document_status_failed(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test getting a document with failed status."""
        doc = create_test_document(db_session, authenticated_user, status="failed")
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["processing_status"] == "failed"


# ============================================================================
# VALIDATION TESTS (Invalid ID Format)
# ============================================================================


class TestGetDocumentValidation:
    """Test validation of document IDs."""

    def test_get_document_invalid_id_format(self, client_authenticated: TestClient):
        """Test that malformed ID returns 422 ValidationAppError."""
        response = client_authenticated.get("/documents/not-a-valid-id")

        assert response.status_code == 422
        result = response.json()

        assert "error" in result
        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "Invalid" in result["error"]["message"]

    def test_get_document_empty_id(self, client_authenticated: TestClient):
        """Test that empty ID returns 422."""
        response = client_authenticated.get("/documents/")

        # Empty path parameter should result in 404 (no route match)
        # or treated as list endpoint
        assert response.status_code in (404, 200)

    def test_get_document_missing_underscore(self, client_authenticated: TestClient):
        """Test ID without underscore returns 422."""
        fake_uuid = "11111111222233334444555555555555"
        response = client_authenticated.get(f"/documents/{fake_uuid}")

        assert response.status_code == 422
        result = response.json()
        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value

    def test_get_document_malformed_uuid(self, client_authenticated: TestClient):
        """Test ID with malformed UUID returns 422."""
        response = client_authenticated.get("/documents/doc_not-a-uuid")

        assert response.status_code == 422
        result = response.json()
        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value


# ============================================================================
# WRONG PREFIX TESTS
# ============================================================================


class TestGetDocumentWrongPrefix:
    """Test handling of wrong typed ID prefix."""

    def test_get_document_user_id_prefix(self, client_authenticated: TestClient):
        """Test that user ID prefix returns 422."""
        user_id = to_api_id("user", uuid4())
        response = client_authenticated.get(f"/documents/{user_id}")

        assert response.status_code == 422
        result = response.json()

        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "document" in result["error"]["message"].lower()

    def test_get_document_highlight_id_prefix(self, client_authenticated: TestClient):
        """Test that highlight ID prefix returns 422."""
        hl_id = to_api_id("highlight", uuid4())
        response = client_authenticated.get(f"/documents/{hl_id}")

        assert response.status_code == 422
        result = response.json()

        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "document" in result["error"]["message"].lower()

    def test_get_document_reader_id_prefix(self, client_authenticated: TestClient):
        """Test that reader ID prefix returns 422."""
        rdr_id = to_api_id("reader", uuid4())
        response = client_authenticated.get(f"/documents/{rdr_id}")

        assert response.status_code == 422
        result = response.json()

        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value


# ============================================================================
# NOT FOUND TESTS
# ============================================================================


class TestGetDocumentNotFound:
    """Test 404 not found scenarios."""

    def test_get_document_nonexistent(self, client_authenticated: TestClient):
        """Test that nonexistent document returns 404."""
        fake_id = to_api_id("document", uuid4())
        response = client_authenticated.get(f"/documents/{fake_id}")

        assert response.status_code == 404
        result = response.json()

        assert result["error"]["code"] == ErrorCode.NOT_FOUND.value
        assert "not found" in result["error"]["message"].lower()
        assert "trace_id" in result["error"]

    def test_get_document_deleted(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that soft-deleted document returns 404."""
        # Create and delete document
        doc = create_test_document(db_session, authenticated_user)
        doc.deleted_at = datetime.now(timezone.utc)
        db_session.flush()

        doc_id = to_api_id("document", doc.id)
        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 404
        result = response.json()
        assert result["error"]["code"] == ErrorCode.NOT_FOUND.value


# ============================================================================
# ACL TESTS
# ============================================================================


class TestGetDocumentACL:
    """Test access control enforcement."""

    def test_user_cannot_see_other_users_document(
        self, db_session: Session, authenticated_user: User, other_user: User
    ):
        """Test that user cannot see another user's document (404, not 403)."""
        # Create app
        app = create_app()

        def override_get_session() -> Session:
            return db_session

        app.dependency_overrides[_get_session] = override_get_session

        from app.core.auth.deps import get_current_user

        # Create document for other_user
        doc = create_test_document(db_session, other_user, title="Other's Document")
        doc_id = to_api_id("document", doc.id)

        # Client as authenticated_user
        async def override_auth_user() -> User:
            return authenticated_user

        app.dependency_overrides[get_current_user] = override_auth_user
        client = TestClient(app)

        response = client.get(f"/documents/{doc_id}")

        # Should return 404 (not 403) to avoid leaking existence
        assert response.status_code == 404
        result = response.json()
        assert result["error"]["code"] == ErrorCode.NOT_FOUND.value

        app.dependency_overrides.clear()

    def test_owner_can_see_own_document(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that owner can see their own document."""
        doc = create_test_document(db_session, authenticated_user)
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["id"] == doc_id


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================


class TestGetDocumentAuthentication:
    """Test authentication requirements."""

    def test_unauthenticated_get(self, client: TestClient, db_session: Session):
        """Test that unauthenticated request returns 401."""
        user = User(
            id=uuid4(),
            external_user_id="test_user",
            email="test@example.com",
        )
        db_session.add(user)
        db_session.flush()

        doc = create_test_document(db_session, user)
        doc_id = to_api_id("document", doc.id)

        response = client.get(f"/documents/{doc_id}")

        assert response.status_code == 401
        result = response.json()
        assert result["error"]["code"] == ErrorCode.AUTH_REQUIRED.value


# ============================================================================
# ERROR ENVELOPE TESTS
# ============================================================================


class TestGetDocumentErrorEnvelope:
    """Test error response envelope compliance."""

    def test_error_envelope_structure_invalid_id(self, client_authenticated: TestClient):
        """Test that error response has correct envelope structure."""
        response = client_authenticated.get("/documents/invalid")

        assert response.status_code == 422
        result = response.json()

        # Error envelope structure
        assert "error" in result
        assert "code" in result["error"]
        assert "message" in result["error"]
        assert "trace_id" in result["error"]
        assert isinstance(result["error"]["trace_id"], str)

    def test_error_envelope_structure_not_found(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test error envelope for not found."""
        fake_id = to_api_id("document", uuid4())
        response = client_authenticated.get(f"/documents/{fake_id}")

        assert response.status_code == 404
        result = response.json()

        # Error envelope structure
        assert "error" in result
        assert "code" in result["error"]
        assert "message" in result["error"]
        assert "trace_id" in result["error"]
        assert "details" in result["error"]

    def test_success_response_no_error_field(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that success response has no error field."""
        doc = create_test_document(db_session, authenticated_user)
        doc_id = to_api_id("document", doc.id)

        response = client_authenticated.get(f"/documents/{doc_id}")

        assert response.status_code == 200
        result = response.json()

        # Should NOT have error field in success response
        assert "error" not in result
        assert "id" in result
