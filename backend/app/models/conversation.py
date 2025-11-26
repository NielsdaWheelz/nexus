"""Conversation model for LLM conversations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    """Conversation model representing an LLM conversation thread.

    Fields:
    - id: UUID primary key
    - user_id: FK to users.id (owner)
    - title: Conversation title
    - description: Optional description

    Summary state:
    - summary_state: JSONB with summary metadata (Phase 2+)
    - summary_updated_at: Timestamp of last summary update

    Visibility:
    - is_public: Whether conversation is publicly accessible

    Lifecycle:
    - deleted_at: Soft delete timestamp
    - created_at: UTC timestamp of creation
    - updated_at: UTC timestamp of last update

    Relationships:
    - user: Owner of the conversation
    - messages: Messages in the conversation thread
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Summary state (Phase 2+)
    summary_state: Mapped[Optional[dict[str, object]]] = mapped_column(JSON, nullable=True)
    summary_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Visibility
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
    user: Mapped["User"] = relationship("User", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )
    object_visibility: Mapped[list["ObjectLibraryVisibility"]] = relationship(
        "ObjectLibraryVisibility",
        foreign_keys="ObjectLibraryVisibility.object_id",
        primaryjoin="and_(ObjectLibraryVisibility.object_type == 'conversation', ObjectLibraryVisibility.object_id == Conversation.id)",
        cascade="all, delete-orphan",
        overlaps="object_visibility",
    )
    links_as_source: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.source_id",
        primaryjoin="and_(Link.source_type == 'conversation', Link.source_id == Conversation.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_source",
    )
    links_as_target: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.target_id",
        primaryjoin="and_(Link.target_type == 'conversation', Link.target_id == Conversation.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_target",
    )

    __table_args__ = (
        Index("idx_conversations_user", user_id, postgresql_where="deleted_at IS NULL"),
        Index(
            "idx_conversations_public",
            is_public,
            postgresql_where="is_public = TRUE AND deleted_at IS NULL",
        ),
    )
