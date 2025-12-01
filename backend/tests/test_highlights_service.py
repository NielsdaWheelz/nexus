"""Tests for highlights and annotations service layer.

This module tests the domain service layer for highlights and annotations:
- Highlight creation with anchor validation
- Highlight retrieval and ACL enforcement
- Highlight listing with pagination
- Annotation creation and listing
- Soft-delete semantics
- Error handling and validation

All tests use the real PostgreSQL test database and session fixtures.
No mocks for database operations.

Spec reference:
- PR 3.2 specification
- spec/anchors.md (anchor validation)
- spec/acl.md (visibility/ownership rules)
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import PaginationParams
from app.models.document import Document
from app.models.user import User
from app.schemas.highlights import AnnotationSummary, HighlightSummary
from app.services.highlights import (
    create_annotation,
    create_highlight,
    get_highlight_for_user,
    list_annotations_for_highlight,
    list_highlights_for_document,
    soft_delete_annotation,
    soft_delete_highlight,
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def make_highlight_anchor(canonical_text: str, phrase: str):
    """Generate valid highlight anchor parameters from canonical text.

    Returns a dict with text_start, text_end, quote, prefix, suffix for the first
    occurrence of phrase in canonical_text.
    """
    canonical_bytes = canonical_text.encode("utf-8")
    idx = canonical_bytes.find(phrase.encode("utf-8"))
    if idx < 0:
        raise ValueError(f"Phrase '{phrase}' not found in canonical text")

    phrase_bytes = phrase.encode("utf-8")
    end_idx = idx + len(phrase_bytes)

    # Prefix: up to 64 bytes before start
    prefix_start = max(0, idx - 64)
    prefix = canonical_bytes[prefix_start:idx].decode("utf-8", errors="replace")

    # Suffix: up to 64 bytes after end
    suffix_end = min(len(canonical_bytes), end_idx + 64)
    suffix = canonical_bytes[end_idx:suffix_end].decode("utf-8", errors="replace")

    return {
        "text_start": idx,
        "text_end": end_idx,
        "quote": phrase,
        "prefix": prefix,
        "suffix": suffix,
    }


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def user1(db_session: Session) -> User:
    """Create first test user."""
    user = User(
        id=uuid.uuid4(),
        external_user_id="user1_test",
        email="user1@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def user2(db_session: Session) -> User:
    """Create second test user (for ACL tests)."""
    user = User(
        id=uuid.uuid4(),
        external_user_id="user2_test",
        email="user2@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def doc1(db_session: Session, user1: User) -> Document:
    """Create a test document."""
    canonical = "This is a test document with some sample text for highlighting. It has multiple sentences and plenty of content to work with for testing anchor validation and quote extraction logic in highlights."
    doc = Document(
        id=uuid.uuid4(),
        user_id=user1.id,
        title="Test Document",
        source_url="https://example.com/doc",
        original_blob_key="s3://bucket/doc.pdf",
        original_mime_type="application/pdf",
        original_size_bytes=1024,
        content_hash="abc123",
        canonical_text=canonical,
        canonical_hash="def456",
        text_byte_length=len(canonical.encode("utf-8")),
        extractor_version="1.0",
        structure={},
        doc_metadata={},
        status="ready",
        embedding_status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(doc)
    db_session.flush()
    return doc


# ============================================================================
# HIGHLIGHT CREATION TESTS
# ============================================================================


class TestCreateHighlight:
    """Tests for create_highlight function."""

    def test_create_highlight_text_anchor_valid(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating a highlight with valid text anchor."""
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        result = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        assert isinstance(result, HighlightSummary)
        assert result.user_id == user1.id
        assert result.media_type == "document"
        assert result.media_id == doc1.id
        assert result.anchor_type == "text"
        assert result.text_start == anchor["text_start"]
        assert result.text_end == anchor["text_end"]
        assert result.quote == anchor["quote"]
        assert result.color == "yellow"
        assert result.is_hidden is False
        assert result.is_detached is False
        assert result.is_public is False

    def test_create_highlight_invalid_quote(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight with mismatched quote fails."""
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        anchor["quote"] = "WRONG"  # Override with invalid quote
        with pytest.raises(ValidationAppError) as exc_info:
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )
        assert exc_info.value.code.value == "VALIDATION_ERROR"
        assert "quote" in str(exc_info.value.message).lower()

    def test_create_highlight_invalid_prefix(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight with mismatched prefix fails."""
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        anchor["prefix"] = "WRONG"  # Override with invalid prefix
        with pytest.raises(ValidationAppError) as exc_info:
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )
        assert exc_info.value.code.value == "VALIDATION_ERROR"
        assert "prefix" in str(exc_info.value.message).lower()

    def test_create_highlight_invalid_suffix(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight with mismatched suffix fails."""
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        anchor["suffix"] = "WRONG"  # Override with invalid suffix
        with pytest.raises(ValidationAppError) as exc_info:
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )
        assert exc_info.value.code.value == "VALIDATION_ERROR"
        assert "suffix" in str(exc_info.value.message).lower()

    def test_create_highlight_negative_offset(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight with negative offset fails."""
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        anchor["text_start"] = -1  # Override with invalid offset
        with pytest.raises(ValidationAppError) as exc_info:
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )
        assert exc_info.value.code.value == "VALIDATION_ERROR"

    def test_create_highlight_end_before_start(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight with end < start fails."""
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        anchor["text_end"] = anchor["text_start"] - 1  # Override: end < start
        with pytest.raises(ValidationAppError) as exc_info:
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )
        assert exc_info.value.code.value == "VALIDATION_ERROR"

    def test_create_highlight_offset_out_of_bounds(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight with offset beyond text fails."""
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        text_len = len(doc1.canonical_text.encode("utf-8"))
        anchor["text_end"] = text_len + 100  # Override: out of bounds
        with pytest.raises(ValidationAppError) as exc_info:
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )
        assert exc_info.value.code.value == "VALIDATION_ERROR"

    def test_create_highlight_no_document_not_found(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight on non-existent document raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "test")
        with pytest.raises(NotFoundError):
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=uuid.uuid4(),  # Does not exist
                anchor_type="text",
                **anchor,
            )

    def test_create_highlight_document_not_owned(
        self, db_session: Session, user1: User, user2: User, doc1: Document
    ) -> None:
        """Test creating highlight on document not owned by user raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "test")
        with pytest.raises(NotFoundError):
            create_highlight(
                session=db_session,
                user=user2,  # Different user
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )

    def test_create_highlight_deleted_document(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight on soft-deleted document raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "test")
        doc1.deleted_at = datetime.now(timezone.utc)
        db_session.flush()

        with pytest.raises(NotFoundError):
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )

    def test_create_highlight_pdf_anchor_valid(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating highlight with valid PDF anchor."""
        result = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="pdf",
            text_start=0,
            text_end=5,
            quote="page",
            prefix="",
            suffix=" text",
            pdf_page_number=1,
            pdf_char_offset=10,
            pdf_file_hash="pdf_hash_123",
        )

        assert result.anchor_type == "pdf"
        assert result.pdf_page_number == 1
        assert result.pdf_char_offset == 10
        assert result.pdf_file_hash == "pdf_hash_123"

    def test_create_highlight_pdf_anchor_missing_page_number(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating PDF highlight without page number fails."""
        with pytest.raises(ValidationAppError):
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="pdf",
                text_start=0,
                text_end=5,
                quote="page",
                prefix="",
                suffix=" text",
                pdf_page_number=None,  # Missing
                pdf_char_offset=10,
                pdf_file_hash="pdf_hash_123",
            )

    def test_create_highlight_pdf_anchor_missing_char_offset(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating PDF highlight without char offset fails."""
        with pytest.raises(ValidationAppError):
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="pdf",
                text_start=0,
                text_end=5,
                quote="page",
                prefix="",
                suffix=" text",
                pdf_page_number=1,
                pdf_char_offset=None,  # Missing
                pdf_file_hash="pdf_hash_123",
            )

    def test_create_highlight_pdf_anchor_missing_file_hash(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating PDF highlight without file hash fails."""
        with pytest.raises(ValidationAppError):
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="pdf",
                text_start=0,
                text_end=5,
                quote="page",
                prefix="",
                suffix=" text",
                pdf_page_number=1,
                pdf_char_offset=10,
                pdf_file_hash=None,  # Missing
            )


# ============================================================================
# HIGHLIGHT RETRIEVAL TESTS
# ============================================================================


class TestGetHighlight:
    """Tests for get_highlight_for_user function."""

    def test_get_highlight_own_highlight(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test retrieving own highlight."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        created = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        retrieved = get_highlight_for_user(
            session=db_session,
            user=user1,
            highlight_id=created.id,
        )

        assert retrieved.id == created.id
        assert retrieved.user_id == user1.id

    def test_get_highlight_not_found(self, db_session: Session, user1: User) -> None:
        """Test retrieving non-existent highlight raises 404."""
        with pytest.raises(NotFoundError):
            get_highlight_for_user(
                session=db_session,
                user=user1,
                highlight_id=uuid.uuid4(),
            )

    def test_get_highlight_not_owned(
        self, db_session: Session, user1: User, user2: User, doc1: Document
    ) -> None:
        """Test retrieving highlight not owned by user raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        created = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        with pytest.raises(NotFoundError):
            get_highlight_for_user(
                session=db_session,
                user=user2,  # Different user
                highlight_id=created.id,
            )

    def test_get_highlight_deleted(self, db_session: Session, user1: User, doc1: Document) -> None:
        """Test retrieving soft-deleted highlight raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        created = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        # Soft delete
        soft_delete_highlight(
            session=db_session,
            user=user1,
            highlight_id=created.id,
        )

        with pytest.raises(NotFoundError):
            get_highlight_for_user(
                session=db_session,
                user=user1,
                highlight_id=created.id,
            )


# ============================================================================
# HIGHLIGHT LISTING TESTS
# ============================================================================


class TestListHighlights:
    """Tests for list_highlights_for_document function."""

    def test_list_highlights_empty(self, db_session: Session, user1: User, doc1: Document) -> None:
        """Test listing highlights on document with none."""
        result = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=20),
        )

        assert result.items == []
        assert result.has_more is False
        assert result.next_cursor is None

    def test_list_highlights_single(self, db_session: Session, user1: User, doc1: Document) -> None:
        """Test listing highlights on document with one."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        created = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        result = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=20),
        )

        assert len(result.items) == 1
        assert result.items[0].id == created.id
        assert result.has_more is False

    def test_list_highlights_multiple(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test listing multiple highlights."""
        anchor1 = make_highlight_anchor(doc1.canonical_text, "This")
        h1 = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor1,
        )

        anchor2 = make_highlight_anchor(doc1.canonical_text, "is")
        h2 = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor2,
        )

        result = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=20),
        )

        assert len(result.items) == 2
        # Order should be newest first (h2 created after h1)
        assert result.items[0].id == h2.id
        assert result.items[1].id == h1.id

    def test_list_highlights_pagination(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test pagination works correctly."""
        # Create 5 highlights
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        for _ in range(5):
            create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )

        # Fetch with limit 2
        result1 = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=2),
        )

        assert len(result1.items) == 2
        assert result1.has_more is True
        assert result1.next_cursor is not None

        # Fetch next page
        result2 = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=2, cursor=result1.next_cursor),
        )

        assert len(result2.items) == 2
        assert result2.has_more is True

        # Fetch third page
        result3 = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=2, cursor=result2.next_cursor),
        )

        assert len(result3.items) == 1
        assert result3.has_more is False

        # Verify no duplicates across pages
        ids1 = {h.id for h in result1.items}
        ids2 = {h.id for h in result2.items}
        ids3 = {h.id for h in result3.items}
        assert len(ids1 & ids2) == 0
        assert len(ids2 & ids3) == 0
        assert len(ids1 & ids3) == 0

    def test_list_highlights_excludes_deleted(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test list excludes soft-deleted highlights."""
        anchor1 = make_highlight_anchor(doc1.canonical_text, "This")
        h1 = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor1,
        )

        anchor2 = make_highlight_anchor(doc1.canonical_text, "is")
        h2 = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor2,
        )

        # Delete one
        soft_delete_highlight(
            session=db_session,
            user=user1,
            highlight_id=h2.id,
        )

        result = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=20),
        )

        assert len(result.items) == 1
        assert result.items[0].id == h1.id

    def test_list_highlights_only_own(
        self, db_session: Session, user1: User, user2: User, doc1: Document
    ) -> None:
        """Test list only includes user's own highlights."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        _ = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        # user2 tries to list highlights on user1's document
        result = list_highlights_for_document(
            session=db_session,
            user=user2,
            document_id=doc1.id,
            pagination=PaginationParams(limit=20),
        )

        assert result.items == []


# ============================================================================
# HIGHLIGHT SOFT-DELETE TESTS
# ============================================================================


class TestSoftDeleteHighlight:
    """Tests for soft_delete_highlight function."""

    def test_soft_delete_highlight(self, db_session: Session, user1: User, doc1: Document) -> None:
        """Test soft-deleting a highlight."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        created = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        result = soft_delete_highlight(
            session=db_session,
            user=user1,
            highlight_id=created.id,
        )

        assert result is True

        # Verify cannot retrieve deleted highlight
        with pytest.raises(NotFoundError):
            get_highlight_for_user(
                session=db_session,
                user=user1,
                highlight_id=created.id,
            )

    def test_soft_delete_already_deleted(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test soft-deleting already deleted highlight returns False."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        created = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        soft_delete_highlight(
            session=db_session,
            user=user1,
            highlight_id=created.id,
        )

        # Delete again
        result = soft_delete_highlight(
            session=db_session,
            user=user1,
            highlight_id=created.id,
        )

        assert result is False

    def test_soft_delete_not_found(self, db_session: Session, user1: User) -> None:
        """Test deleting non-existent highlight raises 404."""
        with pytest.raises(NotFoundError):
            soft_delete_highlight(
                session=db_session,
                user=user1,
                highlight_id=uuid.uuid4(),
            )

    def test_soft_delete_not_owned(
        self, db_session: Session, user1: User, user2: User, doc1: Document
    ) -> None:
        """Test deleting highlight not owned by user raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        created = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        with pytest.raises(NotFoundError):
            soft_delete_highlight(
                session=db_session,
                user=user2,
                highlight_id=created.id,
            )


# ============================================================================
# ANNOTATION CREATION TESTS
# ============================================================================


class TestCreateAnnotation:
    """Tests for create_annotation function."""

    def test_create_annotation_valid(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating annotation on valid highlight."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        result = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="This is an important passage.",
        )

        assert isinstance(result, AnnotationSummary)
        assert result.user_id == user1.id
        assert result.highlight_id == hl.id
        assert result.content == "This is an important passage."
        assert result.is_public is False

    def test_create_annotation_empty_content(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating annotation with empty content fails."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        with pytest.raises(ValidationAppError):
            create_annotation(
                session=db_session,
                user=user1,
                highlight_id=hl.id,
                content="",  # Empty
            )

    def test_create_annotation_whitespace_content(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating annotation with whitespace-only content fails."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        with pytest.raises(ValidationAppError):
            create_annotation(
                session=db_session,
                user=user1,
                highlight_id=hl.id,
                content="   ",  # Only whitespace
            )

    def test_create_annotation_highlight_not_found(self, db_session: Session, user1: User) -> None:
        """Test creating annotation on non-existent highlight raises 404."""
        with pytest.raises(NotFoundError):
            create_annotation(
                session=db_session,
                user=user1,
                highlight_id=uuid.uuid4(),
                content="Some content",
            )

    def test_create_annotation_highlight_not_owned(
        self, db_session: Session, user1: User, user2: User, doc1: Document
    ) -> None:
        """Test creating annotation on highlight not owned by user raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        with pytest.raises(NotFoundError):
            create_annotation(
                session=db_session,
                user=user2,  # Different user
                highlight_id=hl.id,
                content="Some content",
            )

    def test_create_annotation_highlight_deleted(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test creating annotation on soft-deleted highlight raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        soft_delete_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
        )

        with pytest.raises(NotFoundError):
            create_annotation(
                session=db_session,
                user=user1,
                highlight_id=hl.id,
                content="Some content",
            )


# ============================================================================
# ANNOTATION LISTING TESTS
# ============================================================================


class TestListAnnotations:
    """Tests for list_annotations_for_highlight function."""

    def test_list_annotations_empty(self, db_session: Session, user1: User, doc1: Document) -> None:
        """Test listing annotations on highlight with none."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        result = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=20),
        )

        assert result.items == []
        assert result.has_more is False

    def test_list_annotations_single(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test listing annotations on highlight with one."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        ann = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="Important",
        )

        result = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=20),
        )

        assert len(result.items) == 1
        assert result.items[0].id == ann.id

    def test_list_annotations_multiple(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test listing multiple annotations."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        ann1 = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="First note",
        )

        ann2 = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="Second note",
        )

        result = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=20),
        )

        assert len(result.items) == 2
        # Newest first
        assert result.items[0].id == ann2.id
        assert result.items[1].id == ann1.id

    def test_list_annotations_pagination(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test pagination for annotations."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        # Create 3 annotations
        for _ in range(3):
            create_annotation(
                session=db_session,
                user=user1,
                highlight_id=hl.id,
                content="Note",
            )

        # Fetch with limit 1
        result1 = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=1),
        )

        assert len(result1.items) == 1
        assert result1.has_more is True
        assert result1.next_cursor is not None

        # Fetch next page
        result2 = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=1, cursor=result1.next_cursor),
        )

        assert len(result2.items) == 1
        assert result2.has_more is True

        # Verify different annotations
        assert result1.items[0].id != result2.items[0].id

    def test_list_annotations_excludes_deleted(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test list excludes soft-deleted annotations."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        ann1 = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="First",
        )

        ann2 = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="Second",
        )

        soft_delete_annotation(
            session=db_session,
            user=user1,
            annotation_id=ann2.id,
        )

        result = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=20),
        )

        assert len(result.items) == 1
        assert result.items[0].id == ann1.id

    def test_list_annotations_highlight_not_found(self, db_session: Session, user1: User) -> None:
        """Test listing annotations on non-existent highlight raises 404."""
        with pytest.raises(NotFoundError):
            list_annotations_for_highlight(
                session=db_session,
                user=user1,
                highlight_id=uuid.uuid4(),
                pagination=PaginationParams(limit=20),
            )


