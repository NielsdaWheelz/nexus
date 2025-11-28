"""Comprehensive tests for document upload API (POST /documents).

Tests cover:
- Happy path: authenticated upload of valid files
- Correct response shape with typed IDs
- Document stored in DB with correct raw UUID
- Typed ID returned (doc_<uuid>)
- Title resolution (explicit override vs. file.filename)
- Validation errors (missing file, empty file, invalid source_kind)
- Authentication (unauthenticated returns 401)
- Storage errors (simulated storage failure)
- DB integration (document persisted with correct fields)

All tests use real database transactions with auto-rollback.
"""

from io import BytesIO
from unittest.mock import patch
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
    """Create an authenticated test user in the shared db_session.

    Flush makes the user visible to the same session (and transaction).
    Do NOT commit - the transaction is managed by the db_session fixture.
    """
    user = User(
        id=uuid4(),
        external_user_id="clerk_test_user",
        email="testuser@example.com",
    )
    db_session.add(user)
    db_session.flush()  # Assign ID and make visible to this transaction
    return user


@pytest.fixture
def other_user(db_session: Session) -> User:
    """Create another test user in the shared db_session (for ACL testing).

    Flush makes the user visible to the same session (and transaction).
    Do NOT commit - the transaction is managed by the db_session fixture.
    """
    user = User(
        id=uuid4(),
        external_user_id="clerk_other_user",
        email="otheruser@example.com",
    )
    db_session.add(user)
    db_session.flush()  # Assign ID and make visible to this transaction
    return user


@pytest.fixture
def app_with_auth(app: FastAPI, db_session: Session, authenticated_user: User):
    """Extend the base app fixture with authentication mocking.

    This fixture:
    1. Takes the base app (which has db_session override)
    2. Creates an authenticated user in db_session
    3. Mocks get_current_user to return that user
    4. Ensures both the app and the user share the same session
    """
    from app.core.auth.deps import get_current_user

    # Mock get_current_user to return authenticated_user
    async def override_get_current_user() -> User:
        return authenticated_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    yield app

    # Clear auth override (session override will be cleared by base app fixture)
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]


@pytest.fixture
def client_authenticated(app_with_auth: FastAPI):
    """Test client with authenticated user."""
    return TestClient(app_with_auth)


# ============================================================================
# HAPPY PATH TESTS
# ============================================================================


