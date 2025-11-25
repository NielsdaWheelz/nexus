"""Database module with ORM models and session management.

This module provides:
- Base registry for all ORM models
- Session makers for sync and async access
- Model imports for Alembic autogenerate
"""

from app.db.base import Base
from app.db.session import (
    get_async_engine,
    get_async_session_maker,
    get_session,
    get_sync_engine,
    get_sync_session_maker,
)
from app.models.annotation import Annotation  # noqa: F401
from app.models.chunk import ContentChunk, MetadataChunk, ThoughtChunk  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.highlight import Highlight  # noqa: F401
from app.models.library import (
    Library,
    LibraryMedia,
    LibraryMembership,
    ObjectLibraryVisibility,
)  # noqa: F401
from app.models.link import Link  # noqa: F401
from app.models.message import Message  # noqa: F401

# Import all models so Alembic can discover them
# Order matters: import parent models before child models (FK references)
from app.models.user import User  # noqa: F401

__all__ = [
    "Base",
    "get_session",
    "get_sync_engine",
    "get_async_engine",
    "get_sync_session_maker",
    "get_async_session_maker",
    # Models exported for convenience
    "User",
    "Document",
    "Highlight",
    "Annotation",
    "Conversation",
    "Message",
    "Library",
    "LibraryMembership",
    "LibraryMedia",
    "ObjectLibraryVisibility",
    "Link",
    "ContentChunk",
    "ThoughtChunk",
    "MetadataChunk",
]
