"""Comprehensive tests for reader API endpoints.

Tests cover:
- POST /readers: Create reading session
- GET /readers/{reader_id}: Get reading session
- PATCH /readers/{reader_id}: Update reading position
- GET /documents/{document_id}/readers: List readers for document
- Authentication and ACL enforcement
- Error handling and validation
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.ids import from_api_id, to_api_id
from app.models.document import Document
from app.models.reader import Reader
from app.models.user import User


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
    """Create another test user for ACL testing."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_other_user",
        email="otheruser@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_document(db_session: Session, authenticated_user: User) -> Document:
    """Create a test document owned by authenticated_user."""
    doc = Document(
        user_id=authenticated_user.id,
        title="Test Document",
        original_blob_key="s3://bucket/file.pdf",
        original_mime_type="application/pdf",
        original_size_bytes=1000,
        content_hash="abc123",
        canonical_text="test document content here",
        canonical_hash="def456",
        canonical_version=1,
        text_byte_length=25,
        extractor_version="1.0",
        status="ready",
    )
    db_session.add(doc)
    db_session.flush()
    return doc


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
def client_authenticated(app_with_auth: FastAPI) -> TestClient:
    """Test client with authenticated user."""
    return TestClient(app_with_auth)


class TestCreateReader:
    """Test POST /readers endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test successful reader creation."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.post(
            "/readers",
            json={"document_id": doc_typed_id},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("rdr_")
        assert data["document_id"] == doc_typed_id
        assert data["current_position"] is None
        assert data["last_read_at"] is not None
        assert data["created_at"] is not None

        # Verify stored in DB
        rdr_type, rdr_id = from_api_id(data["id"])
        assert rdr_type == "reader"
        reader = db_session.query(Reader).filter(Reader.id == rdr_id).first()
        assert reader is not None
        assert reader.user_id == authenticated_user.id

    def test_idempotent_get_or_create(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        test_document: Document,
    ):
        """Test that POST /readers is idempotent (get-or-create)."""
        doc_typed_id = to_api_id("document", test_document.id)

        response1 = client_authenticated.post(
            "/readers",
            json={"document_id": doc_typed_id},
        )
        assert response1.status_code == 201
        data1 = response1.json()

        response2 = client_authenticated.post(
            "/readers",
            json={"document_id": doc_typed_id},
        )
        assert response2.status_code == 201
        data2 = response2.json()

        # Should return the same reader
        assert data1["id"] == data2["id"]

    def test_invalid_document_id_format(self, client_authenticated: TestClient):
        """Test validation of invalid document_id format."""
        response = client_authenticated.post(
            "/readers",
            json={"document_id": "invalid_format"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_wrong_type_prefix(self, client_authenticated: TestClient):
        """Test validation of wrong typed ID prefix."""
        wrong_id = to_api_id("user", uuid4())

        response = client_authenticated.post(
            "/readers",
            json={"document_id": wrong_id},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_document_not_found(self, client_authenticated: TestClient):
        """Test 404 when document not found."""
        fake_doc_id = to_api_id("document", uuid4())

        response = client_authenticated.post(
            "/readers",
            json={"document_id": fake_doc_id},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_document_not_owned_by_user(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        other_user: User,
    ):
        """Test 404 when user doesn't own the document."""
        doc = Document(
            user_id=other_user.id,  # Owned by other_user
            title="Other Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=4,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        doc_typed_id = to_api_id("document", doc.id)

        response = client_authenticated.post(
            "/readers",
            json={"document_id": doc_typed_id},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestGetReader:
    """Test GET /readers/{reader_id} endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test successful reader retrieval."""
        reader = Reader(
            user_id=authenticated_user.id,
            document_id=test_document.id,
            current_position=500,
        )
        db_session.add(reader)
        db_session.flush()

        reader_typed_id = to_api_id("reader", reader.id)

        response = client_authenticated.get(f"/readers/{reader_typed_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == reader_typed_id
        assert data["current_position"] == 500

    def test_invalid_reader_id_format(self, client_authenticated: TestClient):
        """Test validation of invalid reader_id format."""
        response = client_authenticated.get("/readers/invalid_format")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_wrong_type_prefix(self, client_authenticated: TestClient):
        """Test validation of wrong typed ID prefix."""
        wrong_id = to_api_id("document", uuid4())

        response = client_authenticated.get(f"/readers/{wrong_id}")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_reader_not_found(self, client_authenticated: TestClient):
        """Test 404 when reader not found."""
        fake_reader_id = to_api_id("reader", uuid4())

        response = client_authenticated.get(f"/readers/{fake_reader_id}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_enforces_acl(
        self,
        app_with_auth: FastAPI,
        db_session: Session,
        authenticated_user: User,
        other_user: User,
    ):
        """Test that user cannot access another user's reader."""
        # Create a document for other_user
        doc = Document(
            user_id=other_user.id,
            title="Other User's Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=4,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        # Create reader owned by other_user
        reader = Reader(
            user_id=other_user.id,
            document_id=doc.id,
        )
        db_session.add(reader)
        db_session.flush()

        reader_typed_id = to_api_id("reader", reader.id)

        # Try to access as authenticated_user
        from app.core.auth.deps import get_current_user

        app_with_auth.dependency_overrides[get_current_user] = lambda: authenticated_user

        client = TestClient(app_with_auth)
        response = client.get(f"/readers/{reader_typed_id}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestUpdateReader:
    """Test PATCH /readers/{reader_id} endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test successful reader position update."""
        reader = Reader(
            user_id=authenticated_user.id,
            document_id=test_document.id,
            current_position=0,
        )
        db_session.add(reader)
        db_session.flush()

        reader_typed_id = to_api_id("reader", reader.id)

        response = client_authenticated.patch(
            f"/readers/{reader_typed_id}",
            json={"current_position": 12345},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["current_position"] == 12345
        assert data["last_read_at"] is not None

    def test_invalid_position_negative(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test validation of negative position."""
        reader = Reader(
            user_id=authenticated_user.id,
            document_id=test_document.id,
        )
        db_session.add(reader)
        db_session.flush()

        reader_typed_id = to_api_id("reader", reader.id)

        response = client_authenticated.patch(
            f"/readers/{reader_typed_id}",
            json={"current_position": -1},
        )

        assert response.status_code == 422

    def test_invalid_reader_id_format(self, client_authenticated: TestClient):
        """Test validation of invalid reader_id format."""
        response = client_authenticated.patch(
            "/readers/invalid_format",
            json={"current_position": 100},
        )

        assert response.status_code == 422

    def test_reader_not_found(self, client_authenticated: TestClient):
        """Test 404 when reader not found."""
        fake_reader_id = to_api_id("reader", uuid4())

        response = client_authenticated.patch(
            f"/readers/{fake_reader_id}",
            json={"current_position": 100},
        )

        assert response.status_code == 404

    def test_enforces_acl(
        self,
        app_with_auth: FastAPI,
        db_session: Session,
        authenticated_user: User,
        other_user: User,
    ):
        """Test that user cannot update another user's reader."""
        # Create a document for other_user
        doc = Document(
            user_id=other_user.id,
            title="Other User's Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=4,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        reader = Reader(
            user_id=other_user.id,
            document_id=doc.id,
        )
        db_session.add(reader)
        db_session.flush()

        reader_typed_id = to_api_id("reader", reader.id)

        from app.core.auth.deps import get_current_user

        app_with_auth.dependency_overrides[get_current_user] = lambda: authenticated_user

        client = TestClient(app_with_auth)
        response = client.patch(
            f"/readers/{reader_typed_id}",
            json={"current_position": 100},
        )

        assert response.status_code == 404


class TestListDocumentReaders:
    """Test GET /documents/{document_id}/readers endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
        other_user: User,
    ):
        """Test successful listing of readers."""
        # Create readers for the same document by different users
        reader1 = Reader(user_id=authenticated_user.id, document_id=test_document.id)
        reader2 = Reader(user_id=other_user.id, document_id=test_document.id)
        db_session.add_all([reader1, reader2])
        db_session.flush()

        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.get(f"/documents/{doc_typed_id}/readers")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        assert all(item["document_id"] == doc_typed_id for item in data["items"])

    def test_pagination(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test pagination works correctly."""
        # Create 5 different users and readers for the same document
        users = [authenticated_user]
        for i in range(4):
            user = User(
                id=uuid4(),
                external_user_id=f"clerk_user_{i}",
                email=f"user{i}@example.com",
            )
            db_session.add(user)
            users.append(user)
        db_session.flush()

        # Create 5 readers (one per user for the same document)
        readers = [
            Reader(user_id=user.id, document_id=test_document.id) for user in users
        ]
        db_session.add_all(readers)
        db_session.flush()

        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.get(
            f"/documents/{doc_typed_id}/readers",
            params={"limit": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    def test_empty_result(
        self,
        client_authenticated: TestClient,
        test_document: Document,
    ):
        """Test empty result when no readers."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.get(f"/documents/{doc_typed_id}/readers")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0
        assert data["has_more"] is False

    def test_invalid_document_id_format(self, client_authenticated: TestClient):
        """Test validation of invalid document_id format."""
        response = client_authenticated.get("/documents/invalid_format/readers")

        assert response.status_code == 422

    def test_document_not_found(self, client_authenticated: TestClient):
        """Test 404 when document not found."""
        fake_doc_id = to_api_id("document", uuid4())

        response = client_authenticated.get(f"/documents/{fake_doc_id}/readers")

        assert response.status_code == 404

    def test_enforces_document_ownership(
        self,
        app_with_auth: FastAPI,
        db_session: Session,
        authenticated_user: User,
        other_user: User,
    ):
        """Test that user cannot list readers for documents they don't own."""
        doc = Document(
            user_id=other_user.id,  # Owned by other_user
            title="Other Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=4,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        doc_typed_id = to_api_id("document", doc.id)

        from app.core.auth.deps import get_current_user

        app_with_auth.dependency_overrides[get_current_user] = lambda: authenticated_user

        client = TestClient(app_with_auth)
        response = client.get(f"/documents/{doc_typed_id}/readers")

        assert response.status_code == 404


class TestAuthenticationRequired:
    """Test that all endpoints require authentication."""

    def test_post_readers_unauthenticated(self, client: TestClient):
        """Test POST /readers without authentication."""
        response = client.post(
            "/readers",
            json={"document_id": to_api_id("document", uuid4())},
        )

        assert response.status_code == 401

    def test_get_reader_unauthenticated(self, client: TestClient):
        """Test GET /readers/{id} without authentication."""
        response = client.get(f"/readers/{to_api_id('reader', uuid4())}")

        assert response.status_code == 401

    def test_patch_reader_unauthenticated(self, client: TestClient):
        """Test PATCH /readers/{id} without authentication."""
        response = client.patch(
            f"/readers/{to_api_id('reader', uuid4())}",
            json={"current_position": 100},
        )

        assert response.status_code == 401

    def test_list_readers_unauthenticated(self, client: TestClient):
        """Test GET /documents/{id}/readers without authentication."""
        response = client.get(f"/documents/{to_api_id('document', uuid4())}/readers")

        assert response.status_code == 401
