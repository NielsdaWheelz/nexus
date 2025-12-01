"""Tests for search API endpoint (POST /search/chunks).

Tests cover:
- Happy path with embedded chunks returning similarity results
- Response envelope structure (DataEnvelope[ChunkSearchResponse])
- Typed ID format for chunk_id and document_id
- Authentication (401 when unauthenticated)
- Validation errors (query length, invalid document_ids)
- ACL enforcement (only user-owned documents)
"""

import hashlib
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.ids import to_api_id
from app.models.chunk import ContentChunk
from app.models.document import Document
from app.models.user import User
from app.services.chunking import CHUNK_VERSION_DOCUMENT


@pytest.fixture
def authenticated_user(db_session: Session) -> User:
    """Create an authenticated test user."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_search_test_user",
        email="searchtest@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def other_user(db_session: Session) -> User:
    """Create another test user for ACL testing."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_other_search_user",
        email="othersearchtest@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_ready_document_with_embedding(
    db_session: Session,
    user: User,
    title: str = "Test Document",
) -> Document:
    """Create a document in ready status with embedding_status=ready."""
    canonical_text = f"Test content for {title}. This is sample text for testing search."
    canonical_hash = hashlib.sha256(canonical_text.encode()).hexdigest()
    content_hash = hashlib.sha256(f"blob_{title}".encode()).hexdigest()

    doc = Document(
        user_id=user.id,
        title=title,
        original_blob_key=f"s3://bucket/{title}.pdf",
        original_mime_type="application/pdf",
        original_size_bytes=1000,
        content_hash=content_hash,
        canonical_text=canonical_text,
        canonical_hash=canonical_hash,
        text_byte_length=len(canonical_text.encode("utf-8")),
        extractor_version="html-v1",
        status="ready",
        chunk_version=CHUNK_VERSION_DOCUMENT,
        embedding_status="ready",
        embedding_model="text-embedding-3-small",
    )
    db_session.add(doc)
    db_session.flush()
    return doc


def create_embedded_chunk(
    db_session: Session,
    doc: Document,
    text: str = "Sample chunk text for search",
    embedding_vec: list[float] | None = None,
) -> ContentChunk:
    """Create a content chunk with an embedding."""
    if embedding_vec is None:
        embedding_vec = [0.1] * 1536

    chunk = ContentChunk(
        id=None,
        media_type="document",
        media_id=doc.id,
        chunk_version=CHUNK_VERSION_DOCUMENT,
        text_start=0,
        text_end=len(text),
        text=text,
        embedding=embedding_vec,
        embedding_model="text-embedding-3-small",
    )
    db_session.add(chunk)
    db_session.flush()
    db_session.refresh(chunk)
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


class TestSearchChunksHappyPath:
    """Test successful search scenarios."""

    def test_search_returns_results(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
    ):
        """Test basic search returns matching chunks."""
        # Setup: create document with embedded chunk
        doc = create_ready_document_with_embedding(db_session, authenticated_user)
        chunk = create_embedded_chunk(db_session, doc, text="Important information about cats")

        # Mock the embedding call
        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "cats"},
            )

        assert response.status_code == 200
        data = response.json()

        # Verify envelope structure
        assert "data" in data
        assert "items" in data["data"]
        assert "next_cursor" in data["data"]
        assert "has_more" in data["data"]

        # Verify results
        items = data["data"]["items"]
        assert len(items) >= 1

        # Check first result structure
        hit = items[0]
        assert "chunk_id" in hit
        assert "document_id" in hit
        assert "score" in hit
        assert "text" in hit
        assert "text_start" in hit
        assert "text_end" in hit

    def test_response_uses_typed_ids(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
    ):
        """Test that response uses typed IDs (chunk_<uuid>, doc_<uuid>)."""
        doc = create_ready_document_with_embedding(db_session, authenticated_user)
        chunk = create_embedded_chunk(db_session, doc)

        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "test"},
            )

        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) >= 1

        hit = items[0]
        # Verify typed ID format
        assert hit["chunk_id"].startswith("chunk_")
        assert hit["document_id"].startswith("doc_")

        # Verify IDs match our test data
        assert hit["chunk_id"] == to_api_id("chunk", chunk.id)
        assert hit["document_id"] == to_api_id("document", doc.id)

    def test_search_with_limit(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
    ):
        """Test that limit parameter is respected."""
        doc = create_ready_document_with_embedding(db_session, authenticated_user)

        # Create multiple chunks
        for i in range(5):
            create_embedded_chunk(db_session, doc, text=f"Chunk {i}")

        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "test", "limit": 2},
            )

        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) <= 2

    def test_search_with_document_filter(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
    ):
        """Test filtering search by document_ids."""
        # Create two documents
        doc1 = create_ready_document_with_embedding(db_session, authenticated_user, title="Doc 1")
        doc2 = create_ready_document_with_embedding(db_session, authenticated_user, title="Doc 2")

        # Add chunks to both
        create_embedded_chunk(db_session, doc1, text="Content in doc 1")
        create_embedded_chunk(db_session, doc2, text="Content in doc 2")

        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            # Search only in doc1
            doc1_typed_id = to_api_id("document", doc1.id)
            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "content", "document_ids": [doc1_typed_id]},
            )

        assert response.status_code == 200
        items = response.json()["data"]["items"]

        # All results should be from doc1
        for hit in items:
            assert hit["document_id"] == doc1_typed_id


