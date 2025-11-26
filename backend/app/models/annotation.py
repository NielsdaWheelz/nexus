"""Annotation model for user notes attached to highlights."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Annotation(Base):
    """Annotation model representing a user's note (text) on a highlight.

    Fields:
    - id: UUID primary key
    - user_id: FK to users.id (creator)
    - highlight_id: FK to highlights.id (the highlight being annotated)
    - content: The annotation text (markdown or plain text)
    - is_public: Whether annotation is shared publicly

    Lifecycle:
    - deleted_at: Soft delete timestamp
    - created_at: UTC timestamp of creation
    - updated_at: UTC timestamp of last update

    Invariants:
    - One annotation per highlight (enforced in schema)
    - Annotations always reference valid highlights
    - Cascade delete when highlight is deleted
    """

    __tablename__ = "annotations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    highlight_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("highlights.id"), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)
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
    user: Mapped["User"] = relationship("User", back_populates="annotations")
    highlight: Mapped["Highlight"] = relationship("Highlight", back_populates="annotations")
    object_visibility: Mapped[list["ObjectLibraryVisibility"]] = relationship(
        "ObjectLibraryVisibility",
        foreign_keys="ObjectLibraryVisibility.object_id",
        primaryjoin="and_(ObjectLibraryVisibility.object_type == 'annotation', ObjectLibraryVisibility.object_id == Annotation.id)",
        cascade="all, delete-orphan",
        overlaps="object_visibility",
    )
    thought_chunks: Mapped[list["ThoughtChunk"]] = relationship(
        "ThoughtChunk",
        foreign_keys="ThoughtChunk.object_id",
        primaryjoin="and_(ThoughtChunk.object_type == 'annotation', ThoughtChunk.object_id == Annotation.id)",
        cascade="all, delete-orphan",
        overlaps="thought_chunks",
    )
    links_as_source: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.source_id",
        primaryjoin="and_(Link.source_type == 'annotation', Link.source_id == Annotation.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_source",
    )
    links_as_target: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.target_id",
        primaryjoin="and_(Link.target_type == 'annotation', Link.target_id == Annotation.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_target",
    )

    __table_args__ = (
        Index("idx_annotations_highlight", highlight_id, postgresql_where="deleted_at IS NULL"),
        Index("idx_annotations_user", user_id, postgresql_where="deleted_at IS NULL"),
    )