class TestUploadDocumentHappyPath:
    """Test successful document upload scenarios."""

    def test_upload_pdf_minimal(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test uploading a PDF file with minimal fields."""
        # Create file
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        # Upload
        response = client_authenticated.post("/documents", files=files, data=data)

        # Verify response
        if response.status_code != 201:
            print(f"DEBUG: Response status={response.status_code}, body={response.text}")
        assert response.status_code == 201
        result = response.json()["data"]

        # Verify response shape
        assert "id" in result
        assert "title" in result
        assert "source_kind" in result
        assert "created_at" in result
        assert "updated_at" in result

        # Verify typed ID format
        doc_id = result["id"]
        assert doc_id.startswith("doc_")
        assert len(doc_id) > 4

        # Verify content
        assert result["title"] == "document.pdf"  # Filename as default
        assert result["source_kind"] == "pdf"

        # Verify timestamps are ISO8601
        assert "T" in result["created_at"]
        assert "T" in result["updated_at"]

        # Verify document in database
        db_session.expire_all()
        docs = db_session.query(Document).filter_by(user_id=authenticated_user.id).all()
        assert len(docs) == 1
        doc = docs[0]
        assert doc.title == "document.pdf"
        assert doc.original_mime_type == "application/pdf"
        assert doc.original_size_bytes == len(file_content)
        assert doc.status == "pending"
        assert doc.user_id == authenticated_user.id

    def test_upload_with_explicit_title(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that explicit title overrides filename."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf", "title": "My Custom Title"}

        response = client_authenticated.post("/documents", files=files, data=data)

        assert response.status_code == 201
        result = response.json()["data"]

        # Title should be explicit override
        assert result["title"] == "My Custom Title"

        # Verify in database
        db_session.expire_all()
        doc = db_session.query(Document).filter_by(user_id=authenticated_user.id).first()
        assert doc.title == "My Custom Title"

    def test_upload_epub(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test uploading an EPUB file."""
        file_content = b"EPUB file content"
        files = {"file": ("book.epub", BytesIO(file_content), "application/epub+zip")}
        data = {"source_kind": "epub"}

        response = client_authenticated.post("/documents", files=files, data=data)

        assert response.status_code == 201
        result = response.json()["data"]
        assert result["source_kind"] == "epub"
        assert result["title"] == "book.epub"

    def test_upload_html(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test uploading an HTML file."""
        file_content = b"<html><body>Content</body></html>"
        files = {"file": ("page.html", BytesIO(file_content), "text/html")}
        data = {"source_kind": "html"}

        response = client_authenticated.post("/documents", files=files, data=data)

        assert response.status_code == 201
        result = response.json()["data"]
        assert result["source_kind"] == "html"
        assert result["title"] == "page.html"

    def test_upload_stores_correct_file_size(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that file size is correctly stored."""
        file_content = b"A" * 1024  # 1KB
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)
        assert response.status_code == 201

        db_session.expire_all()
        doc = db_session.query(Document).filter_by(user_id=authenticated_user.id).first()
        assert doc.original_size_bytes == 1024

    def test_upload_document_persisted_once(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that document is persisted exactly once (no duplicates)."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)
        assert response.status_code == 201

        db_session.expire_all()
        docs = db_session.query(Document).filter_by(user_id=authenticated_user.id).all()
        assert len(docs) == 1


# ============================================================================
# VALIDATION ERROR TESTS (422)
# ============================================================================


class TestUploadDocumentValidation:
    """Test validation error scenarios."""

    def test_missing_file(self, client_authenticated: TestClient, authenticated_user: User):
        """Test that missing file returns 422 ValidationError."""
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", data=data)

        assert response.status_code == 422
        # FastAPI returns 422 for missing required fields (not our ValidationAppError)

    def test_empty_file(self, client_authenticated: TestClient, authenticated_user: User):
        """Test that empty file returns 422 ValidationAppError."""
        files = {"file": ("empty.pdf", BytesIO(b""), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)

        assert response.status_code == 422
        result = response.json()
        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "empty" in result["error"]["message"].lower()

    def test_invalid_source_kind(self, client_authenticated: TestClient, authenticated_user: User):
        """Test that invalid source_kind returns 422 ValidationAppError."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "invalid_type"}

        response = client_authenticated.post("/documents", files=files, data=data)

        assert response.status_code == 422
        result = response.json()
        assert result["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "source_kind" in result["error"]["message"].lower()

    def test_missing_source_kind(self, client_authenticated: TestClient, authenticated_user: User):
        """Test that missing source_kind returns 422."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}

        response = client_authenticated.post("/documents", files=files)

        assert response.status_code == 422


# ============================================================================
# AUTHENTICATION TESTS (401)
# ============================================================================


class TestUploadDocumentAuthentication:
    """Test authentication requirements."""

    def test_unauthenticated_upload(self, client: TestClient):
        """Test that unauthenticated request returns 401 AUTH_REQUIRED."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client.post("/documents", files=files, data=data)

        assert response.status_code == 401
        result = response.json()
        assert result["error"]["code"] == ErrorCode.AUTH_REQUIRED.value

    def test_malformed_token(self, client: TestClient):
        """Test that malformed token returns 401."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client.post(
            "/documents",
            files=files,
            data=data,
            headers={"Authorization": "Foo bar"},
        )

        assert response.status_code == 401
        result = response.json()
        assert result["error"]["code"] == ErrorCode.AUTH_REQUIRED.value


# ============================================================================
# STORAGE ERROR TESTS (503)
# ============================================================================


class TestUploadDocumentStorageFailure:
    """Test storage failure scenarios."""

    def test_storage_failure_returns_unavailable(
        self, client_authenticated: TestClient, authenticated_user: User
    ):
        """Test that storage failure returns 503 UNAVAILABLE or 500 INTERNAL_ERROR."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        # Mock storage to raise exception
        with patch("app.api.routes.documents.StorageService.store_raw_blob") as mock_store:
            mock_store.side_effect = OSError("Disk full")

            response = client_authenticated.post("/documents", files=files, data=data)

            # Could be 500 or 503 depending on how error is wrapped
            assert response.status_code in (500, 503)
            result = response.json()
            assert "error" in result
            assert result["error"]["trace_id"] is not None


# ============================================================================
# RESPONSE ENVELOPE TESTS
# ============================================================================


class TestUploadDocumentResponseEnvelope:
    """Test response envelope compliance."""

    def test_success_response_structure(
        self, client_authenticated: TestClient, authenticated_user: User
    ):
        """Test that success response has correct structure."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)

        assert response.status_code == 201
        result = response.json()["data"]

        # Should NOT have error envelope (direct response, no ok field)
        # Per spec, successful responses are direct, not wrapped in ok/error

        # Verify all required fields
        assert isinstance(result["id"], str)
        assert isinstance(result["title"], str)
        assert isinstance(result["source_kind"], str)
        assert isinstance(result["created_at"], str)
        assert isinstance(result["updated_at"], str)

    def test_error_response_structure(
        self, client_authenticated: TestClient, authenticated_user: User
    ):
        """Test that error response has correct envelope."""
        file_content = b""
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)

        assert response.status_code == 422
        result = response.json()

        # Error envelope structure
        assert "error" in result
        assert "code" in result["error"]
        assert "message" in result["error"]
        assert "trace_id" in result["error"]


# ============================================================================
# DB INTEGRATION TESTS
# ============================================================================


class TestUploadDocumentDBIntegration:
    """Test database integration."""

    def test_document_timestamps_valid_iso8601(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that timestamps are valid ISO8601."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)
        assert response.status_code == 201
        result = response.json()["data"]

        # Try parsing timestamps
        from datetime import datetime

        created = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
        updated = datetime.fromisoformat(result["updated_at"].replace("Z", "+00:00"))

        assert created is not None
        assert updated is not None

        # Verify in database
        db_session.expire_all()
        doc = db_session.query(Document).filter_by(user_id=authenticated_user.id).first()
        assert doc.created_at is not None
        assert doc.updated_at is not None

    def test_document_user_ownership(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that document is owned by authenticated user."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)
        assert response.status_code == 201

        db_session.expire_all()
        doc = db_session.query(Document).filter_by(user_id=authenticated_user.id).first()
        assert doc is not None
        assert doc.user_id == authenticated_user.id

    def test_document_not_deleted(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that newly created document is not soft-deleted."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)
        assert response.status_code == 201

        db_session.expire_all()
        doc = db_session.query(Document).filter_by(user_id=authenticated_user.id).first()
        assert doc.deleted_at is None

    def test_document_status_pending(
        self, client_authenticated: TestClient, db_session: Session, authenticated_user: User
    ):
        """Test that document is created with pending status."""
        file_content = b"PDF file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response = client_authenticated.post("/documents", files=files, data=data)
        assert response.status_code == 201

        db_session.expire_all()
        doc = db_session.query(Document).filter_by(user_id=authenticated_user.id).first()
        assert doc.status == "pending"

    def test_multiple_uploads_different_users(
        self, db_session: Session, authenticated_user: User, other_user: User
    ):
        """Test that different users can upload documents independently."""
        # Create separate clients for each user
        app = create_app()

        def override_get_session() -> Session:
            return db_session

        app.dependency_overrides[_get_session] = override_get_session

        from app.core.auth.deps import get_current_user

        # Client 1: authenticated_user
        async def override_user1() -> User:
            return authenticated_user

        app.dependency_overrides[get_current_user] = override_user1
        client1 = TestClient(app)

        file_content = b"PDF 1"
        files = {"file": ("doc1.pdf", BytesIO(file_content), "application/pdf")}
        data = {"source_kind": "pdf"}

        response1 = client1.post("/documents", files=files, data=data)
        assert response1.status_code == 201

        # Client 2: other_user
        async def override_user2() -> User:
            return other_user

        app.dependency_overrides[get_current_user] = override_user2
        client2 = TestClient(app)

        file_content2 = b"PDF 2"
        files2 = {"file": ("doc2.pdf", BytesIO(file_content2), "application/pdf")}
        response2 = client2.post("/documents", files=files2, data=data)
        assert response2.status_code == 201

        # Verify both documents exist and are separated by user
        db_session.expire_all()
        docs1 = db_session.query(Document).filter_by(user_id=authenticated_user.id).all()
        docs2 = db_session.query(Document).filter_by(user_id=other_user.id).all()

        assert len(docs1) == 1
        assert len(docs2) == 1
        assert docs1[0].title == "doc1.pdf"
        assert docs2[0].title == "doc2.pdf"

        app.dependency_overrides.clear()
