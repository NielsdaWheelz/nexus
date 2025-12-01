"""Tests for embeddings service (run_embed_document)."""

import hashlib
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ExternalDependencyError, NotFoundError, ValidationAppError
from app.models.chunk import ContentChunk
from app.models.document import Document
from app.models.user import User
from app.services.chunking import CHUNK_VERSION_DOCUMENT
from app.services.embeddings import EmbeddingResult, run_embed_document


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id=None,
        external_user_id="test_embed_user",
        email="embedtest@example.com",
    )
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)
    return user


def create_ready_document(
    db_session: Session,
    user: User,
    canonical_text: str | None = None,
    chunk_version: str = CHUNK_VERSION_DOCUMENT,
    status: str = "ready",
) -> Document:
    """Helper to create a document in ready status."""
    if canonical_text is None:
        canonical_text = "Test paragraph one.\n\nTest paragraph two.\n\nTest paragraph three."

    canonical_hash = hashlib.sha256(canonical_text.encode()).hexdigest()
    content_hash = hashlib.sha256(b"test_blob").hexdigest()

    doc = Document(
        id=None,
        user_id=user.id,
        title="Test Document",
        original_blob_key="test_blob_key",
        original_mime_type="text/html",
        original_size_bytes=100,
        content_hash=content_hash,
        canonical_text=canonical_text,
        canonical_hash=canonical_hash,
        text_byte_length=len(canonical_text.encode("utf-8")),
        extractor_version="html-v1",
        status=status,
        chunk_version=chunk_version,
        embedding_status="pending",
    )
    db_session.add(doc)
    db_session.flush()
    db_session.refresh(doc)
    return doc


def create_content_chunks(
    db_session: Session,
    doc: Document,
    count: int = 3,
) -> list[ContentChunk]:
    """Helper to create content chunks for a document."""
    chunks = []
    text = doc.canonical_text
    for i in range(count):
        chunk_start = i * 20
        chunk_end = min(chunk_start + 20, len(text))
        chunk_text = text[chunk_start:chunk_end]

        chunk = ContentChunk(
            id=None,
            media_type="document",
            media_id=doc.id,
            chunk_version=CHUNK_VERSION_DOCUMENT,
            text_start=chunk_start,
            text_end=chunk_end,
            text=chunk_text,
        )
        db_session.add(chunk)
        chunks.append(chunk)

    db_session.flush()
    return chunks


class TestEmbeddingsServiceStatusGuards:
    """Test status validation guards."""

    def test_document_not_found(self, db_session: Session) -> None:
        """Test NotFoundError when document doesn't exist."""
        fake_uuid = UUID("00000000-0000-0000-0000-000000000000")

        with pytest.raises(NotFoundError) as exc_info:
            run_embed_document(db_session, fake_uuid)

        assert "not found" in str(exc_info.value).lower()

    def test_document_status_not_ready(self, db_session: Session, test_user: User) -> None:
        """Test ValidationAppError when doc.status != 'ready'."""
        doc = create_ready_document(db_session, test_user, status="processing")

        with pytest.raises(ValidationAppError) as exc_info:
            run_embed_document(db_session, doc.id)

        assert "processing" in str(exc_info.value).lower()

    def test_chunk_version_mismatch(self, db_session: Session, test_user: User) -> None:
        """Test ValidationAppError when chunk_version doesn't match."""
        doc = create_ready_document(
            db_session, test_user, chunk_version="old_chunking_v0"
        )

        with pytest.raises(ValidationAppError) as exc_info:
            run_embed_document(db_session, doc.id)

        assert "chunk_version" in str(exc_info.value).lower()
        assert "mismatch" in str(exc_info.value).lower()

    def test_no_chunks_found(self, db_session: Session, test_user: User) -> None:
        """Test ValidationAppError when document has no chunks."""
        doc = create_ready_document(db_session, test_user)
        # Don't create any chunks

        with pytest.raises(ValidationAppError) as exc_info:
            run_embed_document(db_session, doc.id)

        assert "no content chunks" in str(exc_info.value).lower()

    def test_too_many_chunks(self, db_session: Session, test_user: User) -> None:
        """Test ValidationAppError when chunks exceed max limit."""
        settings = get_settings()
        max_chunks = settings.EMBEDDING_MAX_CHUNKS_PER_DOC

        doc = create_ready_document(db_session, test_user)

        # Create more chunks than allowed
        for i in range(max_chunks + 10):
            chunk = ContentChunk(
                id=None,
                media_type="document",
                media_id=doc.id,
                chunk_version=CHUNK_VERSION_DOCUMENT,
                text_start=i * 10,
                text_end=(i + 1) * 10,
                text=f"Chunk {i}",
            )
            db_session.add(chunk)

        db_session.flush()

        with pytest.raises(ValidationAppError) as exc_info:
            run_embed_document(db_session, doc.id)

        assert "too many chunks" in str(exc_info.value).lower()


