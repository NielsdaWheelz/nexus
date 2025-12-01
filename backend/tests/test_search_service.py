"""Tests for search service."""

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.chunk import ContentChunk
from app.models.document import Document
from app.models.user import User
from app.services.chunking import CHUNK_VERSION_DOCUMENT
from app.services.search import search_document_chunks_for_user


@pytest.fixture
def test_user1(db_session: Session) -> User:
    """Create first test user."""
    user = User(
        id=None,
        external_user_id="test_search_user1",
        email="search1@example.com",
    )
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_user2(db_session: Session) -> User:
    """Create second test user."""
    user = User(
        id=None,
        external_user_id="test_search_user2",
        email="search2@example.com",
    )
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)
    return user


def create_document(
    db_session: Session,
    user: User,
    title: str = "Test Document",
    embedding_status: str = "ready",
) -> Document:
    """Create a test document."""
    import hashlib

    canonical_text = "Sample text for search testing. This is a test document."
    canonical_hash = hashlib.sha256(canonical_text.encode()).hexdigest()
    content_hash = hashlib.sha256(b"test_blob").hexdigest()

    doc = Document(
        id=None,
        user_id=user.id,
        title=title,
        original_blob_key=f"blob_{title}",
        original_mime_type="text/html",
        original_size_bytes=100,
        content_hash=content_hash,
        canonical_text=canonical_text,
        canonical_hash=canonical_hash,
        text_byte_length=len(canonical_text.encode("utf-8")),
        extractor_version="html-v1",
        status="ready",
        chunk_version=CHUNK_VERSION_DOCUMENT,
        embedding_status=embedding_status,
    )
    db_session.add(doc)
    db_session.flush()
    db_session.refresh(doc)
    return doc


def create_embedded_chunk(
    db_session: Session,
    doc: Document,
    text: str = "Sample chunk text",
    embedding_vec: list[float] | None = None,
) -> ContentChunk:
    """Create a chunk with an embedding."""
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


class TestSearchACL:
    """Test ACL enforcement (user ownership)."""

    def test_search_only_user_owned_documents(
        self, db_session: Session, test_user1: User, test_user2: User
    ) -> None:
        """Test that search only returns results from user-owned documents."""
        # Create documents for both users
        doc1 = create_document(db_session, test_user1, title="User1 Doc")
        doc2 = create_document(db_session, test_user2, title="User2 Doc")

        # Add similar chunks to both documents
        create_embedded_chunk(db_session, doc1, text="Search term here")
        create_embedded_chunk(db_session, doc2, text="Search term here")

        # Mock query embedding
        query_embedding = [[0.1] * 1536]

        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            # User1 searches
            results = search_document_chunks_for_user(db_session, test_user1, "search term")

            # Should only get results from user1's documents
            assert len(results) > 0
            for hit in results:
                assert hit.document_id == doc1.id

    def test_search_document_filter(self, db_session: Session, test_user1: User) -> None:
        """Test filtering search by document_ids."""
        # Create multiple documents
        doc1 = create_document(db_session, test_user1, title="Doc 1")
        doc2 = create_document(db_session, test_user1, title="Doc 2")

        # Add similar chunks to both
        create_embedded_chunk(db_session, doc1, text="Common text")
        create_embedded_chunk(db_session, doc2, text="Common text")

        query_embedding = [[0.1] * 1536]

        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            # Search restricted to doc1 only
            results = search_document_chunks_for_user(
                db_session, test_user1, "common", document_ids=[doc1.id]
            )

            # Should only get results from doc1
            assert len(results) > 0
            for hit in results:
                assert hit.document_id == doc1.id


class TestSearchOrdering:
    """Test result ordering by similarity."""

    def test_results_ordered_by_similarity(self, db_session: Session, test_user1: User) -> None:
        """Test that results are ordered by similarity (highest first)."""
        doc = create_document(db_session, test_user1)

        # Create chunks with different embeddings
        # More similar to query (0.2) vs less similar (0.1)
        create_embedded_chunk(
            db_session, doc, text="Very similar text", embedding_vec=[0.2] * 1536
        )
        create_embedded_chunk(
            db_session, doc, text="Less similar text", embedding_vec=[0.1] * 1536
        )

        query_embedding = [[0.2] * 1536]  # Closer to chunk_similar

        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            results = search_document_chunks_for_user(db_session, test_user1, "query")

            # Results should be sorted by similarity
            assert len(results) >= 2
            # First result should have higher score than second
            assert results[0].score >= results[1].score


class TestSearchLimits:
    """Test limit enforcement."""

    def test_limit_capped_at_max(self, db_session: Session, test_user1: User) -> None:
        """Test that limit is capped at 100."""
        doc = create_document(db_session, test_user1)

        # Create many chunks
        for i in range(150):
            create_embedded_chunk(db_session, doc, text=f"Chunk {i}")

        query_embedding = [[0.1] * 1536]

        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            # Request more than max limit
            results = search_document_chunks_for_user(db_session, test_user1, "query", limit=200)

            # Should return at most 100
            assert len(results) <= 100

    def test_limit_default(self, db_session: Session, test_user1: User) -> None:
        """Test that default limit is 20."""
        doc = create_document(db_session, test_user1)

        # Create many chunks
        for i in range(50):
            create_embedded_chunk(db_session, doc, text=f"Chunk {i}")

        query_embedding = [[0.1] * 1536]

        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            results = search_document_chunks_for_user(db_session, test_user1, "query")

            # Default limit should be 20 or less
            assert len(results) <= 20


class TestSearchFiltering:
    """Test filtering logic."""

    def test_only_ready_documents_searched(self, db_session: Session, test_user1: User) -> None:
        """Test that only embedding_status=ready documents are searched."""
        # Create ready document
        ready_doc = create_document(db_session, test_user1, title="Ready", embedding_status="ready")
        create_embedded_chunk(db_session, ready_doc, text="Ready text")

        # Create not-ready document
        not_ready_doc = create_document(
            db_session, test_user1, title="NotReady", embedding_status="pending"
        )
        create_embedded_chunk(db_session, not_ready_doc, text="Not ready text")

        query_embedding = [[0.1] * 1536]

        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            results = search_document_chunks_for_user(db_session, test_user1, "query")

            # Should only get results from ready documents
            assert all(
                hit.document_id == ready_doc.id for hit in results
            ), "Should only search ready documents"

    def test_only_embedded_chunks_searched(self, db_session: Session, test_user1: User) -> None:
        """Test that only chunks with embeddings are searched."""
        doc = create_document(db_session, test_user1)

        # Create embedded chunk
        embedded = create_embedded_chunk(db_session, doc, text="Embedded")

        # Create non-embedded chunk (no embedding)
        not_embedded = ContentChunk(
            id=None,
            media_type="document",
            media_id=doc.id,
            chunk_version=CHUNK_VERSION_DOCUMENT,
            text_start=0,
            text_end=10,
            text="Not embedded",
            embedding=None,  # No embedding
        )
        db_session.add(not_embedded)
        db_session.flush()

        query_embedding = [[0.1] * 1536]

        with patch("app.services.search.embed_texts_with_default_client") as mock_embed:
            mock_embed.return_value = query_embedding

            results = search_document_chunks_for_user(db_session, test_user1, "query")

            # Should only get embedded chunks
            assert all(
                hit.chunk_id == embedded.id for hit in results
            ), "Should only search embedded chunks"
