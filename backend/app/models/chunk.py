"""Chunk models for embeddings across three semantic spaces.

Per spec/schemas/chunks.md, there are three types of chunks:
1. Content chunks: For documents, episodes, videos
2. Thought chunks: For annotations, messages, conversation summaries
3. Metadata chunks: For document/episode/video titles, authors, descriptions

NOTE: Vector embeddings (pgvector) are added in PR 6.1 Embeddings Pipeline.
This PR creates the table structure; embeddings column added later via migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ContentChunk(Base):
    """Content chunk for textual content from documents, episodes, videos.

    Used for semantic search over the primary content.

    Fields:
    - id: UUID primary key
    - media_type: One of 'document', 'episode', 'video'
    - media_id: UUID of the media object
    - chunk_version: Version string of chunking strategy (e.g., "v1")
    - embedding_model: Model name used for embeddings (e.g., "text-embedding-3-small")
    - text_start: Byte offset start in canonical/transcript text
    - text_end: Byte offset end in canonical/transcript text
    - text: The chunk text
    - embedding: Vector representation (1536 dims for OpenAI, configurable)
    - metadata: JSONB with chunk-specific metadata (section_title, page_number, time_start, time_end, etc.)
    - created_at: UTC timestamp of creation

    Indexes:
    - (media_type, media_id): Fast lookup by source
    - Vector index using IVFFlat with cosine similarity
    """

    __tablename__ = "content_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    media_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    chunk_version: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)

    text_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Note: embedding column (pgvector) is added in PR 6.1 via Alembic migration
    # For Phase 1, we store the structure without the vector column

    chunk_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_content_chunks_media", media_type, media_id),
        CheckConstraint(
            "media_type IN ('document', 'episode', 'video')", name="ck_content_chunks_media_type"
        ),
    )


class ThoughtChunk(Base):
    """Thought chunk for semantic content from user-generated thoughts.

    Used for semantic search over annotations, messages, conversation summaries.

    Fields:
    - id: UUID primary key
    - object_type: One of 'annotation', 'message', 'conversation_summary'
    - object_id: UUID of the thought source object
    - user_id: FK to users.id (owner of the thought)
    - chunk_version: Version string of chunking strategy
    - embedding_model: Model name used for embeddings
    - text: The chunk text
    - embedding: Vector representation (1536 dims, configurable)
    - metadata: JSONB with context (annotation_id, highlight_id, media_id, conversation_id, message_id, etc.)
    - created_at: UTC timestamp of creation

    Indexes:
    - (user_id): Fast lookup by user
    - (object_type, object_id): Fast lookup by source object
    - Vector index using IVFFlat with cosine similarity
    """

    __tablename__ = "thought_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    object_type: Mapped[str] = mapped_column(String(30), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    chunk_version: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Note: embedding column (pgvector) is added in PR 6.1 via Alembic migration

    chunk_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_thought_chunks_user", user_id),
        Index("idx_thought_chunks_object", object_type, object_id),
        CheckConstraint(
            "object_type IN ('annotation', 'message', 'conversation_summary')",
            name="ck_thought_chunks_object_type",
        ),
    )


class MetadataChunk(Base):
    """Metadata chunk for entity metadata (titles, authors, descriptions).

    Used for metadata-specific semantic search (boosting for exact match on titles, etc.).

    Fields:
    - id: UUID primary key
    - entity_type: One of 'document', 'episode', 'video', 'podcast'
    - entity_id: UUID of the entity
    - chunk_version: Version string of chunking strategy
    - embedding_model: Model name used for embeddings
    - text: The metadata text (concatenated title, author, description, etc.)
    - embedding: Vector representation (1536 dims, configurable)
    - metadata: JSONB with source fields (title, author, channel, description)
    - created_at: UTC timestamp of creation

    Indexes:
    - (entity_type, entity_id): Fast lookup by entity
    - Vector index using IVFFlat with cosine similarity
    """

    __tablename__ = "metadata_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    chunk_version: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Note: embedding column (pgvector) is added in PR 6.1 via Alembic migration

    chunk_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_metadata_chunks_entity", entity_type, entity_id),
        CheckConstraint(
            "entity_type IN ('document', 'episode', 'video', 'podcast')",
            name="ck_metadata_chunks_entity_type",
        ),
    )