class TestSearchChunksAuthentication:
    """Test authentication requirements."""

    def test_unauthenticated_returns_401(
        self,
        client: TestClient,
    ):
        """Test that unauthenticated request returns 401."""
        response = client.post(
            "/search/chunks",
            json={"query": "test"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "AUTH_REQUIRED"


class TestSearchChunksValidation:
    """Test request validation."""

    def test_empty_query_returns_422(
        self,
        client_authenticated: TestClient,
    ):
        """Test that empty query returns validation error."""
        response = client_authenticated.post(
            "/search/chunks",
            json={"query": ""},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_query_too_long_returns_422(
        self,
        client_authenticated: TestClient,
    ):
        """Test that query exceeding 2000 chars returns validation error."""
        long_query = "x" * 2001

        response = client_authenticated.post(
            "/search/chunks",
            json={"query": long_query},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_limit_returns_422(
        self,
        client_authenticated: TestClient,
    ):
        """Test that limit > 100 returns validation error."""
        response = client_authenticated.post(
            "/search/chunks",
            json={"query": "test", "limit": 150},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_limit_zero_returns_422(
        self,
        client_authenticated: TestClient,
    ):
        """Test that limit=0 returns validation error."""
        response = client_authenticated.post(
            "/search/chunks",
            json={"query": "test", "limit": 0},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_document_id_format_returns_422(
        self,
        client_authenticated: TestClient,
    ):
        """Test that invalid document_id format returns validation error."""
        response = client_authenticated.post(
            "/search/chunks",
            json={"query": "test", "document_ids": ["invalid_format"]},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_wrong_typed_id_type_returns_422(
        self,
        client_authenticated: TestClient,
        authenticated_user: User,
    ):
        """Test that wrong typed ID type (e.g., usr_ instead of doc_) returns 422."""
        user_typed_id = to_api_id("user", authenticated_user.id)

        response = client_authenticated.post(
            "/search/chunks",
            json={"query": "test", "document_ids": [user_typed_id]},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestSearchChunksACL:
    """Test ACL enforcement."""

    def test_search_excludes_other_user_documents(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
        other_user: User,
    ):
        """Test that search only returns results from user-owned documents."""
        # Create documents for both users
        my_doc = create_ready_document_with_embedding(db_session, authenticated_user, title="My Doc")
        other_doc = create_ready_document_with_embedding(db_session, other_user, title="Other Doc")

        # Add similar chunks to both
        create_embedded_chunk(db_session, my_doc, text="Search term here")
        create_embedded_chunk(db_session, other_doc, text="Search term here")

        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "search term"},
            )

        assert response.status_code == 200
        items = response.json()["data"]["items"]

        # All results should be from authenticated user's document
        my_doc_typed_id = to_api_id("document", my_doc.id)
        for hit in items:
            assert hit["document_id"] == my_doc_typed_id

    def test_search_empty_when_no_owned_documents(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        other_user: User,
    ):
        """Test that search returns empty when user has no documents."""
        # Create document for other user only
        other_doc = create_ready_document_with_embedding(db_session, other_user)
        create_embedded_chunk(db_session, other_doc)

        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "test"},
            )

        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) == 0


class TestSearchChunksEnvelopeStructure:
    """Test response envelope structure."""

    def test_envelope_has_all_required_fields(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
    ):
        """Test that response envelope has all required fields."""
        doc = create_ready_document_with_embedding(db_session, authenticated_user)
        create_embedded_chunk(db_session, doc)

        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "test"},
            )

        assert response.status_code == 200
        data = response.json()

        # Top level
        assert "data" in data

        # Data envelope
        envelope = data["data"]
        assert "items" in envelope
        assert "next_cursor" in envelope
        assert "has_more" in envelope

        # Items structure
        assert isinstance(envelope["items"], list)
        assert isinstance(envelope["has_more"], bool)
        # next_cursor can be None
        assert envelope["next_cursor"] is None or isinstance(envelope["next_cursor"], str)

    def test_hit_has_all_required_fields(
        self,
        client_authenticated: TestClient,
        db_session: Session,
        authenticated_user: User,
    ):
        """Test that each hit has all required fields with correct types."""
        doc = create_ready_document_with_embedding(db_session, authenticated_user)
        chunk = create_embedded_chunk(db_session, doc, text="Test chunk text")

        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "test"},
            )

        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert len(items) >= 1

        hit = items[0]
        # Check field presence and types
        assert isinstance(hit["chunk_id"], str)
        assert isinstance(hit["document_id"], str)
        assert isinstance(hit["score"], float)
        assert isinstance(hit["text"], str)
        assert isinstance(hit["text_start"], int)
        assert isinstance(hit["text_end"], int)

        # Score should be between 0 and 1 (or close, accounting for cosine similarity)
        assert hit["score"] >= -1 and hit["score"] <= 1

    def test_empty_results_returns_valid_envelope(
        self,
        client_authenticated: TestClient,
    ):
        """Test that empty results still return valid envelope structure."""
        query_embedding = [[0.1] * 1536]
        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            response = client_authenticated.post(
                "/search/chunks",
                json={"query": "test"},
            )

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert data["data"]["items"] == []
        assert data["data"]["has_more"] is False
        assert data["data"]["next_cursor"] is None

