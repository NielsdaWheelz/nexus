"""Comprehensive tests for document service layer (PR 3.1).

Tests cover:
- Document placeholder creation (happy path + validation errors)
- Document retrieval with ownership and soft-delete checks
- Document listing with cursor pagination (determinism, ordering, has_more)
- Typed ID format validation
- ACL enforcement (other user cannot see documents)

All tests use real database transactions (no mocks) with auto-rollback.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import PaginationParams
from app.models.document import Document
from app.models.user import User
from app.services.documents import (
    create_document_placeholder,
    get_document_for_user,
    list_documents_for_user,
)


@pytest.fixture
def user1(db_session: Session) -> User:
    """Create first test user."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_user_1",
        email="user1@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def user2(db_session: Session) -> User:
    """Create second test user (for ACL testing)."""
    user = User(
        id=uuid4(),
        external_user_id="clerk_user_2",
        email="user2@example.com",
    )
    db_session.add(user)
    db_session.flush()
    return user


# ============================================================================
# CREATE_DOCUMENT_PLACEHOLDER TESTS
# ============================================================================


class TestCreateDocumentPlaceholder:
    """Test create_document_placeholder function."""

    def test_creation_happy_path(self, db_session: Session, user1: User):
        """Test successful document placeholder creation."""
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="My PDF.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=12345,
            content_hash="abc123def456789abc123def456789abc123",
            source_url="https://example.com/pdf",
        )

        # Verify document created with correct fields
        assert doc.id is not None
        assert doc.user_id == user1.id
        assert doc.title == "My PDF.pdf"
        assert doc.original_blob_key == "s3://bucket/file.pdf"
        assert doc.original_mime_type == "application/pdf"
        assert doc.original_size_bytes == 12345
        assert doc.content_hash == "abc123def456789abc123def456789abc123"
        assert doc.source_url == "https://example.com/pdf"

        # Verify initial state
        assert doc.canonical_text == ""
        assert doc.canonical_hash == ""
        assert doc.status == "pending"
        assert doc.embedding_status == "pending"
        assert doc.deleted_at is None

        # Verify timestamps set
        assert doc.created_at is not None
        assert doc.updated_at is not None
        assert isinstance(doc.created_at, datetime)
        assert doc.created_at.tzinfo is not None  # Must have timezone

    def test_creation_with_minimal_args(self, db_session: Session, user1: User):
        """Test creation with minimal required arguments."""
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="epub",
            original_blob_uri="file:///path/to/file.epub",
            original_filename=None,  # Optional
            original_mime_type=None,  # Optional
            original_size_bytes=None,  # Optional
            content_hash="hash123",
            source_url=None,  # Optional
        )

        assert doc.id is not None
        assert doc.user_id == user1.id
        assert doc.title == "Untitled"  # Default when filename is None
        assert doc.original_mime_type == "application/octet-stream"  # Default
        assert doc.original_size_bytes == 0  # Default

    def test_validation_empty_content_hash(self, db_session: Session, user1: User):
        """Test that empty content_hash raises ValidationAppError."""
        with pytest.raises(ValidationAppError) as exc_info:
            create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="pdf",
                original_blob_uri="s3://bucket/file.pdf",
                original_filename="test.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=100,
                content_hash="",  # Empty!
                source_url=None,
            )

        err = exc_info.value
        assert err.code.value == "VALIDATION_ERROR"
        assert err.http_status == 422
        assert "content_hash" in err.message.lower() or "required" in err.message.lower()

    def test_validation_invalid_source_kind(self, db_session: Session, user1: User):
        """Test that invalid source_kind raises ValidationAppError."""
        with pytest.raises(ValidationAppError) as exc_info:
            create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="docx",  # Invalid!
                original_blob_uri="s3://bucket/file.docx",
                original_filename="test.docx",
                original_mime_type="application/vnd.ms-word",
                original_size_bytes=100,
                content_hash="hash123",
                source_url=None,
            )

        err = exc_info.value
        assert err.code.value == "VALIDATION_ERROR"
        assert err.http_status == 422
        assert "source_kind" in err.message.lower()

    def test_validation_negative_size(self, db_session: Session, user1: User):
        """Test that negative size_bytes raises ValidationAppError."""
        with pytest.raises(ValidationAppError) as exc_info:
            create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="pdf",
                original_blob_uri="s3://bucket/file.pdf",
                original_filename="test.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=-1,  # Negative!
                content_hash="hash123",
                source_url=None,
            )

        err = exc_info.value
        assert err.code.value == "VALIDATION_ERROR"
        assert err.http_status == 422
        assert "size" in err.message.lower() or "negative" in err.message.lower()

    def test_creation_persists_to_db(self, db_session: Session, user1: User):
        """Test that created document is persisted to database."""
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="html",
            original_blob_uri="http://example.com/page.html",
            original_filename="page.html",
            original_mime_type="text/html",
            original_size_bytes=5000,
            content_hash="htmlhash",
            source_url="http://example.com/page.html",
        )

        doc_id = doc.id

        # Query database to verify persistence
        fetched = db_session.query(Document).filter(Document.id == doc_id).first()
        assert fetched is not None
        assert fetched.user_id == user1.id
        assert fetched.original_filename == "page.html"


