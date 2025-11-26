"""Tests for reader service layer.

Tests cover:
- Creating readers (get-or-create semantics)
- Retrieving readers with ACL enforcement
- Updating reader position
- Listing readers for documents with pagination
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.pagination import PaginationParams
from app.models.document import Document
from app.models.reader import Reader
from app.models.user import User
from app.services.readers import (
    get_or_create_reader_for_user,
    get_reader_for_user,
    list_readers_for_document,
    update_reader_position,
)


class TestGetOrCreateReaderForUser:
    """Test get_or_create_reader_for_user function."""

    def test_creates_reader_first_time(self, db_session: Session):
        """Test that calling get_or_create_reader creates a new reader on first call."""
        user = User(id=uuid4(), external_user_id="clerk_user_1", email="user@example.com")
        db_session.add(user)
        db_session.flush()

        doc = Document(
            user_id=user.id,
            title="Test Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test text",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=9,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        reader = get_or_create_reader_for_user(
            session=db_session,
            user=user,
            document=doc,
        )

        assert reader.id is not None
        assert reader.user_id == user.id
        assert reader.document_id == doc.id
        assert reader.current_position is None
        assert reader.last_read_at is not None

        # Verify it was stored in DB
        stored = db_session.query(Reader).filter(Reader.id == reader.id).first()
        assert stored is not None
        assert stored.user_id == user.id

    def test_returns_existing_reader_second_time(self, db_session: Session):
        """Test that calling get_or_create_reader twice returns the same reader."""
        user = User(id=uuid4(), external_user_id="clerk_user_1", email="user@example.com")
        db_session.add(user)
        db_session.flush()

        doc = Document(
            user_id=user.id,
            title="Test Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test text",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=9,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        reader1 = get_or_create_reader_for_user(
            session=db_session,
            user=user,
            document=doc,
        )

        reader2 = get_or_create_reader_for_user(
            session=db_session,
            user=user,
            document=doc,
        )

        assert reader1.id == reader2.id

    def test_raises_not_found_for_non_owned_document(self, db_session: Session):
        """Test that get_or_create_reader raises NotFoundError if user doesn't own doc."""
        user1 = User(id=uuid4(), external_user_id="clerk_user_1", email="user1@example.com")
        user2 = User(id=uuid4(), external_user_id="clerk_user_2", email="user2@example.com")
        db_session.add_all([user1, user2])
        db_session.flush()

        doc = Document(
            user_id=user1.id,  # Owned by user1
            title="Test Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test text",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=9,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        with pytest.raises(NotFoundError) as exc_info:
            get_or_create_reader_for_user(
                session=db_session,
                user=user2,  # user2 trying to read user1's doc
                document=doc,
            )

        assert exc_info.value.message == "Document not found"


class TestGetReaderForUser:
    """Test get_reader_for_user function."""

    def test_retrieves_existing_reader(self, db_session: Session):
        """Test that get_reader_for_user retrieves an existing reader."""
        user = User(id=uuid4(), external_user_id="clerk_user_1", email="user@example.com")
        db_session.add(user)
        db_session.flush()

        doc = Document(
            user_id=user.id,
            title="Test Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test text",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=9,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        reader = Reader(
            user_id=user.id,
            document_id=doc.id,
            current_position=1000,
            last_read_at=datetime.now(timezone.utc),
        )
        db_session.add(reader)
        db_session.flush()

        retrieved = get_reader_for_user(
            session=db_session,
            user=user,
            reader_id=reader.id,
        )

        assert retrieved.id == reader.id
        assert retrieved.current_position == 1000

    def test_raises_not_found_for_missing_reader(self, db_session: Session):
        """Test that get_reader_for_user raises NotFoundError for missing reader."""
        user = User(id=uuid4(), external_user_id="clerk_user_1", email="user@example.com")
        db_session.add(user)
        db_session.flush()

        missing_id = uuid4()

        with pytest.raises(NotFoundError) as exc_info:
            get_reader_for_user(
                session=db_session,
                user=user,
                reader_id=missing_id,
            )

        assert exc_info.value.message == "Reader not found"

    def test_enforces_acl_different_user(self, db_session: Session):
        """Test that get_reader_for_user raises NotFoundError if user doesn't own reader."""
        user1 = User(id=uuid4(), external_user_id="clerk_user_1", email="user1@example.com")
        user2 = User(id=uuid4(), external_user_id="clerk_user_2", email="user2@example.com")
        db_session.add_all([user1, user2])
        db_session.flush()

        doc = Document(
            user_id=user1.id,
            title="Test Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test text",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=9,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        reader = Reader(
            user_id=user1.id,  # Owned by user1
            document_id=doc.id,
        )
        db_session.add(reader)
        db_session.flush()

        with pytest.raises(NotFoundError):
            get_reader_for_user(
                session=db_session,
                user=user2,  # user2 trying to read user1's reader
                reader_id=reader.id,
            )


class TestUpdateReaderPosition:
    """Test update_reader_position function."""

    def test_updates_position_and_last_read_at(self, db_session: Session):
        """Test that update_reader_position updates both fields."""
        user = User(id=uuid4(), external_user_id="clerk_user_1", email="user@example.com")
        db_session.add(user)
        db_session.flush()

        doc = Document(
            user_id=user.id,
            title="Test Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test text",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=9,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        old_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        reader = Reader(
            user_id=user.id,
            document_id=doc.id,
            current_position=500,
            last_read_at=old_time,
        )
        db_session.add(reader)
        db_session.flush()

        updated = update_reader_position(
            session=db_session,
            user=user,
            reader_id=reader.id,
            current_position=1000,
        )

        assert updated.current_position == 1000
        assert updated.last_read_at > old_time

    def test_enforces_acl(self, db_session: Session):
        """Test that update_reader_position enforces ACL."""
        user1 = User(id=uuid4(), external_user_id="clerk_user_1", email="user1@example.com")
        user2 = User(id=uuid4(), external_user_id="clerk_user_2", email="user2@example.com")
        db_session.add_all([user1, user2])
        db_session.flush()

        doc = Document(
            user_id=user1.id,
            title="Test Document",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test text",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=9,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        reader = Reader(
            user_id=user1.id,
            document_id=doc.id,
        )
        db_session.add(reader)
        db_session.flush()

        with pytest.raises(NotFoundError):
            update_reader_position(
                session=db_session,
                user=user2,
                reader_id=reader.id,
                current_position=1000,
            )


class TestListReadersForDocument:
    """Test list_readers_for_document function."""

    def test_returns_only_readers_for_document(self, db_session: Session):
        """Test that list_readers_for_document returns only readers for that doc."""
        owner = User(id=uuid4(), external_user_id="clerk_owner", email="owner@example.com")
        user1 = User(id=uuid4(), external_user_id="clerk_user1", email="user1@example.com")
        user2 = User(id=uuid4(), external_user_id="clerk_user2", email="user2@example.com")
        db_session.add_all([owner, user1, user2])
        db_session.flush()

        doc1 = Document(
            user_id=owner.id,
            title="Doc 1",
            original_blob_key="s3://bucket/file1.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=4,
            extractor_version="1.0",
            status="ready",
        )
        doc2 = Document(
            user_id=owner.id,
            title="Doc 2",
            original_blob_key="s3://bucket/file2.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="ghi789",
            canonical_text="test",
            canonical_hash="jkl012",
            canonical_version=1,
            text_byte_length=4,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add_all([doc1, doc2])
        db_session.flush()

        # Create readers: user1 and user2 reading doc1, and user1 reading doc2
        reader1 = Reader(user_id=user1.id, document_id=doc1.id)
        reader2 = Reader(user_id=user2.id, document_id=doc1.id)
        reader3 = Reader(user_id=user1.id, document_id=doc2.id)  # Different doc
        db_session.add_all([reader1, reader2, reader3])
        db_session.flush()

        result = list_readers_for_document(
            session=db_session,
            owner=owner,
            document_id=doc1.id,
            pagination=PaginationParams(limit=20, cursor=None),
        )

        assert len(result.items) == 2
        assert all(item.document_id == doc1.id for item in result.items)
        assert result.has_more is False

    def test_respects_pagination_limit(self, db_session: Session):
        """Test that list_readers_for_document respects pagination limit."""
        owner = User(id=uuid4(), external_user_id="clerk_owner", email="owner@example.com")
        db_session.add(owner)
        db_session.flush()

        doc = Document(
            user_id=owner.id,
            title="Test Doc",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=4,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        # Create 5 different users, each with one reader for the document
        users = [
            User(id=uuid4(), external_user_id=f"clerk_user_{i}", email=f"user{i}@example.com")
            for i in range(5)
        ]
        db_session.add_all(users)
        db_session.flush()

        readers = [Reader(user_id=user.id, document_id=doc.id) for user in users]
        db_session.add_all(readers)
        db_session.flush()

        result = list_readers_for_document(
            session=db_session,
            owner=owner,
            document_id=doc.id,
            pagination=PaginationParams(limit=2, cursor=None),
        )

        assert len(result.items) == 2
        assert result.has_more is True
        assert result.next_cursor is not None

    def test_raises_not_found_for_missing_document(self, db_session: Session):
        """Test that list_readers_for_document raises NotFoundError for missing doc."""
        owner = User(id=uuid4(), external_user_id="clerk_owner", email="owner@example.com")
        db_session.add(owner)
        db_session.flush()

        missing_doc_id = uuid4()

        with pytest.raises(NotFoundError):
            list_readers_for_document(
                session=db_session,
                owner=owner,
                document_id=missing_doc_id,
                pagination=PaginationParams(limit=20, cursor=None),
            )

    def test_enforces_document_ownership(self, db_session: Session):
        """Test that list_readers_for_document enforces document ownership."""
        owner = User(id=uuid4(), external_user_id="clerk_owner", email="owner@example.com")
        other_user = User(id=uuid4(), external_user_id="clerk_other", email="other@example.com")
        db_session.add_all([owner, other_user])
        db_session.flush()

        doc = Document(
            user_id=owner.id,  # Owned by owner
            title="Test Doc",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1000,
            content_hash="abc123",
            canonical_text="test",
            canonical_hash="def456",
            canonical_version=1,
            text_byte_length=4,
            extractor_version="1.0",
            status="ready",
        )
        db_session.add(doc)
        db_session.flush()

        with pytest.raises(NotFoundError):
            list_readers_for_document(
                session=db_session,
                owner=other_user,  # other_user trying to list readers
                document_id=doc.id,
                pagination=PaginationParams(limit=20, cursor=None),
            )
