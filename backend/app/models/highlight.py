"""Highlight model for text selections across documents, episodes, and videos."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Highlight(Base):
    """Highlight model representing a user's text selection (anchor) in media.

    Fields:
    - id: UUID primary key
    - user_id: FK to users.id (creator)
    - media_type: One of 'document', 'episode', 'video'
    - media_id: UUID of the media object

    Anchor type and coordinates:
    - anchor_type: One of 'text', 'pdf', 'transcript'
    - text_start: Byte offset start in canonical/transcript text (immutable)
    - text_end: Byte offset end in canonical/transcript text (immutable)

    Anchoring metadata (immutable):
    - quote: The exact text of the highlight
    - prefix: Text before the highlight (for disambiguation)
    - suffix: Text after the highlight (for disambiguation)

    Version anchors:
    - canonical_version: Version of canonical text when highlight was created (for documents)
    - transcript_hash: SHA256 of transcript at creation time (for episodes/videos)

    PDF-specific anchoring (only set if anchor_type='pdf'):
    - pdf_page_number: Page number in PDF
    - pdf_char_offset: Character offset within page
    - pdf_extraction_confidence: Confidence score of text extraction
    - pdf_file_hash: SHA256 of PDF file for stability

    Transcript-specific anchoring (only set if anchor_type='transcript'):
    - time_start: Start time in seconds
    - time_end: End time in seconds

    Mutable fields:
    - color: Highlight color (yellow, blue, green, pink, purple)
    - is_hidden: Whether highlight is hidden from list
    - is_detached: Whether highlight lost its anchor due to content change
    - detached_reason: Reason why highlight was detached
    - is_public: Whether highlight is shared publicly

    Lifecycle:
    - deleted_at: Soft delete timestamp
    - created_at: UTC timestamp of creation
    - updated_at: UTC timestamp of last update
    """

    __tablename__ = "highlights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    media_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    anchor_type: Mapped[str] = mapped_column(String(20), nullable=False)

    text_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text_end: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Anchoring metadata (immutable)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    prefix: Mapped[str] = mapped_column(Text, nullable=False)
    suffix: Mapped[str] = mapped_column(Text, nullable=False)

    # Version anchors
    canonical_version: Mapped[Optional[int]] = mapped_column(nullable=True)
    transcript_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # PDF-specific
    pdf_page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pdf_char_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pdf_extraction_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pdf_file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Transcript-specific
    time_start: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    time_end: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Mutable fields
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="yellow")
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_detached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detached_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="highlights")
    annotations: Mapped[list["Annotation"]] = relationship(
        "Annotation", back_populates="highlight", cascade="all, delete-orphan"
    )
    object_visibility: Mapped[list["ObjectLibraryVisibility"]] = relationship(
        "ObjectLibraryVisibility",
        foreign_keys="ObjectLibraryVisibility.object_id",
        primaryjoin="and_(ObjectLibraryVisibility.object_type == 'highlight', ObjectLibraryVisibility.object_id == Highlight.id)",
        cascade="all, delete-orphan",
        overlaps="object_visibility",
    )
    links_as_source: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.source_id",
        primaryjoin="and_(Link.source_type == 'highlight', Link.source_id == Highlight.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_source",
    )
    links_as_target: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.target_id",
        primaryjoin="and_(Link.target_type == 'highlight', Link.target_id == Highlight.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_target",
    )

    __table_args__ = (
        Index(
            "idx_highlights_user", user_id, postgresql_where="NOT is_hidden AND deleted_at IS NULL"
        ),
        Index("idx_highlights_media", media_type, media_id, postgresql_where="deleted_at IS NULL"),
        Index("idx_highlights_anchor_type", anchor_type),
        Index(
            "idx_highlights_pdf",
            media_id,
            pdf_page_number,
            postgresql_where="anchor_type = 'pdf' AND deleted_at IS NULL",
        ),
        Index(
            "idx_highlights_transcript",
            media_id,
            time_start,
            postgresql_where="anchor_type = 'transcript' AND deleted_at IS NULL",
        ),
        CheckConstraint("text_end > text_start", name="ck_highlights_text_range"),
        CheckConstraint(
            "media_type IN ('document', 'episode', 'video')", name="ck_highlights_media_type"
        ),
        CheckConstraint(
            "anchor_type IN ('text', 'pdf', 'transcript')", name="ck_highlights_anchor_type"
        ),
        CheckConstraint(
            "color IN ('yellow', 'blue', 'green', 'pink', 'purple')", name="ck_highlights_color"
        ),
        # Version anchor consistency
        CheckConstraint(
            "(media_type = 'document' AND canonical_version IS NOT NULL AND transcript_hash IS NULL) OR "
            "(media_type IN ('episode', 'video') AND transcript_hash IS NOT NULL AND canonical_version IS NULL)",
            name="ck_highlights_version_anchor",
        ),
        # Anchor type validity
        CheckConstraint(
            "(anchor_type = 'text' AND pdf_page_number IS NULL AND pdf_char_offset IS NULL AND "
            "pdf_extraction_confidence IS NULL AND pdf_file_hash IS NULL AND time_start IS NULL AND time_end IS NULL) OR "
            "(anchor_type = 'pdf' AND pdf_page_number IS NOT NULL AND pdf_char_offset IS NOT NULL AND "
            "pdf_file_hash IS NOT NULL AND time_start IS NULL AND time_end IS NULL) OR "
            "(anchor_type = 'transcript' AND time_start IS NOT NULL AND time_end IS NOT NULL AND "
            "pdf_page_number IS NULL AND pdf_char_offset IS NULL AND pdf_extraction_confidence IS NULL AND pdf_file_hash IS NULL)",
            name="ck_highlights_anchor_type_validity",
        ),
        # Media/anchor compatibility
        CheckConstraint(
            "(media_type = 'document' AND anchor_type IN ('text', 'pdf')) OR "
            "(media_type IN ('episode', 'video') AND anchor_type = 'transcript')",
            name="ck_highlights_media_anchor_compatibility",
        ),
    )
