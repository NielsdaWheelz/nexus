"""Comprehensive tests for annotations API endpoints.

Tests cover:
- POST /annotations: Create annotation on highlight or chunk
- PATCH /annotations/{annotation_id}: Update annotation content
- DELETE /annotations/{annotation_id}: Soft-delete annotation
- GET /documents/{document_id}/annotations: List annotations on a document
- GET /highlights/{highlight_id}/annotations: List annotations on a highlight
- GET /users/{user_id}/annotations: List annotations created by a user
- Authentication and ACL enforcement
- Validation and error handling
- Pagination
- Soft-delete semantics
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.ids import from_api_id, to_api_id
from app.models.annotation import Annotation
from app.models.chunk import ContentChunk
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
        canonical_version=1,
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
        canonical_version=1,
        text_byte_length=65,
        extractor_version="1.0",
        status="ready",
    )
    db_session.add(doc)
    db_session.flush()
    return doc


@pytest.fixture
def test_highlight(
    db_session: Session, authenticated_user: User, test_document: Document
) -> Highlight:
    """Create a test highlight on test_document."""
    hl = Highlight(
        user_id=authenticated_user.id,
        media_type="document",
        media_id=test_document.id,
        anchor_type="text",
        text_start=4,
        text_end=19,
        quote="quick brown fox",
        prefix="The ",
        suffix=" jum",
        canonical_version=1,
    )
    db_session.add(hl)
    db_session.flush()
    return hl


@pytest.fixture
def other_user_highlight(
    db_session: Session, other_user: User, other_user_document: Document
) -> Highlight:
    """Create a highlight owned by other_user for ACL testing."""
    hl = Highlight(
        user_id=other_user.id,
        media_type="document",
        media_id=other_user_document.id,
        anchor_type="text",
        text_start=0,
        text_end=10,
        quote="Some other",
        prefix="",
        suffix=" con",
        canonical_version=1,
    )
    db_session.add(hl)
    db_session.flush()
    return hl


@pytest.fixture
def test_chunk(
    db_session: Session, authenticated_user: User, test_document: Document
) -> ContentChunk:
    """Create a test content chunk on test_document."""
    chunk = ContentChunk(
        media_type="document",
        media_id=test_document.id,
        chunk_version="v1",
        embedding_model="text-embedding-3-small",
        text_start=0,
        text_end=50,
        text="The quick brown fox jumps over the lazy dog.",
        chunk_metadata={},
    )
    db_session.add(chunk)
    db_session.flush()
    return chunk


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


class TestCreateAnnotation:
    """Test POST /annotations endpoint."""

    def test_happy_path_on_highlight(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test successful annotation creation on a highlight."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)

        response = client_authenticated.post(
            "/annotations",
            json={
                "highlight_id": hl_typed_id,
                "content": "This is a great quote about foxes!",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("ann_")
        assert data["user_id"] == to_api_id("user", authenticated_user.id)
        assert data["highlight_id"] == hl_typed_id
        assert data["chunk_id"] is None
        assert data["content"] == "This is a great quote about foxes!"
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

        # Verify stored in DB
        ann_type, ann_id = from_api_id(data["id"])
        assert ann_type == "annotation"
        annotation = db_session.query(Annotation).filter(Annotation.id == ann_id).first()
        assert annotation is not None
        assert annotation.user_id == authenticated_user.id
        assert annotation.highlight_id == test_highlight.id
        assert annotation.chunk_id is None
        assert annotation.content == "This is a great quote about foxes!"
        assert annotation.deleted_at is None

    def test_happy_path_on_chunk(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_chunk: ContentChunk,
    ):
        """Test successful annotation creation on a chunk."""
        chunk_typed_id = to_api_id("chunk", test_chunk.id)

        response = client_authenticated.post(
            "/annotations",
            json={
                "chunk_id": chunk_typed_id,
                "content": "Interesting passage about animals.",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"].startswith("ann_")
        assert data["highlight_id"] is None
        assert data["chunk_id"] == chunk_typed_id
        assert data["content"] == "Interesting passage about animals."

        # Verify stored in DB
        ann_type, ann_id = from_api_id(data["id"])
        annotation = db_session.query(Annotation).filter(Annotation.id == ann_id).first()
        assert annotation is not None
        assert annotation.chunk_id == test_chunk.id
        assert annotation.highlight_id is None

    def test_both_highlight_and_chunk_provided(
        self,
        client_authenticated: TestClient,
        test_highlight: Highlight,
        test_chunk: ContentChunk,
    ):
        """Test that providing both highlight_id and chunk_id returns 422."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)
        chunk_typed_id = to_api_id("chunk", test_chunk.id)

        response = client_authenticated.post(
            "/annotations",
            json={
                "highlight_id": hl_typed_id,
                "chunk_id": chunk_typed_id,
                "content": "This should fail",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_neither_highlight_nor_chunk_provided(
        self,
        client_authenticated: TestClient,
    ):
        """Test that providing neither highlight_id nor chunk_id returns 422."""
        response = client_authenticated.post(
            "/annotations",
            json={
                "content": "This should fail",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_empty_content(
        self,
        client_authenticated: TestClient,
        test_highlight: Highlight,
    ):
        """Test that empty content returns 422."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)

        response = client_authenticated.post(
            "/annotations",
            json={
                "highlight_id": hl_typed_id,
                "content": "   ",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_highlight_id_format(self, client_authenticated: TestClient):
        """Test that invalid highlight_id format returns 422."""
        response = client_authenticated.post(
            "/annotations",
            json={
                "highlight_id": "invalid_id_format",
                "content": "Some content",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_highlight_id_type(
        self,
        client_authenticated: TestClient,
        authenticated_user: User,
    ):
        """Test that wrong typed ID (e.g., usr_ instead of hl_) returns 422."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        response = client_authenticated.post(
            "/annotations",
            json={
                "highlight_id": user_typed_id,
                "content": "Some content",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_highlight_not_found(self, client_authenticated: TestClient):
        """Test that non-existent highlight returns 404."""
        fake_hl_id = to_api_id("highlight", uuid4())

        response = client_authenticated.post(
            "/annotations",
            json={
                "highlight_id": fake_hl_id,
                "content": "Some content",
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["details"]["resource_type"] == "highlight"

    def test_acl_highlight_not_owned(
        self,
        client_authenticated: TestClient,
        other_user_highlight: Highlight,
    ):
        """Test that annotating another user's highlight returns 404."""
        hl_typed_id = to_api_id("highlight", other_user_highlight.id)

        response = client_authenticated.post(
            "/annotations",
            json={
                "highlight_id": hl_typed_id,
                "content": "Some content",
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_chunk_not_found(self, client_authenticated: TestClient):
        """Test that non-existent chunk returns 404."""
        fake_chunk_id = to_api_id("chunk", uuid4())

        response = client_authenticated.post(
            "/annotations",
            json={
                "chunk_id": fake_chunk_id,
                "content": "Some content",
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["details"]["resource_type"] == "chunk"

    def test_unauthenticated_returns_401(self, client: TestClient, test_highlight: Highlight):
        """Test that unauthenticated request returns 401."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)

        response = client.post(
            "/annotations",
            json={
                "highlight_id": hl_typed_id,
                "content": "Some content",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_REQUIRED"


class TestUpdateAnnotation:
    """Test PATCH /annotations/{annotation_id} endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test successful annotation update."""
        # Create an annotation first
        annotation = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Original content",
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client_authenticated.patch(
            f"/annotations/{ann_typed_id}",
            json={
                "content": "Updated content",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == ann_typed_id
        assert data["content"] == "Updated content"
        assert data["updated_at"] is not None

        # Verify in DB
        db_session.refresh(annotation)
        assert annotation.content == "Updated content"

    def test_empty_content(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test that empty content returns 422."""
        annotation = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Original content",
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client_authenticated.patch(
            f"/annotations/{ann_typed_id}",
            json={
                "content": "   ",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_annotation_id_format(self, client_authenticated: TestClient):
        """Test that invalid annotation_id format returns 422."""
        response = client_authenticated.patch(
            "/annotations/invalid_id",
            json={
                "content": "Some content",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_annotation_id_type(
        self,
        client_authenticated: TestClient,
        test_highlight: Highlight,
    ):
        """Test that wrong typed ID (e.g., hl_ instead of ann_) returns 422."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)

        response = client_authenticated.patch(
            f"/annotations/{hl_typed_id}",
            json={
                "content": "Some content",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_annotation_not_found(self, client_authenticated: TestClient):
        """Test that non-existent annotation returns 404."""
        fake_ann_id = to_api_id("annotation", uuid4())

        response = client_authenticated.patch(
            f"/annotations/{fake_ann_id}",
            json={
                "content": "Some content",
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["details"]["resource_type"] == "annotation"

    def test_acl_annotation_not_owned(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        other_user: User,
        other_user_highlight: Highlight,
    ):
        """Test that updating another user's annotation returns 404."""
        annotation = Annotation(
            user_id=other_user.id,
            highlight_id=other_user_highlight.id,
            content="Other user's annotation",
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client_authenticated.patch(
            f"/annotations/{ann_typed_id}",
            json={
                "content": "Trying to update",
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_annotation_already_deleted(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test that updating a soft-deleted annotation returns 404."""
        annotation = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Original content",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client_authenticated.patch(
            f"/annotations/{ann_typed_id}",
            json={
                "content": "Trying to update",
            },
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_unauthenticated_returns_401(
        self,
        client: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test that unauthenticated request returns 401."""
        annotation = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Original content",
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client.patch(
            f"/annotations/{ann_typed_id}",
            json={
                "content": "Trying to update",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_REQUIRED"


class TestDeleteAnnotation:
    """Test DELETE /annotations/{annotation_id} endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test successful annotation soft-delete."""
        annotation = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="To be deleted",
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client_authenticated.delete(f"/annotations/{ann_typed_id}")

        assert response.status_code == 204

        # Verify soft-deleted in DB
        db_session.refresh(annotation)
        assert annotation.deleted_at is not None

    def test_invalid_annotation_id_format(self, client_authenticated: TestClient):
        """Test that invalid annotation_id format returns 422."""
        response = client_authenticated.delete("/annotations/invalid_id")

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_annotation_not_found(self, client_authenticated: TestClient):
        """Test that non-existent annotation returns 404."""
        fake_ann_id = to_api_id("annotation", uuid4())

        response = client_authenticated.delete(f"/annotations/{fake_ann_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_acl_annotation_not_owned(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        other_user: User,
        other_user_highlight: Highlight,
    ):
        """Test that deleting another user's annotation returns 404."""
        annotation = Annotation(
            user_id=other_user.id,
            highlight_id=other_user_highlight.id,
            content="Other user's annotation",
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client_authenticated.delete(f"/annotations/{ann_typed_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_annotation_already_deleted(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test that deleting an already soft-deleted annotation returns 404."""
        annotation = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Already deleted",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client_authenticated.delete(f"/annotations/{ann_typed_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_unauthenticated_returns_401(
        self,
        client: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test that unauthenticated request returns 401."""
        annotation = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="To be deleted",
        )
        db_session.add(annotation)
        db_session.flush()

        ann_typed_id = to_api_id("annotation", annotation.id)

        response = client.delete(f"/annotations/{ann_typed_id}")

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_REQUIRED"


class TestListDocumentAnnotations:
    """Test GET /documents/{document_id}/annotations endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
        test_highlight: Highlight,
    ):
        """Test listing annotations on a document."""
        doc_typed_id = to_api_id("document", test_document.id)

        # Create annotations on the highlight
        ann1 = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="First annotation",
        )
        ann2 = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Second annotation",
        )
        db_session.add(ann1)
        db_session.add(ann2)
        db_session.flush()

        response = client_authenticated.get(f"/documents/{doc_typed_id}/annotations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is False
        assert data["next_cursor"] is None

        # Check items
        assert all(item["id"].startswith("ann_") for item in data["items"])
        assert all(item["document_id"] == doc_typed_id for item in data["items"])

    def test_empty_list(
        self,
        client_authenticated: TestClient,
        test_document: Document,
    ):
        """Test listing annotations on document with no annotations."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.get(f"/documents/{doc_typed_id}/annotations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0
        assert data["has_more"] is False
        assert data["next_cursor"] is None

    def test_pagination(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
        test_highlight: Highlight,
    ):
        """Test pagination with limit and cursor."""
        doc_typed_id = to_api_id("document", test_document.id)

        # Create 3 annotations
        for i in range(3):
            ann = Annotation(
                user_id=authenticated_user.id,
                highlight_id=test_highlight.id,
                content=f"Annotation {i}",
            )
            db_session.add(ann)
        db_session.flush()

        # Get first page (limit=2)
        response1 = client_authenticated.get(
            f"/documents/{doc_typed_id}/annotations",
            params={"limit": 2},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["items"]) == 2
        assert data1["has_more"] is True
        assert data1["next_cursor"] is not None

        # Get second page
        response2 = client_authenticated.get(
            f"/documents/{doc_typed_id}/annotations",
            params={"limit": 2, "cursor": data1["next_cursor"]},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 1
        assert data2["has_more"] is False

        # Ensure no duplicates across pages
        page1_ids = {item["id"] for item in data1["items"]}
        page2_ids = {item["id"] for item in data2["items"]}
        assert len(page1_ids & page2_ids) == 0

    def test_soft_delete_filtering(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_document: Document,
        test_highlight: Highlight,
    ):
        """Test that soft-deleted annotations are excluded."""
        doc_typed_id = to_api_id("document", test_document.id)

        # Create active annotation
        ann1 = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Active annotation",
        )
        # Create deleted annotation
        ann2 = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Deleted annotation",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(ann1)
        db_session.add(ann2)
        db_session.flush()

        response = client_authenticated.get(f"/documents/{doc_typed_id}/annotations")

        assert response.status_code == 200
        data = response.json()
        # Should only see active annotation
        assert len(data["items"]) == 1
        assert data["items"][0]["content"] == "Active annotation"

    def test_invalid_document_id_format(self, client_authenticated: TestClient):
        """Test that invalid document ID format returns 422."""
        response = client_authenticated.get("/documents/invalid_id/annotations")
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_document_not_found(self, client_authenticated: TestClient):
        """Test that non-existent document returns 404."""
        fake_doc_id = to_api_id("document", uuid4())
        response = client_authenticated.get(f"/documents/{fake_doc_id}/annotations")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_acl_other_user_document(
        self,
        client_authenticated: TestClient,
        other_user_document: Document,
    ):
        """Test that listing annotations on another user's document returns 404."""
        doc_typed_id = to_api_id("document", other_user_document.id)
        response = client_authenticated.get(f"/documents/{doc_typed_id}/annotations")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"


class TestListHighlightAnnotations:
    """Test GET /highlights/{highlight_id}/annotations endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test listing annotations on a highlight."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)

        # Create annotations
        ann1 = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="First note",
        )
        ann2 = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="Second note",
        )
        db_session.add(ann1)
        db_session.add(ann2)
        db_session.flush()

        response = client_authenticated.get(f"/highlights/{hl_typed_id}/annotations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert all(item["highlight_id"] == hl_typed_id for item in data["items"])
        assert data["has_more"] is False

    def test_empty_list(
        self,
        client_authenticated: TestClient,
        test_highlight: Highlight,
    ):
        """Test listing annotations on highlight with no annotations."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)

        response = client_authenticated.get(f"/highlights/{hl_typed_id}/annotations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0
        assert data["has_more"] is False

    def test_pagination(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test pagination for highlight annotations."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)

        # Create 3 annotations
        for i in range(3):
            ann = Annotation(
                user_id=authenticated_user.id,
                highlight_id=test_highlight.id,
                content=f"Note {i}",
            )
            db_session.add(ann)
        db_session.flush()

        # Get first page (limit=2)
        response1 = client_authenticated.get(
            f"/highlights/{hl_typed_id}/annotations",
            params={"limit": 2},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["items"]) == 2
        assert data1["has_more"] is True

        # Get second page
        response2 = client_authenticated.get(
            f"/highlights/{hl_typed_id}/annotations",
            params={"limit": 2, "cursor": data1["next_cursor"]},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 1
        assert data2["has_more"] is False

    def test_invalid_highlight_id_format(self, client_authenticated: TestClient):
        """Test that invalid highlight ID format returns 422."""
        response = client_authenticated.get("/highlights/invalid_id/annotations")
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_highlight_not_found(self, client_authenticated: TestClient):
        """Test that non-existent highlight returns 404."""
        fake_hl_id = to_api_id("highlight", uuid4())
        response = client_authenticated.get(f"/highlights/{fake_hl_id}/annotations")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_acl_other_user_highlight(
        self,
        client_authenticated: TestClient,
        other_user_highlight: Highlight,
    ):
        """Test that listing annotations on another user's highlight returns 404."""
        hl_typed_id = to_api_id("highlight", other_user_highlight.id)
        response = client_authenticated.get(f"/highlights/{hl_typed_id}/annotations")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"


class TestListUserAnnotations:
    """Test GET /users/{user_id}/annotations endpoint."""

    def test_happy_path(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test listing all annotations created by a user."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        # Create annotations
        ann = Annotation(
            user_id=authenticated_user.id,
            highlight_id=test_highlight.id,
            content="My annotation",
        )
        db_session.add(ann)
        db_session.flush()

        response = client_authenticated.get(f"/users/{user_typed_id}/annotations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["id"].startswith("ann_")
        assert data["has_more"] is False

    def test_empty_list(
        self,
        client_authenticated: TestClient,
        authenticated_user: User,
    ):
        """Test listing annotations for user with no annotations."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        response = client_authenticated.get(f"/users/{user_typed_id}/annotations")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0
        assert data["has_more"] is False

    def test_pagination(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        test_highlight: Highlight,
    ):
        """Test pagination for user's annotations."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        # Create 3 annotations
        for i in range(3):
            ann = Annotation(
                user_id=authenticated_user.id,
                highlight_id=test_highlight.id,
                content=f"Annotation {i}",
            )
            db_session.add(ann)
        db_session.flush()

        # Get first page (limit=2)
        response1 = client_authenticated.get(
            f"/users/{user_typed_id}/annotations",
            params={"limit": 2},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["items"]) == 2
        assert data1["has_more"] is True

        # Get second page
        response2 = client_authenticated.get(
            f"/users/{user_typed_id}/annotations",
            params={"limit": 2, "cursor": data1["next_cursor"]},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 1
        assert data2["has_more"] is False

    def test_invalid_user_id_format(self, client_authenticated: TestClient):
        """Test that invalid user ID format returns 422."""
        response = client_authenticated.get("/users/invalid_id/annotations")
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_user_id_type(self, client_authenticated: TestClient, test_document: Document):
        """Test that wrong typed ID (e.g., doc_ instead of usr_) returns 422."""
        doc_typed_id = to_api_id("document", test_document.id)

        response = client_authenticated.get(f"/users/{doc_typed_id}/annotations")

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_acl_other_user(
        self,
        client_authenticated: TestClient,
        other_user: User,
    ):
        """Test that accessing another user's annotations returns 404."""
        other_user_typed_id = to_api_id("user", other_user.id)

        response = client_authenticated.get(f"/users/{other_user_typed_id}/annotations")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "NOT_FOUND"

    def test_unauthenticated_returns_401(self, client: TestClient, authenticated_user: User):
        """Test that unauthenticated request returns 401."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        response = client.get(f"/users/{user_typed_id}/annotations")

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_REQUIRED"


class TestAnnotationErrorEnvelopes:
    """Test that error responses use canonical error envelope."""

    def test_error_envelope_structure(
        self,
        client_authenticated: TestClient,
        test_highlight: Highlight,
    ):
        """Test that errors include all required envelope fields."""
        hl_typed_id = to_api_id("highlight", test_highlight.id)

        response = client_authenticated.post(
            "/annotations",
            json={
                "highlight_id": hl_typed_id,
                "content": "   ",  # Empty content
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
