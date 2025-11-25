"""Document model for uploaded files and their canonical text representations."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    """Document model representing an uploaded document (PDF, EPUB, HTML, etc.).

    Fields:
    - id: UUID primary key
    - user_id: FK to users.id (owner)
    - title: Document title
    - author: Optional author name
    - published_date: Optional publication date (ISO date)
    - source_url: Optional URL where document was sourced from

    Original blob storage (critical for reproducibility):
    - original_blob_key: S3 or filesystem key to original uploaded file
    - original_mime_type: MIME type of original (e.g., application/pdf)
    - original_size_bytes: File size in bytes

    Canonical text (immutable after creation):
    - content_hash: SHA256 of the original blob (for change detection)
    - canonical_text: Deterministic UTF-8 text extraction from original
    - canonical_hash: SHA256 of canonical_text
    - canonical_version: Version of extraction logic used
    - text_byte_length: Length of canonical_text in bytes
    - extractor_version: Version string of extraction tool

    Structure and metadata:
    - structure: JSONB with document structure (sections, pages, etc.)
    - metadata: JSONB with extracted metadata
    - language: Detected or specified language code

    Processing status:
    - status: One of 'pending', 'processing', 'ready', 'failed'
    - error_code: Error code if status='failed'
    - error_message: Human-readable error message
    - retries_count: Number of failed processing attempts
    - last_attempted_at: Timestamp of last processing attempt

    Embedding status:
    - embedding_status: One of 'pending', 'ready', 'failed'
    - embedding_model: Model name used for embeddings
    - chunk_version: Version of chunking strategy

    Lifecycle:
    - deleted_at: Soft delete timestamp (NULL = not deleted)
    - created_at: UTC timestamp of upload
    - updated_at: UTC timestamp of last update
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_date: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # ISO date format
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Original blob storage (immutable)
    original_blob_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    original_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Canonical text (immutable)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SHA256
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    canonical_version: Mapped[int] = mapped_column(nullable=False, default=1)
    text_byte_length: Mapped[int] = mapped_column(nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(50), nullable=False)

    # Structure and metadata
    structure: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    doc_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Processing status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retries_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Embedding status
    embedding_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    chunk_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

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

    # Foreign key to users
    user: Mapped["User"] = relationship("User", back_populates="documents")

    # Relationships
    highlights: Mapped[list["Highlight"]] = relationship(
        "Highlight",
        foreign_keys="Highlight.media_id",
        primaryjoin="and_(Highlight.media_type == 'document', Highlight.media_id == Document.id)",
        cascade="all, delete-orphan",
        overlaps="highlights",
    )
    content_chunks: Mapped[list["ContentChunk"]] = relationship(
        "ContentChunk",
        foreign_keys="ContentChunk.media_id",
        primaryjoin="and_(ContentChunk.media_type == 'document', ContentChunk.media_id == Document.id)",
        cascade="all, delete-orphan",
        overlaps="content_chunks",
    )
    library_media: Mapped[list["LibraryMedia"]] = relationship(
        "LibraryMedia",
        foreign_keys="LibraryMedia.media_id",
        primaryjoin="and_(LibraryMedia.media_type == 'document', LibraryMedia.media_id == Document.id)",
        cascade="all, delete-orphan",
        overlaps="library_media",
    )
    links_as_source: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.source_id",
        primaryjoin="and_(Link.source_type == 'document', Link.source_id == Document.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_source",
    )
    links_as_target: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.target_id",
        primaryjoin="and_(Link.target_type == 'document', Link.target_id == Document.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_target",
    )

    __table_args__ = (
        Index("idx_documents_user", user_id),
        Index(
            "idx_documents_status",
            status,
            postgresql_where="status != 'ready' AND deleted_at IS NULL",
        ),
        Index(
            "idx_documents_embedding_status",
            embedding_status,
            postgresql_where="embedding_status != 'ready' AND deleted_at IS NULL",
        ),
        Index("idx_documents_content_hash", content_hash),
        CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_documents_status",
        ),
        CheckConstraint(
            "embedding_status IN ('pending', 'ready', 'failed')",
            name="ck_documents_embedding_status",
        ),
    )
