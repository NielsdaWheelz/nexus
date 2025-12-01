"""Integration tests for document ingestion pipeline.

Tests verify:
- Full ingestion flow: upload → ingest_document task → canonicalization
- Status transitions (pending → processing → ready)
- Hash computation and storage
- anchored_content_hash set on first ingestion
- Remap trigger logic
- Error handling and retry
- All fields populated correctly
"""

import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.documents import create_document_placeholder
from app.services.ingestion import run_ingest_document
from app.services.storage import StorageService


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        id=None,  # Will be auto-generated
        external_user_id="test_user_123",
        email="test@example.com",
    )
    db_session.add(user)
    db_session.flush()  # Flush to DB within transaction, but don't commit
    db_session.refresh(user)
    return user


@pytest.fixture
def test_html_blob() -> bytes:
    """Create a simple test HTML document."""
    return b"""<!DOCTYPE html>
<html>
<body>
<h1>Test Document</h1>
<p>This is a test document for ingestion.</p>
</body>
</html>
"""


def test_ingestion_full_workflow_html(db_session: Session, test_user: User, test_html_blob: bytes):
    """Test complete HTML ingestion workflow."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document placeholder
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    doc_id = doc.id
    assert doc.status == "pending"

    # Ingest document
    result = run_ingest_document(db_session, str(doc_id))

    # Verify result
    assert result["status"] == "success"
    assert result["document_id"] == str(doc_id)

    # Verify document was updated
    db_session.refresh(doc)

    assert doc.status == "ready"
    assert doc.canonical_text
    assert "Test Document" in doc.canonical_text
    assert doc.canonical_hash
    assert doc.content_hash
    assert doc.text_byte_length > 0
    assert doc.extractor_version == "html-v1"
    assert doc.language == "en"
    assert doc.structure["type"] == "html"
    assert doc.anchored_content_hash == doc.canonical_hash  # Set on first ingestion
    assert doc.retries_count == 1


def test_ingestion_idempotent_same_content(
    db_session: Session, test_user: User, test_html_blob: bytes
):
    """Test that ingesting same content twice is idempotent (no-op on second run)."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document placeholder
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    # First ingestion
    run_ingest_document(db_session, str(doc.id))
    db_session.refresh(doc)
    first_text = doc.canonical_text
    first_hash = doc.canonical_hash

    # Set status to ready to test re-ingestion logic
    doc.status = "ready"
    db_session.commit()

    # Second ingestion with same content
    result = run_ingest_document(db_session, str(doc.id))

    # Should skip (already ready with same hash)
    assert result["status"] == "skipped"
    assert result["reason"] == "already_ready_same_hash"

    # Text should be unchanged
    db_session.refresh(doc)
    assert doc.canonical_text == first_text
    assert doc.canonical_hash == first_hash


def test_ingestion_status_transitions(db_session: Session, test_user: User, test_html_blob: bytes):
    """Test document status transitions during ingestion."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document in pending state
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    assert doc.status == "pending"

    # Ingest
    run_ingest_document(db_session, str(doc.id))

    # Verify status transitioned to ready
    db_session.refresh(doc)
    assert doc.status == "ready"


def test_ingestion_hashes_correct(db_session: Session, test_user: User, test_html_blob: bytes):
    """Test that content_hash and canonical_hash are computed correctly."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    # Ingest
    run_ingest_document(db_session, str(doc.id))
    db_session.refresh(doc)

    # Verify hashes
    expected_content_hash = hashlib.sha256(test_html_blob).hexdigest()
    expected_canonical_hash = hashlib.sha256(doc.canonical_text.encode("utf-8")).hexdigest()

    assert doc.content_hash == expected_content_hash
    assert doc.canonical_hash == expected_canonical_hash
    assert len(doc.content_hash) == 64  # SHA256 hex
    assert len(doc.canonical_hash) == 64


