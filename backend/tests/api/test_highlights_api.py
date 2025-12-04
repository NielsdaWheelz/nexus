"""Comprehensive tests for highlights API endpoints.

Tests cover:
- POST /highlights: Create highlight with character-range anchor
- GET /documents/{document_id}/highlights: List highlights on a document
- GET /users/{user_id}/highlights: List highlights created by a user
- Authentication and ACL enforcement
- Anchor validation and error handling
- Pagination
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.ids import from_api_id, to_api_id
from app.models.document import Document
from app.models.highlight import Highlight
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
        canonical_text="The quick brown fox jumps over the lazy dog. This is a test document with some content.",
        canonical_hash="def456",
        text_byte_length=85,
        extractor_version="1.0",
        status="ready",
    )
    db_session.add(doc)
    db_session.flush()
    return doc


@pytest.fixture
def other_user_document(db_session: Session, other_user: User) -> Document:
    """Create a document owned by other_user for ACL testing."""
    doc = Document(
        user_id=other_user.id,
        title="Other User's Document",
        original_blob_key="s3://bucket/file2.pdf",
        original_mime_type="application/pdf",
        original_size_bytes=1000,
        content_hash="xyz789",
        canonical_text="Some other content that the authenticated user should not access.",
        canonical_hash="uvw456",
        text_byte_length=65,
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


class TestCreateHighlight:
    """Test POST /highlights endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test successful highlight creation."""
        doc_typed_id = to_api_id("document", test_document.id)

        # Create highlight for "quick brown fox" (chars 4-19)
        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": doc_typed_id,
                "anchor_type": "text",
                "text_start": 4,
                "text_end": 19,
            },
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["id"].startswith("hlght_")
        assert data["document_id"] == doc_typed_id
        assert data["text_start"] == 4
        assert data["text_end"] == 19
        assert data["quote"] == "quick brown fox"
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

        # Verify stored in DB
        hl_type, hl_id = from_api_id(data["id"])
        assert hl_type == "highlight"
        highlight = db_session.query(Highlight).filter(Highlight.id == hl_id).first()
        assert highlight is not None
        assert highlight.user_id == authenticated_user.id
        assert highlight.media_id == test_document.id
        assert highlight.text_start == 4
        assert highlight.text_end == 19
        assert highlight.quote == "quick brown fox"
        assert highlight.anchor_type == "text"
        assert highlight.media_type == "document"

    def test_invalid_media_id_format(self, client_authenticated: TestClient):
        """Test that invalid media ID format returns 422."""
        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": "invalid_id_format",
                "anchor_type": "text",
                "text_start": 0,
                "text_end": 10,
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert (
            "media_id" in str(data["error"])
            or "Invalid media_id format" in data["error"]["message"]
        )

    def test_invalid_media_id_type(
        self,
        client_authenticated: TestClient,
        authenticated_user: User,
    ):
        """Test that wrong typed ID (e.g., usr_ instead of doc_) returns 422."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": user_typed_id,
                "anchor_type": "text",
                "text_start": 0,
                "text_end": 10,
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_document_not_found(self, client_authenticated: TestClient):
        """Test that non-existent document returns 404."""
        fake_doc_id = to_api_id("document", uuid4())

        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": fake_doc_id,
                "anchor_type": "text",
                "text_start": 0,
                "text_end": 10,
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["details"]["resource_type"] == "document"

    def test_acl_document_not_owned(
        self,
        client_authenticated: TestClient,
        other_user_document: Document,
    ):
        """Test that highlighting another user's document returns 404."""
        doc_typed_id = to_api_id("document", other_user_document.id)

        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": doc_typed_id,
                "anchor_type": "text",
                "text_start": 0,
                "text_end": 10,
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_text_start_negative(
        self,
        client_authenticated: TestClient,
        test_document: Document,
    ):
        """Test that negative text_start returns 422."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": doc_typed_id,
                "anchor_type": "text",
                "text_start": -1,
                "text_end": 10,
            },
        )

        assert response.status_code == 422

    def test_text_end_less_than_start(
        self,
        client_authenticated: TestClient,
        test_document: Document,
    ):
        """Test that text_end < text_start returns 422."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": doc_typed_id,
                "anchor_type": "text",
                "text_start": 10,
                "text_end": 5,
            },
        )

        assert response.status_code == 422

    def test_text_end_exceeds_canonical_length(
        self,
        client_authenticated: TestClient,
        test_document: Document,
    ):
        """Test that text_end > canonical_text length returns 422."""
        doc_typed_id = to_api_id("document", test_document.id)
        canonical_length = len(test_document.canonical_text)

        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": doc_typed_id,
                "anchor_type": "text",
                "text_start": 0,
                "text_end": canonical_length + 100,
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_unauthenticated_returns_401(self, client: TestClient, test_document: Document):
        """Test that unauthenticated request returns 401."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": doc_typed_id,
                "anchor_type": "text",
                "text_start": 0,
                "text_end": 10,
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_REQUIRED"


class TestListDocumentHighlights:
    """Test GET /documents/{document_id}/highlights endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test listing highlights on a document."""
        # Create a few highlights
        doc_typed_id = to_api_id("document", test_document.id)

        # Highlight 1: "quick brown"
        hl1 = Highlight(
            user_id=authenticated_user.id,
            media_type="document",
            media_id=test_document.id,
            anchor_type="text",
            text_start=4,
            text_end=15,
            quote="quick brown",
            prefix="The ",
            suffix=" fox",
        )
        db_session.add(hl1)

        # Highlight 2: "lazy dog"
        hl2 = Highlight(
            user_id=authenticated_user.id,
            media_type="document",
            media_id=test_document.id,
            anchor_type="text",
            text_start=40,
            text_end=48,
            quote="lazy dog",
            prefix="the ",
            suffix=". This",
        )
        db_session.add(hl2)
        db_session.flush()

        response = client_authenticated.get(f"/documents/{doc_typed_id}/highlights")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 2
        assert data["has_more"] is False
        assert data["next_cursor"] is None

        # Check first item (should be newest first)
        item = data["items"][0]
        assert item["id"].startswith("hlght_")
        assert item["document_id"] == doc_typed_id
        assert item["text_start"] in [4, 40]
        assert item["text_end"] in [15, 48]

    def test_empty_list(
        self,
        client_authenticated: TestClient,
        test_document: Document,
    ):
        """Test listing highlights on document with no highlights."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.get(f"/documents/{doc_typed_id}/highlights")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 0
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    def test_pagination(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test pagination with limit and cursor."""
        doc_typed_id = to_api_id("document", test_document.id)

        # Create 3 highlights
        for i in range(3):
            hl = Highlight(
                user_id=authenticated_user.id,
                media_type="document",
                media_id=test_document.id,
                anchor_type="text",
                text_start=i * 10,
                text_end=i * 10 + 5,
                quote=f"text{i}",
                prefix="",
                suffix="",
            )
            db_session.add(hl)
        db_session.flush()

        # Get first page (limit=2)
        response1 = client_authenticated.get(
            f"/documents/{doc_typed_id}/highlights",
            params={"limit": 2},
        )
        assert response1.status_code == 200
        data1 = response1.json()["data"]
        assert len(data1["items"]) == 2
        assert data1["has_more"] is True
        assert data1["next_cursor"] is not None

        # Get second page
        response2 = client_authenticated.get(
            f"/documents/{doc_typed_id}/highlights",
            params={"limit": 2, "cursor": data1["next_cursor"]},
        )
        assert response2.status_code == 200
        data2 = response2.json()["data"]
        assert len(data2["items"]) == 1
        assert data2["has_more"] is False

        # Ensure no duplicates across pages
        page1_ids = {item["id"] for item in data1["items"]}
        page2_ids = {item["id"] for item in data2["items"]}
        assert len(page1_ids & page2_ids) == 0

    def test_invalid_document_id_format(self, client_authenticated: TestClient):
        """Test that invalid document ID format returns 422."""
        response = client_authenticated.get("/documents/invalid_id/highlights")
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_document_not_found(self, client_authenticated: TestClient):
        """Test that non-existent document returns 404."""
        fake_doc_id = to_api_id("document", uuid4())
        response = client_authenticated.get(f"/documents/{fake_doc_id}/highlights")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_acl_other_user_document(
        self,
        client_authenticated: TestClient,
        other_user_document: Document,
    ):
        """Test that listing highlights on another user's document returns 404."""
        doc_typed_id = to_api_id("document", other_user_document.id)
        response = client_authenticated.get(f"/documents/{doc_typed_id}/highlights")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_only_user_highlights_returned(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        other_user: User,
        test_document: Document,
    ):
        """Test that only highlights owned by current user are returned."""
        doc_typed_id = to_api_id("document", test_document.id)

        # Create highlights for both users on same document
        hl_user1 = Highlight(
            user_id=authenticated_user.id,
            media_type="document",
            media_id=test_document.id,
            anchor_type="text",
            text_start=0,
            text_end=5,
            quote="The q",
            prefix="",
            suffix="",
        )
        hl_user2 = Highlight(
            user_id=other_user.id,
            media_type="document",
            media_id=test_document.id,
            anchor_type="text",
            text_start=10,
            text_end=15,
            quote="brown",
            prefix="",
            suffix="",
        )
        db_session.add(hl_user1)
        db_session.add(hl_user2)
        db_session.flush()

        response = client_authenticated.get(f"/documents/{doc_typed_id}/highlights")

        assert response.status_code == 200
        data = response.json()["data"]
        # Should only see authenticated_user's highlight
        assert len(data["items"]) == 1
        assert data["items"][0]["text_start"] == 0


class TestListUserHighlights:
    """Test GET /users/{user_id}/highlights endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test listing all highlights created by a user."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        # Create a highlight
        hl = Highlight(
            user_id=authenticated_user.id,
            media_type="document",
            media_id=test_document.id,
            anchor_type="text",
            text_start=0,
            text_end=5,
            quote="The q",
            prefix="",
            suffix="",
        )
        db_session.add(hl)
        db_session.flush()

        response = client_authenticated.get(f"/users/{user_typed_id}/highlights")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 1
        assert data["items"][0]["id"].startswith("hlght_")
        assert data["has_more"] is False

    def test_empty_list(
        self,
        client_authenticated: TestClient,
        authenticated_user: User,
    ):
        """Test listing highlights for user with no highlights."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        response = client_authenticated.get(f"/users/{user_typed_id}/highlights")

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data["items"]) == 0
        assert data["has_more"] is False

    def test_pagination(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
    ):
        """Test pagination for user's highlights."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        # Create 3 highlights
        for i in range(3):
            hl = Highlight(
                user_id=authenticated_user.id,
                media_type="document",
                media_id=test_document.id,
                anchor_type="text",
                text_start=i * 10,
                text_end=i * 10 + 5,
                quote=f"text{i}",
                prefix="",
                suffix="",
            )
            db_session.add(hl)
        db_session.flush()

        # Get first page (limit=2)
        response1 = client_authenticated.get(
            f"/users/{user_typed_id}/highlights",
            params={"limit": 2},
        )
        assert response1.status_code == 200
        data1 = response1.json()["data"]
        assert len(data1["items"]) == 2
        assert data1["has_more"] is True
        assert data1["next_cursor"] is not None

        # Get second page
        response2 = client_authenticated.get(
            f"/users/{user_typed_id}/highlights",
            params={"limit": 2, "cursor": data1["next_cursor"]},
        )
        assert response2.status_code == 200
        data2 = response2.json()["data"]
        assert len(data2["items"]) == 1
        assert data2["has_more"] is False

    def test_invalid_user_id_format(self, client_authenticated: TestClient):
        """Test that invalid user ID format returns 422."""
        response = client_authenticated.get("/users/invalid_id/highlights")
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_user_id_type(self, client_authenticated: TestClient, test_document: Document):
        """Test that wrong typed ID (e.g., doc_ instead of usr_) returns 422."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.get(f"/users/{doc_typed_id}/highlights")

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_acl_other_user(
        self,
        client_authenticated: TestClient,
        other_user: User,
    ):
        """Test that accessing another user's highlights returns 404."""
        other_user_typed_id = to_api_id("user", other_user.id)

        response = client_authenticated.get(f"/users/{other_user_typed_id}/highlights")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_unauthenticated_returns_401(self, client: TestClient, authenticated_user: User):
        """Test that unauthenticated request returns 401."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        response = client.get(f"/users/{user_typed_id}/highlights")

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_REQUIRED"


class TestHighlightErrorEnvelopes:
    """Test that error responses use canonical error envelope."""

    def test_error_envelope_structure(
        self,
        client_authenticated: TestClient,
        test_document: Document,
    ):
        """Test that errors include all required envelope fields."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.post(
            "/highlights",
            json={
                "media_type": "document",
                "media_id": doc_typed_id,
                "anchor_type": "text",
                "text_start": 1000,
                "text_end": 2000,  # Out of bounds
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "details" in data["error"]
        assert "trace_id" in data["error"]
        assert data["error"]["trace_id"].startswith("req_")