# ============================================================================
# ANNOTATION SOFT-DELETE TESTS
# ============================================================================


class TestSoftDeleteAnnotation:
    """Tests for soft_delete_annotation function."""

    def test_soft_delete_annotation(self, db_session: Session, user1: User, doc1: Document) -> None:
        """Test soft-deleting an annotation."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        ann = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="Some content",
        )

        result = soft_delete_annotation(
            session=db_session,
            user=user1,
            annotation_id=ann.id,
        )

        assert result is True

        # Verify cannot list deleted annotation
        list_result = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=20),
        )
        assert list_result.items == []

    def test_soft_delete_already_deleted(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test soft-deleting already deleted annotation returns False."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        ann = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="Some content",
        )

        soft_delete_annotation(
            session=db_session,
            user=user1,
            annotation_id=ann.id,
        )

        result = soft_delete_annotation(
            session=db_session,
            user=user1,
            annotation_id=ann.id,
        )

        assert result is False

    def test_soft_delete_annotation_not_found(self, db_session: Session, user1: User) -> None:
        """Test deleting non-existent annotation raises 404."""
        with pytest.raises(NotFoundError):
            soft_delete_annotation(
                session=db_session,
                user=user1,
                annotation_id=uuid.uuid4(),
            )

    def test_soft_delete_annotation_not_owned(
        self, db_session: Session, user1: User, user2: User, doc1: Document
    ) -> None:
        """Test deleting annotation not owned by user raises 404."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        ann = create_annotation(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            content="Some content",
        )

        with pytest.raises(NotFoundError):
            soft_delete_annotation(
                session=db_session,
                user=user2,  # Different user
                annotation_id=ann.id,
            )


