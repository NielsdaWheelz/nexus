"""User model for Clerk-authenticated users."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """User model representing a Clerk-authenticated user.

    Fields:
    - id: UUID primary key
    - external_user_id: Clerk 'sub' claim, unique and immutable
    - email: User's email address, unique and normalized (lowercase)
    - created_at: UTC timestamp of account creation
    - updated_at: UTC timestamp of last update

    Relationships:
    - documents: User's uploaded documents
    - highlights: User's highlights across documents
    - annotations: User's annotations on highlights
    - conversations: User's conversations
    - messages: User's messages (both user and assistant)
    - libraries: User's owned libraries
    - library_memberships: User's memberships in shared libraries
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_user_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships (lazy="select" for sync, will be overridden for async)
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="user", cascade="all, delete-orphan"
    )
    highlights: Mapped[list["Highlight"]] = relationship(
        "Highlight", back_populates="user", cascade="all, delete-orphan"
    )
    annotations: Mapped[list["Annotation"]] = relationship(
        "Annotation", back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="user", cascade="all, delete-orphan"
    )
    libraries: Mapped[list["Library"]] = relationship(
        "Library", back_populates="user", cascade="all, delete-orphan"
    )
    library_memberships: Mapped[list["LibraryMembership"]] = relationship(
        "LibraryMembership", back_populates="user", cascade="all, delete-orphan"
    )
    links: Mapped[list["Link"]] = relationship(
        "Link", back_populates="created_by_user", cascade="all, delete-orphan"
    )
    readers: Mapped[list["Reader"]] = relationship(
        "Reader", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_users_external_user_id", external_user_id),)
