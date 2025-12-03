"""Full pipeline integration tests with real Celery workers.

These tests verify the complete ingest→chunk→embed pipeline with actual workers,
detecting race conditions, flush/commit timing issues, and concurrency bugs
that eager mode would hide.

IMPORTANT DESIGN NOTE:
The spec's tests used mocks for canonicalize_document and embed_texts, but this
doesn't work for real integration tests because:
1. Worker is a separate process - mocks aren't shared
2. Worker creates its own db session - transaction isolation

Instead, these tests:
1. Use committed database sessions (data visible to workers)
2. Use real HTML files that can be canonicalized
3. Set OPENAI_API_KEY=test-skip to skip actual embedding API calls
4. Verify database state changes after pipeline completion

Run with: make backend-test-integration
"""

import hashlib
import time
import uuid as uuid_lib
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.chunk import ContentChunk
from app.models.document import Document
from app.models.user import User
from app.services.storage import StorageService
from app.tasks.documents import ingest_document


@pytest.mark.integration
class TestFullPipeline:
    """Test complete ingest→chunk→embed pipeline with real workers."""

    def test_full_pipeline_end_to_end(
        self,
        committed_db_session: Session,
        integration_test_user: User,
        celery_integration_app,
        wait_for_task_fixture,
        clear_queues,
    ):
        """
        Verify full pipeline: ingestion→chunking→embedding.

        Tests:
        - ingest_document task receives and processes document
        - Document status transitions correctly
        - Chunks are created after pipeline completion

        Note: Embedding may be skipped in test environment if OPENAI_API_KEY
        is not configured. The test verifies the pipeline runs without error.
        """
        # Create a real HTML file that can be canonicalized
        html_content = b"""
        <!DOCTYPE html>
        <html>
        <head><title>Integration Test Document</title></head>
        <body>
            <h1>Test Article</h1>
            <p>This is paragraph one with some test content.</p>
            <p>This is paragraph two with different content.</p>
            <p>This is paragraph three for chunking tests.</p>
        </body>
        </html>
        """

        # Store the HTML file
        storage = StorageService()
        from unittest.mock import MagicMock

        mock_file = MagicMock()
        mock_file.file.read = MagicMock(side_effect=[html_content, b""])
        blob_key = storage.store_raw_blob(mock_file)

        # Create document placeholder (visible to worker)
        doc_id = uuid_lib.uuid4()
        content_hash = hashlib.sha256(html_content).hexdigest()

        doc = Document(
            id=doc_id,
            user_id=integration_test_user.id,
            title="Integration Test",
            original_blob_key=blob_key,
            original_mime_type="text/html",
            original_size_bytes=len(html_content),
            content_hash=content_hash,
            canonical_text="",  # Will be filled by ingestion
            canonical_hash="",  # Will be filled by ingestion
            text_byte_length=0,
            extractor_version="pending",
            status="pending",
            embedding_status="pending",
        )
        committed_db_session.add(doc)
        committed_db_session.commit()

        # Enqueue ingest task
        result = ingest_document.delay(str(doc_id))

        # Wait for task completion
        try:
            wait_for_task_fixture(result.id, timeout=30)
        except Exception as e:
            # Get document state for debugging
            committed_db_session.expire_all()
            doc = committed_db_session.query(Document).filter(Document.id == doc_id).first()
            pytest.fail(
                f"Task failed: {e}\n"
                f"Document status: {doc.status if doc else 'not found'}\n"
                f"Error: {doc.error_message if doc else 'N/A'}"
            )

        # Give worker time to process downstream tasks (chunk → embed)
        time.sleep(3)

        # Verify document state
        committed_db_session.expire_all()
        doc = committed_db_session.query(Document).filter(Document.id == doc_id).one()

        assert doc.status == "ready", f"Expected status 'ready', got '{doc.status}'"
        assert doc.canonical_text, "canonical_text should be populated"
        assert doc.canonical_hash, "canonical_hash should be populated"

        # Verify chunks created (chunking task ran)
        chunks = (
            committed_db_session.query(ContentChunk)
            .filter(ContentChunk.media_id == doc_id)
            .all()
        )
        assert len(chunks) > 0, "Chunks should be created by chunking task"

        # Clean up: delete test data
        for chunk in chunks:
            committed_db_session.delete(chunk)
        committed_db_session.delete(doc)
        committed_db_session.commit()

    def test_chunks_visible_before_embedding(
        self,
        committed_db_session: Session,
        integration_test_user: User,
        celery_integration_app,
        wait_for_task_fixture,
        clear_queues,
    ):
        """
        Critical test: Chunks must be committed before embed task processes them.

        This catches the race condition where:
        - chunk_document flushes chunks but transaction not committed
        - embed_document dequeues immediately, doesn't see chunks
        - Result: ValidationError "No chunks found"

        If this test fails, it indicates a commit timing issue in the pipeline.
        """
        # Create a simple HTML document
        html_content = b"""
        <!DOCTYPE html>
        <html>
        <head><title>Durability Test</title></head>
        <body>
            <h1>Test</h1>
            <p>Content for durability testing paragraph one.</p>
            <p>Content for durability testing paragraph two.</p>
        </body>
        </html>
        """

        # Store the HTML file
        storage = StorageService()
        from unittest.mock import MagicMock

        mock_file = MagicMock()
        mock_file.file.read = MagicMock(side_effect=[html_content, b""])
        blob_key = storage.store_raw_blob(mock_file)

        # Create document
        doc_id = uuid_lib.uuid4()
        content_hash = hashlib.sha256(html_content).hexdigest()

        doc = Document(
            id=doc_id,
            user_id=integration_test_user.id,
            title="Durability Test",
            original_blob_key=blob_key,
            original_mime_type="text/html",
            original_size_bytes=len(html_content),
            content_hash=content_hash,
            canonical_text="",
            canonical_hash="",
            text_byte_length=0,
            extractor_version="pending",
            status="pending",
            embedding_status="pending",
        )
        committed_db_session.add(doc)
        committed_db_session.commit()

        # Run full pipeline
        result = ingest_document.delay(str(doc_id))
        wait_for_task_fixture(result.id, timeout=30)

        # Wait for downstream tasks
        time.sleep(5)

        # Check for chunks
        committed_db_session.expire_all()
        chunks = (
            committed_db_session.query(ContentChunk)
            .filter(ContentChunk.media_id == doc_id)
            .all()
        )

        # If race condition exists, chunks will either:
        # 1. Not exist (embed task failed before chunks were visible)
        # 2. Exist but embedding_status is 'failed' (embed task saw no chunks)
        assert len(chunks) > 0, (
            "RACE CONDITION DETECTED: Chunks not created or not visible. "
            "This indicates a flush/commit timing issue in chunk_document task."
        )

        # Check document embedding status
        doc = committed_db_session.query(Document).filter(Document.id == doc_id).one()

        # embedding_status should not be 'failed' due to missing chunks
        if doc.embedding_status == "failed" and doc.error_message:
            if "no chunks" in doc.error_message.lower():
                pytest.fail(
                    "RACE CONDITION DETECTED: embed_document ran before chunks "
                    "were committed. Error: " + doc.error_message
                )

        # Clean up
        for chunk in chunks:
            committed_db_session.delete(chunk)
        committed_db_session.delete(doc)
        committed_db_session.commit()