class TestEmbeddingsServiceIdempotency:
    """Test idempotent behavior."""

    def test_idempotency_no_reembedding(
        self, db_session: Session, test_user: User
    ) -> None:
        """Test that second run with same model doesn't re-embed."""
        doc = create_ready_document(db_session, test_user)
        chunks = create_content_chunks(db_session, doc, count=2)

        # First embedding
        mock_embeddings_1 = [[0.1] * 1536 for _ in chunks]
        with patch(
            "app.services.embeddings.embed_texts_with_default_client",
            return_value=mock_embeddings_1,
        ):
            result1 = run_embed_document(db_session, doc.id)
            db_session.commit()

        assert result1.newly_embedded_chunks == 2
        assert result1.total_chunks == 2

        # Verify embeddings were stored
        for chunk in chunks:
            db_session.refresh(chunk)
            assert chunk.embedding is not None

        # Second embedding (should be no-op)
        with patch(
            "app.services.embeddings.embed_texts_with_default_client"
        ) as mock_embed:
            result2 = run_embed_document(db_session, doc.id)
            db_session.commit()

            # Embedding client should NOT be called (no-op)
            mock_embed.assert_not_called()

        assert result2.newly_embedded_chunks == 0
        assert result2.total_chunks == 2

    def test_returns_correct_result_counts(
        self, db_session: Session, test_user: User
    ) -> None:
        """Test that result counts are accurate."""
        doc = create_ready_document(db_session, test_user)
        chunks = create_content_chunks(db_session, doc, count=5)

        mock_embeddings = [[0.1] * 1536 for _ in chunks]
        with patch(
            "app.services.embeddings.embed_texts_with_default_client",
            return_value=mock_embeddings,
        ):
            result = run_embed_document(db_session, doc.id)
            db_session.commit()

        assert isinstance(result, EmbeddingResult)
        assert result.document_id == doc.id
        assert result.total_chunks == 5
        assert result.newly_embedded_chunks == 5


class TestEmbeddingsServiceExternalErrors:
    """Test external dependency error handling."""

    def test_external_dependency_error_propagates(
        self, db_session: Session, test_user: User
    ) -> None:
        """Test that ExternalDependencyError propagates for Celery retry."""
        doc = create_ready_document(db_session, test_user)
        create_content_chunks(db_session, doc, count=1)

        # Simulate OpenAI API error
        with patch(
            "app.services.embeddings.embed_texts_with_default_client",
            side_effect=ExternalDependencyError(message="OpenAI quota exceeded"),
        ):
            with pytest.raises(ExternalDependencyError):
                run_embed_document(db_session, doc.id)

        # Document status should remain pending on error (Celery task handles retry/failure marking)
        # The check constraint only allows ('pending', 'ready', 'failed') - no intermediate "processing"
        db_session.refresh(doc)
        assert doc.embedding_status == "pending"


class TestEmbeddingsServiceStatusTransitions:
    """Test document status transitions during embedding."""

    def test_status_transitions_on_success(
        self, db_session: Session, test_user: User
    ) -> None:
        """Test that embedding_status transitions: pending -> ready on success."""
        doc = create_ready_document(db_session, test_user)
        create_content_chunks(db_session, doc, count=1)

        assert doc.embedding_status == "pending"

        mock_embeddings = [[0.1] * 1536]
        with patch(
            "app.services.embeddings.embed_texts_with_default_client",
            return_value=mock_embeddings,
        ):
            run_embed_document(db_session, doc.id)

        db_session.flush()
        db_session.refresh(doc)

        assert doc.embedding_status == "ready"
        assert doc.embedding_model == get_settings().EMBEDDING_MODEL_DOCUMENT

    def test_embedding_model_set_correctly(
        self, db_session: Session, test_user: User
    ) -> None:
        """Test that embedding_model is set to configured model."""
        doc = create_ready_document(db_session, test_user)
        create_content_chunks(db_session, doc, count=1)

        settings = get_settings()
        mock_embeddings = [[0.1] * 1536]

        with patch(
            "app.services.embeddings.embed_texts_with_default_client",
            return_value=mock_embeddings,
        ):
            run_embed_document(db_session, doc.id)

        db_session.flush()
        db_session.refresh(doc)

        assert doc.embedding_model == settings.EMBEDDING_MODEL_DOCUMENT
