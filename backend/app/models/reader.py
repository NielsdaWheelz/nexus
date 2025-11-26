"""Reader model for tracking reading sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class Reader(Base):
    """Reader model tracking a user's reading session for a document.

    Represents a reading session: one reader per (user, document) pair.
    Tracks the user's current reading position and last access time.

    Fields:
    - id: UUID primary key
    - user_id: FK to users.id (the reader)
    - document_id: FK to documents.id (the document being read)
    - current_position: Optional byte offset into canonical_text (None = not started)
    - last_read_at: Optional timestamp of last access
    - created_at: UTC timestamp when reader was created
    - updated_at: UTC timestamp of last update

    Constraints:
    - UNIQUE (user_id, document_id): One reader per user+document pair
    - Foreign keys enforce referential integrity
    - Indices on user_id and document_id for efficient queries

    Relationships:
    - user: The user performing the reading
    - document: The document being read
    """

    __tablename__ = "readers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )

    current_position: Mapped[Optional[int]] = mapped_column(nullable=True)
    """Byte offset into canonical_text; None = not started"""

    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    """Timestamp of last read activity"""

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
    user: Mapped["User"] = relationship("User", back_populates="readers")
    document: Mapped["Document"] = relationship("Document", back_populates="readers")

    __table_args__ = (
        UniqueConstraint("user_id", "document_id", name="uq_readers_user_document"),
        Index("idx_readers_user", user_id),
        Index("idx_readers_document", document_id),
    )
