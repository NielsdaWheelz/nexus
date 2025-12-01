"""Tests for the document chunking service.

Tests cover:
- Happy path: chunking a ready document
- Idempotency: re-chunking unchanged document produces no duplicates
- Re-chunking on canonical text change
- Status guards
- Empty canonical_text guard
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.chunk import ContentChunk
from app.models.user import User
from app.services.chunking import CHUNK_VERSION_DOCUMENT, run_chunk_document
from app.services.documents import create_document_placeholder
from app.services.ingestion import canonicalize_document
from app.services.storage import StorageService


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id=None,
        external_user_id="test_user_chunk",
        email="chunk@example.com",
    )
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_html_blob() -> bytes:
    """Create a test HTML document with multiple paragraphs."""
    return b"""<!DOCTYPE html>
<html>
<body>
<h1>Document Title</h1>
<p>This is the first paragraph with some content.</p>
<p>This is the second paragraph with more content.</p>
<p>This is the third paragraph.</p>
</body>
</html>
"""


def create_ready_document(
    db_session: Session, test_user: User, canonical_text: str = None
):
    """Helper to create a document in ready status with canonical text."""
    from app.models.document import Document

    if canonical_text is None:
        canonical_text = "Test paragraph one.\n\nTest paragraph two.\n\nTest paragraph three."

    canonical_hash = hashlib.sha256(canonical_text.encode()).hexdigest()
    content_hash = hashlib.sha256(b"test_blob").hexdigest()

    doc = Document(
        id=None,
        user_id=test_user.id,
        title="Test Document",
        original_blob_key="test_blob_key",
        original_mime_type="text/html",
        original_size_bytes=100,
        content_hash=content_hash,
        canonical_text=canonical_text,
        canonical_hash=canonical_hash,
        text_byte_length=len(canonical_text.encode("utf-8")),
        extractor_version="html-v1",
        status="ready",
        embedding_status="pending",
    )
    db_session.add(doc)
    db_session.flush()
    db_session.refresh(doc)
    return doc


class TestRunChunkDocument:
    """Tests for run_chunk_document service function."""

    def test_chunk_ready_document_happy_path(self, db_session: Session, test_user: User):
        """Happy path: chunk a ready document."""
        doc = create_ready_document(db_session, test_user)
        doc_id = doc.id

        # Run chunking
        chunks_created = run_chunk_document(db_session, doc_id)

        # Verify chunks were created
        assert chunks_created > 0

        # Verify chunks exist in DB
        db_session.refresh(doc)
        chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc_id,
            )
            .all()
        )

        assert len(chunks) == chunks_created
        assert chunks_created >= 1

        # Verify all chunks have correct properties
        for chunk in chunks:
            assert chunk.media_type == "document"
            assert chunk.media_id == doc_id
            assert chunk.chunk_version == CHUNK_VERSION_DOCUMENT
            assert chunk.embedding_model is None
            assert chunk.text_start >= 0
            assert chunk.text_end > chunk.text_start
            assert chunk.text
            assert isinstance(chunk.chunk_metadata, dict)

        # Verify document was updated
        assert doc.chunk_version == CHUNK_VERSION_DOCUMENT

    def test_chunk_non_overlapping(self, db_session: Session, test_user: User):
        """Chunks should be non-overlapping."""
        doc = create_ready_document(db_session, test_user)

        run_chunk_document(db_session, doc.id)

        chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc.id,
            )
            .order_by(ContentChunk.text_start)
            .all()
        )

        for i in range(len(chunks) - 1):
            assert chunks[i].text_end <= chunks[i + 1].text_start

    def test_chunk_sorted_by_start(self, db_session: Session, test_user: User):
        """Chunks should be sorted by text_start."""
        doc = create_ready_document(db_session, test_user)

        run_chunk_document(db_session, doc.id)

        chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc.id,
            )
            .all()
        )

        starts = [c.text_start for c in chunks]
        assert starts == sorted(starts)

    def test_idempotent_rechunk_unchanged_document(
        self, db_session: Session, test_user: User
    ):
        """Re-chunking an unchanged document is idempotent (no duplicates)."""
        doc = create_ready_document(db_session, test_user)
        doc_id = doc.id

        # First chunk
        chunks_created_1 = run_chunk_document(db_session, doc_id)
        db_session.flush()

        # Count chunks
        count_1 = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc_id,
            )
            .count()
        )

        # Re-chunk with same canonical_text
        chunks_created_2 = run_chunk_document(db_session, doc_id)

        # Count chunks again
        count_2 = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc_id,
            )
            .count()
        )

        # Should return 0 on idempotent re-run (already chunked)
        assert chunks_created_2 == 0

        # Chunk counts should match
        assert count_1 == count_2

    def test_rechunk_on_canonical_change(self, db_session: Session, test_user: User):
        """Changing canonical_text results in new chunks being created."""
        doc = create_ready_document(db_session, test_user, "Original text\n\nParagraph 2")

        # First chunk
        chunks_created_1 = run_chunk_document(db_session, doc.id)
        db_session.flush()

        # Get old chunks
        old_chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc.id,
            )
            .all()
        )
        old_texts = {c.text for c in old_chunks}

        # Modify document
        new_text = "Completely different text\n\nNew paragraph"
        doc.canonical_text = new_text
        doc.canonical_hash = hashlib.sha256(new_text.encode()).hexdigest()
        doc.chunk_version = None  # Reset to trigger re-chunking
        db_session.flush()

        # Re-chunk
        chunks_created_2 = run_chunk_document(db_session, doc.id)

        # Get new chunks
        new_chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc.id,
            )
            .all()
        )
        new_texts = {c.text for c in new_chunks}

        # Should have new chunks
        assert chunks_created_2 > 0

        # New chunks should have new text
        assert new_texts != old_texts or len(old_chunks) != len(new_chunks)

    def test_guard_non_ready_status(self, db_session: Session, test_user: User):
        """Should raise error if document status is not ready."""
        from app.models.document import Document

        doc = Document(
            id=None,
            user_id=test_user.id,
            title="Test",
            original_blob_key="test",
            original_mime_type="text/html",
            original_size_bytes=100,
            content_hash="abc",
            canonical_text="some text",
            canonical_hash="def",
            text_byte_length=9,
            extractor_version="html-v1",
            status="pending",  # Not ready
            embedding_status="pending",
        )
        db_session.add(doc)
        db_session.flush()

        with pytest.raises(ValueError, match="status is pending"):
            run_chunk_document(db_session, doc.id)

    def test_guard_empty_canonical_text(self, db_session: Session, test_user: User):
        """Should raise error if canonical_text is empty."""
        from app.models.document import Document

        doc = Document(
            id=None,
            user_id=test_user.id,
            title="Test",
            original_blob_key="test",
            original_mime_type="text/html",
            original_size_bytes=100,
            content_hash="abc",
            canonical_text="",  # Empty
            canonical_hash="def",
            text_byte_length=0,
            extractor_version="html-v1",
            status="ready",
            embedding_status="pending",
        )
        db_session.add(doc)
        db_session.flush()

        with pytest.raises(ValueError, match="canonical_text is empty"):
            run_chunk_document(db_session, doc.id)

    def test_guard_document_not_found(self, db_session: Session):
        """Should raise error if document not found."""
        from uuid import uuid4

        non_existent_id = uuid4()

        with pytest.raises(ValueError, match="Document not found"):
            run_chunk_document(db_session, non_existent_id)

    def test_chunk_metadata_populated(self, db_session: Session, test_user: User):
        """Chunk metadata should contain expected fields."""
        doc = create_ready_document(db_session, test_user)

        run_chunk_document(db_session, doc.id)

        chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc.id,
            )
            .all()
        )

        for chunk in chunks:
            assert "index" in chunk.chunk_metadata
            assert "approx_char_length" in chunk.chunk_metadata
            assert "approx_paragraphs" in chunk.chunk_metadata
            assert chunk.chunk_metadata["approx_char_length"] > 0

    def test_chunk_version_set_correctly(self, db_session: Session, test_user: User):
        """All chunks should have correct chunk_version."""
        doc = create_ready_document(db_session, test_user)

        run_chunk_document(db_session, doc.id)

        chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc.id,
            )
            .all()
        )

        for chunk in chunks:
            assert chunk.chunk_version == CHUNK_VERSION_DOCUMENT

    def test_embedding_model_is_null(self, db_session: Session, test_user: User):
        """All chunks should have embedding_model = NULL."""
        doc = create_ready_document(db_session, test_user)

        run_chunk_document(db_session, doc.id)

        chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc.id,
            )
            .all()
        )

        for chunk in chunks:
            assert chunk.embedding_model is None

    def test_document_status_unaffected_by_chunking(self, db_session: Session, test_user: User):
        """Chunking should NOT modify document status (stays 'ready')."""
        doc = create_ready_document(db_session, test_user)
        original_status = doc.status

        run_chunk_document(db_session, doc.id)
        db_session.refresh(doc)

        # Status should remain unchanged
        assert doc.status == original_status
        assert doc.status == "ready"

    def test_chunking_error_does_not_brick_document(self, db_session: Session, test_user: User):
        """Chunking errors should not change document status to failed.

        This allows Celery to retry independently without document being stuck.
        """
        from app.models.document import Document

        doc = Document(
            id=None,
            user_id=test_user.id,
            title="Test",
            original_blob_key="key",
            original_mime_type="text/html",
            original_size_bytes=100,
            content_hash="abc",
            canonical_text="test",
            canonical_hash="def",
            text_byte_length=4,
            extractor_version="html-v1",
            status="ready",
            embedding_status="pending",
        )
        db_session.add(doc)
        db_session.flush()
        original_status = doc.status

        # Simulate a chunking failure by patching the algorithm
        with patch("app.services.chunking.chunk_canonical_text") as mock_chunk:
            mock_chunk.side_effect = Exception("Simulated chunking error")

            with pytest.raises(Exception):
                run_chunk_document(db_session, doc.id)

        # Document status should NOT be modified to 'failed'
        db_session.refresh(doc)
        assert doc.status == original_status
        assert doc.status == "ready"

    def test_remap_pipeline_can_call_chunk_independently(
        self, db_session: Session, test_user: User
    ):
        """run_chunk_document can be called from remap pipeline independently.

        Simulates: canonical_text changes → highlights remap trigger → re-chunk
        """
        doc = create_ready_document(
            db_session, test_user, "Original paragraph one.\n\nOriginal paragraph two."
        )

        # First chunk with original text
        chunks_1 = run_chunk_document(db_session, doc.id)
        assert chunks_1 > 0
        db_session.flush()

        # Simulate canonical_text change (e.g., from re-ingestion)
        new_text = "Brand new paragraph one.\n\nBrand new paragraph two.\n\nBrand new paragraph three."
        doc.canonical_text = new_text
        doc.canonical_hash = hashlib.sha256(new_text.encode()).hexdigest()
        doc.chunk_version = None  # Force re-chunking (simulate remap trigger)
        db_session.flush()

        # Call chunking from "remap pipeline" context
        # (This would be called from app/tasks/remap.py or similar)
        chunks_2 = run_chunk_document(db_session, doc.id)

        # Should have created new chunks
        assert chunks_2 > 0

        # Verify old chunks are gone
        chunks = (
            db_session.query(ContentChunk)
            .filter(
                ContentChunk.media_type == "document",
                ContentChunk.media_id == doc.id,
            )
            .all()
        )

        # All chunks should have new content
        chunk_texts = {c.text for c in chunks}
        old_text = "Original paragraph"
        new_text_sample = "Brand new"

        for text in chunk_texts:
            assert old_text not in text, f"Old text found in chunk: {text}"
            assert new_text_sample in text, f"New text not found in chunk: {text}"