# ============================================================================
# DETERMINISTIC ORDERING TESTS
# ============================================================================


class TestDeterministicOrdering:
    """Tests for deterministic ordering of lists."""

    def test_highlight_order_deterministic(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test highlights are ordered consistently."""
        anchor = make_highlight_anchor(doc1.canonical_text, "is")
        ids = []
        for _ in range(3):
            hl = create_highlight(
                session=db_session,
                user=user1,
                media_type="document",
                media_id=doc1.id,
                anchor_type="text",
                **anchor,
            )
            ids.append(hl.id)

        # Fetch twice and verify same order
        result1 = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=20),
        )

        result2 = list_highlights_for_document(
            session=db_session,
            user=user1,
            document_id=doc1.id,
            pagination=PaginationParams(limit=20),
        )

        order1 = [h.id for h in result1.items]
        order2 = [h.id for h in result2.items]
        assert order1 == order2

    def test_annotation_order_deterministic(
        self, db_session: Session, user1: User, doc1: Document
    ) -> None:
        """Test annotations are ordered consistently."""
        anchor = make_highlight_anchor(doc1.canonical_text, "This")
        hl = create_highlight(
            session=db_session,
            user=user1,
            media_type="document",
            media_id=doc1.id,
            anchor_type="text",
            **anchor,
        )

        for _ in range(3):
            create_annotation(
                session=db_session,
                user=user1,
                highlight_id=hl.id,
                content="Note",
            )

        # Fetch twice and verify same order
        result1 = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=20),
        )

        result2 = list_annotations_for_highlight(
            session=db_session,
            user=user1,
            highlight_id=hl.id,
            pagination=PaginationParams(limit=20),
        )

        order1 = [a.id for a in result1.items]
        order2 = [a.id for a in result2.items]
        assert order1 == order2