def test_ingestion_text_byte_length(db_session: Session, test_user: User, test_html_blob: bytes):
    """Test that text_byte_length is correct."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    # Ingest
    run_ingest_document(db_session, str(doc.id))
    db_session.refresh(doc)

    # Verify text_byte_length
    expected_byte_length = len(doc.canonical_text.encode("utf-8"))
    assert doc.text_byte_length == expected_byte_length


def test_ingestion_remap_trigger_first_ingestion(
    db_session: Session, test_user: User, test_html_blob: bytes
):
    """Test that first ingestion doesn't trigger remap."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    # Verify anchored_content_hash is None before ingestion
    assert doc.anchored_content_hash is None

    # Ingest with mocked remap task
    with patch("app.services.ingestion.remap_highlights_for_document") as mock_remap:
        run_ingest_document(db_session, str(doc.id))

        # Remap should NOT be triggered on first ingestion
        mock_remap.delay.assert_not_called()

    db_session.refresh(doc)

    # anchored_content_hash should now be set to canonical_hash
    assert doc.anchored_content_hash == doc.canonical_hash


@patch("app.services.ingestion.remap_highlights_for_document")
def test_ingestion_remap_trigger_changed_hash(
    mock_remap,
    db_session: Session,
    test_user: User,
    test_html_blob: bytes,
):
    """Test that remap is triggered when canonical_hash changes."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    # First ingestion
    run_ingest_document(db_session, str(doc.id))
    db_session.refresh(doc)

    # Simulate hash change by setting anchored_content_hash to different value
    doc.anchored_content_hash = "different_old_hash"
    db_session.commit()

    # Re-ingest with mocked remap (simulate changed content)
    # First, set status back to pending to allow re-ingestion
    doc.status = "pending"
    db_session.commit()

    with patch("app.services.ingestion.canonicalize_document") as mock_canonicalize:
        # Return different canonical_hash to simulate extraction algorithm change
        mock_canonicalize.return_value = MagicMock(
            canonical_text="Modified content",
            canonical_hash="new_hash_different",
            content_hash="new_content_hash_different",  # Different blob content to trigger re-extraction
            structure={"type": "html"},
            language="en",
            extractor_version="html-v1",
            text_byte_length=16,
        )

        run_ingest_document(db_session, str(doc.id))

        # Remap SHOULD be triggered
        mock_remap.delay.assert_called_once()
        call_args = mock_remap.delay.call_args[0]
        assert call_args[0] == str(doc.id)
        assert call_args[1] == "different_old_hash"
        assert call_args[2] == "new_hash_different"


def test_ingestion_updates_retries_count(
    db_session: Session, test_user: User, test_html_blob: bytes
):
    """Test that retries_count is incremented during ingestion."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    assert doc.retries_count == 0

    # Ingest
    run_ingest_document(db_session, str(doc.id))
    db_session.refresh(doc)

    assert doc.retries_count == 1


def test_ingestion_sets_last_attempted_at(
    db_session: Session, test_user: User, test_html_blob: bytes
):
    """Test that last_attempted_at is set during ingestion."""
    # Create storage and store blob
    storage = StorageService()
    mock_file = MagicMock()
    mock_file.file.read = MagicMock(side_effect=[test_html_blob, b""])
    blob_key = storage.store_raw_blob(mock_file)

    # Create document
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri=blob_key,
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=len(test_html_blob),
        source_url=None,
        title="Test Document",
    )

    assert doc.last_attempted_at is None

    # Ingest
    before = datetime.now(timezone.utc)
    run_ingest_document(db_session, str(doc.id))
    after = datetime.now(timezone.utc)

    db_session.refresh(doc)

    assert doc.last_attempted_at is not None
    assert before <= doc.last_attempted_at <= after


def test_ingestion_error_handling(db_session: Session, test_user: User):
    """Test that ingestion errors set status to failed."""
    # Create document with invalid blob_key
    doc = create_document_placeholder(
        session=db_session,
        user=test_user,
        source_kind="html",
        original_blob_uri="nonexistent_blob_key",
        original_filename="test.html",
        original_mime_type="text/html",
        original_size_bytes=100,
        source_url=None,
        title="Test Document",
    )

    # Ingest should fail and set status to failed
    with pytest.raises(FileNotFoundError):
        run_ingest_document(db_session, str(doc.id))

    db_session.refresh(doc)

    assert doc.status == "failed"
    assert doc.error_code == "INTERNAL_ERROR"
    assert doc.error_message  # Should contain error details