# ============================================================================
# GET_DOCUMENT_FOR_USER TESTS
# ============================================================================


class TestGetDocumentForUser:
    """Test get_document_for_user function."""

    def test_get_owned_document(self, db_session: Session, user1: User):
        """Test user can retrieve their own document."""
        # Create document
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=100,
            content_hash="hash1",
            source_url=None,
        )

        # Retrieve it
        retrieved = get_document_for_user(
            session=db_session,
            user=user1,
            document_id=doc.id,
        )

        assert retrieved.id == doc.id
        assert retrieved.user_id == user1.id

    def test_get_nonexistent_document_raises_not_found(self, db_session: Session, user1: User):
        """Test that getting nonexistent document raises NotFoundError."""
        nonexistent_id = uuid4()

        with pytest.raises(NotFoundError) as exc_info:
            get_document_for_user(
                session=db_session,
                user=user1,
                document_id=nonexistent_id,
            )

        err = exc_info.value
        assert err.code.value == "NOT_FOUND"
        assert err.http_status == 404
        assert "not found" in err.message.lower()
        # Verify typed ID in details
        assert err.details.get("resource_type") == "document"
        assert err.details.get("resource_id").startswith("doc_")

    def test_get_other_user_document_raises_not_found(
        self, db_session: Session, user1: User, user2: User
    ):
        """Test that user cannot access another user's document (ACL)."""
        # User1 creates document
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="user1_doc.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=100,
            content_hash="hash1",
            source_url=None,
        )

        # User2 tries to access it -> should get NOT_FOUND (not FORBIDDEN)
        with pytest.raises(NotFoundError) as exc_info:
            get_document_for_user(
                session=db_session,
                user=user2,
                document_id=doc.id,
            )

        err = exc_info.value
        assert err.code.value == "NOT_FOUND"
        assert err.http_status == 404

    def test_get_soft_deleted_document_raises_not_found(self, db_session: Session, user1: User):
        """Test that soft-deleted documents are not retrievable."""
        # Create document
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=100,
            content_hash="hash1",
            source_url=None,
        )

        # Soft-delete it
        doc.deleted_at = datetime.now(timezone.utc)
        db_session.flush()

        # Try to retrieve -> should get NOT_FOUND
        with pytest.raises(NotFoundError) as exc_info:
            get_document_for_user(
                session=db_session,
                user=user1,
                document_id=doc.id,
            )

        err = exc_info.value
        assert err.http_status == 404


# ============================================================================
# LIST_DOCUMENTS_FOR_USER TESTS
# ============================================================================


