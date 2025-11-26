"""Link model for symmetric, untyped relationships between objects."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Link(Base):
    """Link model representing a symmetric, untyped relationship between two objects.

    v1 supports only untyped "related" links; typed links are deferred to Phase 2+.

    Fields:
    - id: UUID primary key
    - source_type: Type of source object (document, episode, video, highlight, annotation, message, conversation)
    - source_id: UUID of source object
    - target_type: Type of target object
    - target_id: UUID of target object
    - created_by_user_id: FK to users.id (who created the link)
    - created_at: UTC timestamp of creation

    Invariants:
    - Symmetric: link(A, B) is equivalent to link(B, A)
    - Stored in canonical ordering to prevent duplicates
    - Uniqueness constraint on (source_type, source_id, target_type, target_id)
    - No self-links: source != target (enforced via CHECK constraint)
    - Both endpoints must be valid object types

    Visibility:
    - Links are NOT independently visible
    - Both endpoints must be visible to a user to see the link
    - Links do NOT grant additional visibility
    """

    __tablename__ = "links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    created_by_user: Mapped["User"] = relationship("User", back_populates="links")

    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            name="uq_links_canonical",
        ),
        Index("idx_links_source", source_type, source_id),
        Index("idx_links_target", target_type, target_id),
        Index("idx_links_creator", created_by_user_id),
        CheckConstraint(
            "NOT (source_type = target_type AND source_id = target_id)",
            name="ck_links_no_self_links",
        ),
        CheckConstraint(
            "source_type IN ('document', 'episode', 'video', 'highlight', 'annotation', 'message', 'conversation')",
            name="ck_links_valid_source_type",
        ),
        CheckConstraint(
            "target_type IN ('document', 'episode', 'video', 'highlight', 'annotation', 'message', 'conversation')",
            name="ck_links_valid_target_type",
        ),
    )
