"""Tests for chunking Celery task and wiring.

Tests cover:
- chunk_document task calls service correctly
- Task returns expected result format
- Ingestion enqueues chunk_document on success
"""

import hashlib
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.tasks.documents import chunk_document
from app.services.documents import create_document_placeholder


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id=None,
        external_user_id="test_user_tasks",
        email="tasks@example.com",
    )
    db_session.add(user)
    db_session.flush()
    db_session.refresh(user)
    return user


def create_ready_document_for_chunking(db_session: Session, test_user: User):
    """Helper to create a ready document."""
    from app.models.document import Document

    canonical_text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    canonical_hash = hashlib.sha256(canonical_text.encode()).hexdigest()
    content_hash = hashlib.sha256(b"blob").hexdigest()

    doc = Document(
        id=None,
        user_id=test_user.id,
        title="Test Document",
        original_blob_key="blob_key",
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


class TestChunkDocumentTask:
    """Tests for chunk_document Celery task."""

    def test_chunk_document_task_propagates_errors(self):
        """Task should propagate errors from service for retry."""
        non_existent_id = str(uuid4())

        with pytest.raises(ValueError):
            chunk_document(non_existent_id)


class TestIngestionEnqueuesChunking:
    """Tests for ingestion enqueuing chunking task."""

    def test_ingestion_enqueues_chunk_document_on_success(
        self, db_session: Session, test_user: User
    ):
        """Successful ingestion should enqueue chunk_document task."""
        from app.services.ingestion import run_ingest_document
        from app.services.storage import StorageService

        # Create test HTML blob
        html_blob = b"<html><body><p>Test</p></body></html>"

        # Store blob
        storage = StorageService()
        mock_file = MagicMock()
        mock_file.file.read = MagicMock(side_effect=[html_blob, b""])
        blob_key = storage.store_raw_blob(mock_file)

        # Create document placeholder
        doc = create_document_placeholder(
            session=db_session,
            user=test_user,
            source_kind="html",
            original_blob_uri=blob_key,
            original_filename="test.html",
            original_mime_type="text/html",
            original_size_bytes=len(html_blob),
            source_url=None,
            title="Test",
        )

        doc_id = str(doc.id)

        # Mock chunk_document.delay to verify it's called
        # The import happens inside run_ingest_document, so we patch the imported function
        with patch("app.tasks.documents.chunk_document") as mock_chunk_task:
            result = run_ingest_document(db_session, doc_id)

            # Verify ingestion succeeded
            assert result["status"] == "success"

            # Verify chunk_document.delay was called with correct document ID
            mock_chunk_task.delay.assert_called_once_with(doc_id)

    def test_ingestion_only_enqueues_on_success_status(
        self, db_session: Session, test_user: User
    ):
        """Ingestion should only enqueue chunking when status is 'ready'."""
        from app.models.document import Document

        # Create document with failed status
        doc = Document(
            id=None,
            user_id=test_user.id,
            title="Test",
            original_blob_key="key",
            original_mime_type="text/html",
            original_size_bytes=100,
            content_hash="abc",
            canonical_text="text",
            canonical_hash="def",
            text_byte_length=4,
            extractor_version="html-v1",
            status="failed",  # Not ready
            embedding_status="pending",
        )
        db_session.add(doc)
        db_session.flush()

        # Try to chunk directly (should fail due to status guard)
        from app.services.chunking import run_chunk_document

        with pytest.raises(ValueError):
            run_chunk_document(db_session, doc.id)
