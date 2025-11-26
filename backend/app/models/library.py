"""Library models for shared collections and visibility management."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Library(Base):
    """Library model representing a shared collection of media.

    Fields:
    - id: UUID primary key
    - user_id: FK to users.id (owner)
    - name: Library name
    - description: Optional description
    - is_public: Whether library is publicly visible

    Timestamps:
    - created_at: UTC timestamp of creation
    - updated_at: UTC timestamp of last update

    Relationships:
    - user: Owner of the library
    - memberships: User memberships in this library
    - media: Media items in this library
    """

    __tablename__ = "libraries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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
    user: Mapped["User"] = relationship("User", back_populates="libraries")
    memberships: Mapped[list["LibraryMembership"]] = relationship(
        "LibraryMembership", back_populates="library", cascade="all, delete-orphan"
    )
    media: Mapped[list["LibraryMedia"]] = relationship(
        "LibraryMedia", back_populates="library", cascade="all, delete-orphan"
    )
    object_visibility: Mapped[list["ObjectLibraryVisibility"]] = relationship(
        "ObjectLibraryVisibility",
        back_populates="library",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_libraries_user", user_id),
        Index("idx_libraries_public", is_public, postgresql_where="is_public = TRUE"),
    )


class LibraryMembership(Base):
    """LibraryMembership model for user memberships in libraries.

    Fields:
    - id: UUID primary key
    - library_id: FK to libraries.id
    - user_id: FK to users.id
    - role: One of 'owner', 'editor', 'viewer'
    - created_at: UTC timestamp of when user was added

    Invariants:
    - Unique (library_id, user_id): one membership per user per library
    """

    __tablename__ = "library_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    library_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    library: Mapped["Library"] = relationship("Library", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="library_memberships")

    __table_args__ = (
        UniqueConstraint("library_id", "user_id", name="uq_library_memberships_library_user"),
        Index("idx_library_memberships_user", user_id),
        Index("idx_library_memberships_library", library_id),
        CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')", name="ck_library_memberships_role"
        ),
    )


class LibraryMedia(Base):
    """LibraryMedia model for media items in libraries.

    Fields:
    - id: UUID primary key
    - library_id: FK to libraries.id
    - media_type: One of 'document', 'episode', 'video'
    - media_id: UUID of the media object
    - added_by_user_id: FK to users.id (user who added the media)
    - created_at: UTC timestamp of when media was added

    Invariants:
    - Unique (library_id, media_type, media_id): each media item appears once per library
    """

    __tablename__ = "library_media"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    library_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    media_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    added_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    library: Mapped["Library"] = relationship("Library", back_populates="media")

    __table_args__ = (
        UniqueConstraint(
            "library_id", "media_type", "media_id", name="uq_library_media_library_media"
        ),
        Index("idx_library_media_library", library_id),
        Index("idx_library_media_media", media_type, media_id),
        CheckConstraint(
            "media_type IN ('document', 'episode', 'video')", name="ck_library_media_type"
        ),
    )


class ObjectLibraryVisibility(Base):
    """ObjectLibraryVisibility model for sharing objects to libraries.

    This table tracks which library-specific objects (highlights, annotations, conversations, messages)
    are shared to which libraries, allowing for selective sharing without changing overall visibility.

    Fields:
    - id: UUID primary key
    - object_type: One of 'highlight', 'annotation', 'conversation', 'message'
    - object_id: UUID of the object
    - library_id: FK to libraries.id
    - shared_by_user_id: FK to users.id (user who shared the object)
    - created_at: UTC timestamp of when object was shared

    Invariants:
    - Unique (object_type, object_id, library_id): each object shared once per library
    """

    __tablename__ = "object_library_visibility"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    object_type: Mapped[str] = mapped_column(String(20), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    library_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    shared_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    library: Mapped["Library"] = relationship("Library", back_populates="object_visibility")

    __table_args__ = (
        UniqueConstraint(
            "object_type", "object_id", "library_id", name="uq_object_visibility_object_library"
        ),
        Index("idx_object_visibility_library", library_id),
        Index("idx_object_visibility_object", object_type, object_id),
        CheckConstraint(
            "object_type IN ('highlight', 'annotation', 'conversation', 'message')",
            name="ck_object_visibility_type",
        ),
    )