class TestListDocumentsForUser:
    """Test list_documents_for_user function."""

    def test_list_empty_no_documents(self, db_session: Session, user1: User):
        """Test listing when user has no documents."""
        result = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=20, cursor=None),
        )

        assert result.items == []
        assert result.has_more is False
        assert result.next_cursor is None

    def test_list_single_document(self, db_session: Session, user1: User):
        """Test listing with single document."""
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=100,
            content_hash="hash1",
            source_url=None,
        )

        result = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=20, cursor=None),
        )

        assert len(result.items) == 1
        assert result.items[0].id == doc.id
        assert result.has_more is False
        assert result.next_cursor is None

    def test_list_preserves_document_summary_format(self, db_session: Session, user1: User):
        """Test that list response has correct schema (DocumentSummary)."""
        create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="epub",
            original_blob_uri="file.epub",
            original_filename="book.epub",
            original_mime_type="application/epub+zip",
            original_size_bytes=50000,
            content_hash="epubhash",
            source_url="http://example.com/book.epub",
        )

        result = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=20, cursor=None),
        )

        assert len(result.items) == 1
        summary = result.items[0]

        # Verify DocumentSummary fields
        assert summary.id.startswith("doc_")
        assert summary.title == "book.epub"
        assert summary.source_kind == "epub"
        assert summary.processing_status == "pending"
        assert isinstance(summary.created_at, datetime)
        assert isinstance(summary.updated_at, datetime)

    def test_list_ordering_newest_first(self, db_session: Session, user1: User):
        """Test that documents are ordered by created_at DESC (newest first)."""
        # Create 3 documents with slight delays to ensure different timestamps
        import time

        docs = []
        for i in range(3):
            doc = create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="pdf",
                original_blob_uri=f"s3://bucket/file{i}.pdf",
                original_filename=f"doc{i}.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=100 + i,
                content_hash=f"hash{i}",
                source_url=None,
            )
            docs.append(doc)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        result = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=20, cursor=None),
        )

        assert len(result.items) == 3

        # Verify newest first (reverse order of creation)
        created_times = [doc.created_at for doc in docs]
        result_times = [item.created_at for item in result.items]
        assert result_times == sorted(created_times, reverse=True)

    def test_list_pagination_with_limit(self, db_session: Session, user1: User):
        """Test pagination respects limit parameter."""
        # Create 5 documents
        for i in range(5):
            create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="pdf",
                original_blob_uri=f"s3://bucket/file{i}.pdf",
                original_filename=f"doc{i}.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=100,
                content_hash=f"hash{i}",
                source_url=None,
            )

        # Request with limit=2
        result = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=2, cursor=None),
        )

        assert len(result.items) == 2
        assert result.has_more is True
        assert result.next_cursor is not None

    def test_list_pagination_cursor_navigation(self, db_session: Session, user1: User):
        """Test cursor pagination navigates correctly through pages."""
        # Create 5 documents
        for i in range(5):
            create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="pdf",
                original_blob_uri=f"s3://bucket/file{i}.pdf",
                original_filename=f"doc{i}.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=100,
                content_hash=f"hash{i}",
                source_url=None,
            )

        # Page 1: limit=2
        result1 = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=2, cursor=None),
        )
        assert len(result1.items) == 2
        assert result1.has_more is True
        page1_ids = [item.id for item in result1.items]

        # Page 2: use cursor from page 1
        result2 = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=2, cursor=result1.next_cursor),
        )
        assert len(result2.items) == 2
        assert result2.has_more is True
        page2_ids = [item.id for item in result2.items]

        # Verify no overlap
        assert set(page1_ids).isdisjoint(set(page2_ids))

        # Page 3: use cursor from page 2
        result3 = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=2, cursor=result2.next_cursor),
        )
        assert len(result3.items) == 1
        assert result3.has_more is False
        assert result3.next_cursor is None
        page3_ids = [item.id for item in result3.items]

        # Verify total coverage
        assert len(set(page1_ids) | set(page2_ids) | set(page3_ids)) == 5

    def test_list_deterministic_pagination(self, db_session: Session, user1: User):
        """Test that pagination is deterministic (same cursor -> same results)."""
        # Create documents
        for i in range(3):
            create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="pdf",
                original_blob_uri=f"s3://bucket/file{i}.pdf",
                original_filename=f"doc{i}.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=100,
                content_hash=f"hash{i}",
                source_url=None,
            )

        # Get first page
        result1a = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=2, cursor=None),
        )

        # Get same page again
        result1b = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=2, cursor=None),
        )

        # Results should be identical
        assert [item.id for item in result1a.items] == [item.id for item in result1b.items]
        assert result1a.next_cursor == result1b.next_cursor
        assert result1a.has_more == result1b.has_more

    def test_list_excludes_soft_deleted_documents(self, db_session: Session, user1: User):
        """Test that soft-deleted documents are excluded from list."""
        # Create 3 documents
        docs = []
        for i in range(3):
            doc = create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="pdf",
                original_blob_uri=f"s3://bucket/file{i}.pdf",
                original_filename=f"doc{i}.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=100,
                content_hash=f"hash{i}",
                source_url=None,
            )
            docs.append(doc)

        # Soft-delete one
        docs[1].deleted_at = datetime.now(timezone.utc)
        db_session.flush()

        # List should return only 2
        result = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=20, cursor=None),
        )

        assert len(result.items) == 2
        returned_ids = [item.id for item in result.items]
        assert docs[1].id not in returned_ids

    def test_list_other_user_documents_excluded(
        self, db_session: Session, user1: User, user2: User
    ):
        """Test that other users' documents are not visible in list."""
        # User1 creates 2 documents
        for i in range(2):
            create_document_placeholder(
                session=db_session,
                user=user1,
                source_kind="pdf",
                original_blob_uri=f"s3://bucket/user1/{i}.pdf",
                original_filename=f"u1_doc{i}.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=100,
                content_hash=f"u1hash{i}",
                source_url=None,
            )

        # User2 creates 3 documents
        for i in range(3):
            create_document_placeholder(
                session=db_session,
                user=user2,
                source_kind="pdf",
                original_blob_uri=f"s3://bucket/user2/{i}.pdf",
                original_filename=f"u2_doc{i}.pdf",
                original_mime_type="application/pdf",
                original_size_bytes=100,
                content_hash=f"u2hash{i}",
                source_url=None,
            )

        # User1 lists -> should see only their 2
        result1 = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=20, cursor=None),
        )
        assert len(result1.items) == 2

        # User2 lists -> should see only their 3
        result2 = list_documents_for_user(
            session=db_session,
            user=user2,
            pagination=PaginationParams(limit=20, cursor=None),
        )
        assert len(result2.items) == 3


