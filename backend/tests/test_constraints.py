"""Tests for database constraint violations and error handling.

Tests cover:
- Unique constraint violations (duplicate user email, etc.)
- Foreign key constraint violations
- NOT NULL violations
- Correct error mapping to HTTP responses

All tests use real database with actual constraint enforcement.
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.highlight import Highlight
from app.models.user import User


class TestUniqueConstraintViolations:
    """Test unique constraint violations are handled correctly."""

    def test_duplicate_user_email_raises_integrity_error(self, db_session: Session):
        """Test that creating users with duplicate emails raises IntegrityError."""
        # Create first user
        user1 = User(
            id=uuid4(),
            external_user_id="user_unique_1",
            email="duplicate@example.com",
        )
        db_session.add(user1)
        db_session.flush()

        # Attempt to create second user with same email
        user2 = User(
            id=uuid4(),
            external_user_id="user_unique_2",
            email="duplicate@example.com",  # DUPLICATE
        )
        db_session.add(user2)

        # Should raise IntegrityError on flush
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()

        # Verify error mentions unique constraint
        assert "unique" in str(exc_info.value).lower() or "duplicate" in str(exc_info.value).lower()

    def test_duplicate_user_external_id_raises_integrity_error(self, db_session: Session):
        """Test that creating users with duplicate external_user_id raises IntegrityError."""
        # Create first user
        user1 = User(
            id=uuid4(),
            external_user_id="clerk_duplicate",
            email="user1@example.com",
        )
        db_session.add(user1)
        db_session.flush()

        # Attempt to create second user with same external_user_id
        user2 = User(
            id=uuid4(),
            external_user_id="clerk_duplicate",  # DUPLICATE
            email="user2@example.com",
        )
        db_session.add(user2)

        # Should raise IntegrityError on flush
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()

        # Verify error mentions unique constraint
        assert "unique" in str(exc_info.value).lower() or "duplicate" in str(exc_info.value).lower()


class TestForeignKeyConstraintViolations:
    """Test foreign key constraint violations are handled correctly."""

    def test_document_with_invalid_user_id_raises_integrity_error(self, db_session: Session):
        """Test that creating a document with non-existent user_id raises IntegrityError."""
        # Create document with non-existent user_id
        fake_user_id = uuid4()
        doc = Document(
            id=uuid4(),
            user_id=fake_user_id,  # FK violation - user doesn't exist
            title="Test Doc",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1234,
            content_hash="abc123",
            canonical_text="Test text",
            canonical_hash="def456",
            text_byte_length=9,
            extractor_version="1.0",
            status="pending",
            embedding_status="pending",
        )
        db_session.add(doc)

        # Should raise IntegrityError on flush
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()

        # Verify error mentions foreign key
        assert "foreign key" in str(exc_info.value).lower() or "fk" in str(exc_info.value).lower()

    def test_highlight_with_invalid_user_id_raises_integrity_error(self, db_session: Session):
        """Test that creating a highlight with non-existent user_id raises IntegrityError."""
        # Create user and document first
        user = User(
            id=uuid4(),
            external_user_id="fk_test_user",
            email="fktest@example.com",
        )
        db_session.add(user)

        doc = Document(
            id=uuid4(),
            user_id=user.id,
            title="Test Doc",
            original_blob_key="s3://bucket/file.pdf",
            original_mime_type="application/pdf",
            original_size_bytes=1234,
            content_hash="abc123",
            canonical_text="Test content",
            canonical_hash="hash123",
            text_byte_length=12,
            extractor_version="1.0",
            status="ready",
            embedding_status="pending",
        )
        db_session.add(doc)
        db_session.flush()

        # Create highlight with non-existent user_id
        fake_user_id = uuid4()
        highlight = Highlight(
            id=uuid4(),
            user_id=fake_user_id,  # FK violation
            media_type="document",
            media_id=doc.id,
            anchor_type="text",
            text_start=0,
            text_end=10,
            quote="Test",
            prefix="",
            suffix="",
            canonical_version=1,
        )
        db_session.add(highlight)

        # Should raise IntegrityError on flush
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()

        # Verify error mentions foreign key
        assert "foreign key" in str(exc_info.value).lower() or "fk" in str(exc_info.value).lower()


class TestNotNullConstraintViolations:
    """Test NOT NULL constraint violations are handled correctly."""

    def test_user_without_email_raises_integrity_error(self, db_session: Session):
        """Test that creating a user without email raises IntegrityError."""
        # Attempt to create user without email
        user = User(
            id=uuid4(),
            external_user_id="no_email_user",
            email=None,  # NOT NULL violation
        )
        db_session.add(user)

        # Should raise IntegrityError on flush
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()

        # Verify error mentions not null or violation
        error_msg = str(exc_info.value).lower()
        assert "not null" in error_msg or "null value" in error_msg or "violates" in error_msg

    def test_user_without_external_user_id_raises_integrity_error(self, db_session: Session):
        """Test that creating a user without external_user_id raises IntegrityError."""
        # Attempt to create user without external_user_id
        user = User(
            id=uuid4(),
            external_user_id=None,  # NOT NULL violation
            email="noexternal@example.com",
        )
        db_session.add(user)

        # Should raise IntegrityError on flush
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()

        # Verify error mentions not null or violation
        error_msg = str(exc_info.value).lower()
        assert "not null" in error_msg or "null value" in error_msg or "violates" in error_msg


class TestConstraintErrorMapping:
    """Test that constraint errors are properly caught and mapped to appropriate responses.

    NOTE: These tests verify the DATABASE behavior (IntegrityError raised).
    The actual HTTP error mapping would happen in production code's exception handlers.
    If production code doesn't catch IntegrityError, that's a bug to document.
    """

    def test_constraint_errors_include_useful_information(self, db_session: Session):
        """Verify IntegrityError contains enough info for debugging."""
        # Create duplicate email scenario
        user1 = User(
            id=uuid4(),
            external_user_id="error_info_1",
            email="info@example.com",
        )
        db_session.add(user1)
        db_session.flush()

        user2 = User(
            id=uuid4(),
            external_user_id="error_info_2",
            email="info@example.com",  # Duplicate
        )
        db_session.add(user2)

        # Capture error
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()

        error_str = str(exc_info.value)

        # Should include:
        # - Table name
        # - Column or constraint name
        # - Helpful context
        assert "users" in error_str or "email" in error_str
        # PostgreSQL error should be informative
        assert len(error_str) > 50  # Not just a generic message