@pytest.mark.integration
class TestTaskEnqueuing:
    """Test that tasks are properly enqueued across the pipeline."""

    def test_ingestion_enqueues_chunking(
        self,
        committed_db_session: Session,
        integration_test_user: User,
        celery_integration_app,
        wait_for_task_fixture,
        clear_queues,
    ):
        """Verify ingestion task enqueues chunking task on success."""
        html_content = b"""
        <!DOCTYPE html>
        <html>
        <head><title>Enqueue Test</title></head>
        <body><p>Test content</p></body>
        </html>
        """

        storage = StorageService()
        from unittest.mock import MagicMock

        mock_file = MagicMock()
        mock_file.file.read = MagicMock(side_effect=[html_content, b""])
        blob_key = storage.store_raw_blob(mock_file)

        doc_id = uuid_lib.uuid4()
        doc = Document(
            id=doc_id,
            user_id=integration_test_user.id,
            title="Enqueue Test",
            original_blob_key=blob_key,
            original_mime_type="text/html",
            original_size_bytes=len(html_content),
            content_hash=hashlib.sha256(html_content).hexdigest(),
            canonical_text="",
            canonical_hash="",
            text_byte_length=0,
            extractor_version="pending",
            status="pending",
            embedding_status="pending",
        )
        committed_db_session.add(doc)
        committed_db_session.commit()

        # Run ingestion
        result = ingest_document.delay(str(doc_id))
        wait_for_task_fixture(result.id, timeout=30)

        # Wait for chunking to complete
        time.sleep(3)

        # Verify chunks exist (proves chunking task was enqueued and ran)
        committed_db_session.expire_all()
        chunks = (
            committed_db_session.query(ContentChunk)
            .filter(ContentChunk.media_id == doc_id)
            .all()
        )

        assert len(chunks) > 0, "Chunking task should have created chunks"

        # Clean up
        doc = committed_db_session.query(Document).filter(Document.id == doc_id).one()
        for chunk in chunks:
            committed_db_session.delete(chunk)
        committed_db_session.delete(doc)
        committed_db_session.commit()