# ============================================================================
# UUID FORMAT TESTS
# ============================================================================


class TestUUIDFormat:
    """Test that service layer returns raw UUIDs (typed ID conversion at API layer)."""

    def test_get_document_returns_raw_uuid(self, db_session: Session, user1: User):
        """Test that service returns raw UUID (not typed ID)."""
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=100,
            content_hash="hash1",
            source_url=None,
        )

        retrieved = get_document_for_user(
            session=db_session,
            user=user1,
            document_id=doc.id,
        )

        # Service returns raw UUID (not typed ID string)
        assert retrieved.id == doc.id
        assert isinstance(retrieved.id, UUID)

    def test_list_documents_returns_raw_uuids(self, db_session: Session, user1: User):
        """Test that list service returns raw UUIDs (API layer handles typed ID conversion)."""
        doc = create_document_placeholder(
            session=db_session,
            user=user1,
            source_kind="pdf",
            original_blob_uri="s3://bucket/file.pdf",
            original_filename="test.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=100,
            content_hash="hash1",
            source_url=None,
        )

        result = list_documents_for_user(
            session=db_session,
            user=user1,
            pagination=PaginationParams(limit=20, cursor=None),
        )

        assert len(result.items) == 1
        item_id = result.items[0].id

        # Service returns raw UUID, not typed ID string
        assert isinstance(item_id, UUID)
        assert item_id == doc.id
