"""Message model for messages in conversations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Message(Base):
    """Message model representing a single message in a conversation.

    Fields:
    - id: UUID primary key
    - conversation_id: FK to conversations.id
    - user_id: FK to users.id (sender)
    - role: One of 'user' or 'assistant'
    - content: The message text (markdown or plain text)

    LLM metadata:
    - effective_model_id: Model ID used for assistant messages
    - token_count: Approximate token count for the message

    Visibility:
    - is_public: Whether message is publicly accessible

    Lifecycle:
    - deleted_at: Soft delete timestamp
    - created_at: UTC timestamp of creation (immutable)
    - updated_at: UTC timestamp of last update

    Invariants:
    - Messages are immutable after creation (no updates)
    - Role must be 'user' or 'assistant'
    - All messages in a conversation ordered by created_at ASC
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM metadata
    effective_model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Visibility
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps (immutable after creation)
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
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    user: Mapped["User"] = relationship("User", back_populates="messages")
    object_visibility: Mapped[list["ObjectLibraryVisibility"]] = relationship(
        "ObjectLibraryVisibility",
        foreign_keys="ObjectLibraryVisibility.object_id",
        primaryjoin="and_(ObjectLibraryVisibility.object_type == 'message', ObjectLibraryVisibility.object_id == Message.id)",
        cascade="all, delete-orphan",
        overlaps="object_visibility",
    )
    thought_chunks: Mapped[list["ThoughtChunk"]] = relationship(
        "ThoughtChunk",
        foreign_keys="ThoughtChunk.object_id",
        primaryjoin="and_(ThoughtChunk.object_type == 'message', ThoughtChunk.object_id == Message.id)",
        cascade="all, delete-orphan",
        overlaps="thought_chunks",
    )
    links_as_source: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.source_id",
        primaryjoin="and_(Link.source_type == 'message', Link.source_id == Message.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_source",
    )
    links_as_target: Mapped[list["Link"]] = relationship(
        "Link",
        foreign_keys="Link.target_id",
        primaryjoin="and_(Link.target_type == 'message', Link.target_id == Message.id)",
        cascade="all, delete-orphan",
        overlaps="links_as_target",
    )

    __table_args__ = (
        Index(
            "idx_messages_conversation",
            conversation_id,
            created_at,
            postgresql_where="deleted_at IS NULL",
        ),
        Index("idx_messages_user", user_id, postgresql_where="deleted_at IS NULL"),
    )
