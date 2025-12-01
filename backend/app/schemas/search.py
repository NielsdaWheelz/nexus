"""Search API schemas (PR 6.3).

Defines request and response schemas for semantic search over document chunks.
"""

from pydantic import BaseModel, Field, conint, constr


class ChunkSearchRequest(BaseModel):
    """Request schema for chunk similarity search.

    Attributes:
        query: Search query text (required, 1-2000 chars)
        limit: Max results to return (optional, 1-100, default 20)
        document_ids: Optional list of document IDs to restrict search (typed IDs: doc_<uuid>)
    """

    query: constr(min_length=1, max_length=2000) = Field(
        description="Search query (1-2000 characters)"
    )
    limit: conint(gt=0, le=100) = Field(default=20, description="Max results (1-100)")
    document_ids: list[str] | None = Field(
        default=None,
        description="Optional list of document IDs to restrict search (typed IDs: doc_<uuid>)",
    )


class ChunkSearchHit(BaseModel):
    """Single search result in response.

    Attributes:
        chunk_id: UUID of matched chunk (typed ID: chunk_<uuid>)
        document_id: UUID of parent document (typed ID: doc_<uuid>)
        score: Similarity score (0-1, higher is more similar)
        text: Chunk text
        text_start: Byte offset of chunk start
        text_end: Byte offset of chunk end
    """

    chunk_id: str = Field(description="Chunk ID (typed: chunk_<uuid>)")
    document_id: str = Field(description="Document ID (typed: doc_<uuid>)")
    score: float = Field(description="Similarity score (0-1)")
    text: str = Field(description="Chunk text content")
    text_start: int = Field(description="Byte offset start")
    text_end: int = Field(description="Byte offset end")


class ChunkSearchResponse(BaseModel):
    """Response schema for chunk similarity search.

    Attributes:
        items: List of search results
        next_cursor: Pagination cursor (always None for now)
        has_more: Whether more results exist (always False for now)
    """

    items: list[ChunkSearchHit] = Field(description="Search results")
    next_cursor: str | None = Field(
        default=None, description="Pagination cursor (unused, always null)"
    )
    has_more: bool = Field(default=False, description="Whether more results exist (unused)")
