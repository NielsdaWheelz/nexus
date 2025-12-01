"""Document content chunking algorithm and service.

This module implements deterministic chunking of document canonical text:
- chunk_canonical_text: Pure function that splits text into ChunkSpan objects
- run_chunk_document: Service function that applies chunking and stores chunks

Spec reference:
- spec/chunking.md (chunking algorithm and invariants)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chunk import ContentChunk
from app.models.document import Document

logger = logging.getLogger(__name__)

# Chunking constants
MAX_CHUNK_CHARS = 1000
CHUNK_VERSION_DOCUMENT = "doc_v1_chars_1000"


@dataclass(frozen=True)
class ChunkSpan:
    """Represents a single chunk extracted from canonical text.

    Fields:
    - start: Byte offset (start position in UTF-8 encoded text)
    - end: Byte offset (end position in UTF-8 encoded text)
    - text: The actual chunk text
    - metadata: Dict with chunk metadata (index, approx_char_length, approx_paragraphs)
    """

    start: int
    end: int
    text: str
    metadata: dict[str, Any]


def chunk_canonical_text(canonical_text: str) -> list[ChunkSpan]:
    """Split canonical text into chunks using paragraph-aware greedy algorithm.

    Algorithm:
    1. Split text into paragraphs (separated by double newlines or more)
    2. Greedily accumulate paragraphs into chunks, respecting MAX_CHUNK_CHARS
    3. Each chunk stores byte offsets (UTF-8) and computed metadata

    Args:
        canonical_text: The full canonical text to chunk

    Returns:
        List of ChunkSpan objects, sorted by start position

    Invariants:
    - All spans are non-overlapping: spans[i].end <= spans[i+1].start
    - All spans are sorted by start position
    - Spans cover the full text with minimal gaps (only at paragraph boundaries)
    - Same input always produces identical output (deterministic)
    """
    import re

    if not canonical_text:
        return []

    # Split paragraphs by double newlines (or more) and track their positions
    # Para pattern matches "\n\n" or more newlines
    para_pattern = re.compile(r"\n\n+")

    # Extract paragraphs with their text positions in the original string
    paragraphs: list[tuple[int, int, str]] = []  # (char_start, char_end, text)
    last_end = 0
    for match in para_pattern.finditer(canonical_text):
        para_text = canonical_text[last_end : match.start()]
        if para_text:
            paragraphs.append((last_end, match.start(), para_text))
        last_end = match.end()

    # Handle remaining text after last separator
    if last_end < len(canonical_text):
        para_text = canonical_text[last_end:]
        if para_text:
            paragraphs.append((last_end, len(canonical_text), para_text))

    # Convert character positions to byte offsets
    # For each paragraph, compute its byte offset in UTF-8
    para_byte_positions: list[tuple[int, int, str]] = []
    current_byte_pos = 0

    for char_start, char_end, para_text in paragraphs:
        # Compute byte offset by encoding from start of text to char_start
        para_start_byte = len(canonical_text[:char_start].encode("utf-8"))
        para_end_byte = para_start_byte + len(para_text.encode("utf-8"))
        para_byte_positions.append((para_start_byte, para_end_byte, para_text))

    # Build chunks greedily
    # Track what we actually include from the canonical text
    spans: list[ChunkSpan] = []
    chunk_start_byte = None
    chunk_end_byte = None
    chunk_buffer = ""  # Track the actual text we're accumulating
    chunk_index = 0

    for para_start_byte, para_end_byte, para_text in para_byte_positions:
        # Count characters (not bytes) for size check
        potential_size = len(chunk_buffer) + len(para_text)

        if chunk_buffer and potential_size > MAX_CHUNK_CHARS:
            # Emit current chunk and start new one
            chunk_text = chunk_buffer.rstrip()
            chunk_span = ChunkSpan(
                start=chunk_start_byte,
                end=chunk_end_byte,
                text=chunk_text,
                metadata={
                    "index": chunk_index,
                    "approx_char_length": len(chunk_text),
                    "approx_paragraphs": chunk_buffer.count("\n\n") + 1,
                },
            )
            spans.append(chunk_span)
            chunk_buffer = para_text
            chunk_start_byte = para_start_byte
            chunk_end_byte = para_end_byte
            chunk_index += 1
        else:
            if chunk_start_byte is None:
                chunk_start_byte = para_start_byte
            # Track the end position: we'll include up to para_end_byte
            chunk_end_byte = para_end_byte
            # Build the actual text: add separator if not first
            chunk_buffer += "\n\n" + para_text if chunk_buffer else para_text

    # Emit final chunk
    if chunk_buffer:
        chunk_text = chunk_buffer.rstrip()
        chunk_span = ChunkSpan(
            start=chunk_start_byte,
            end=chunk_end_byte,
            text=chunk_text,
            metadata={
                "index": chunk_index,
                "approx_char_length": len(chunk_text),
                "approx_paragraphs": chunk_buffer.count("\n\n") + 1,
            },
        )
        spans.append(chunk_span)

    return spans


def run_chunk_document(session: Session, document_id: UUID) -> int:
    """Apply chunking algorithm to a document and store chunks.

    Chunking is an independent, idempotent operation that runs asynchronously
    after successful document ingestion. If chunking fails, the document remains
    "ready" (ingestion succeeded), and the Celery task will retry.

    Design note: Document status is NOT modified by chunking. Chunking failure
    does not affect document readiness, only chunk availability. Future highlight
    remap operations will re-chunk as needed.

    Remap-safe: This function can be called independently from a remap pipeline.
    When canonical_text changes (detected via chunk_version mismatch or explicit call),
    old chunks are deleted and new ones created atomically. Safe to call multiple
    times, from different call sites, in parallel (within same transaction context).

    Idempotent: re-running on unchanged canonical_text produces no duplicates.
    If canonical_text changes, old chunks are replaced.

    Args:
        session: SQLAlchemy Session
        document_id: Document UUID

    Returns:
        Number of chunks created

    Raises:
        ValueError: If document not found
        ValueError: If document status is not "ready"
        ValueError: If canonical_text is empty
    """
    # Load document with lock
    stmt = select(Document).where(Document.id == document_id).with_for_update()
    doc = session.execute(stmt).scalar_one_or_none()

    if not doc:
        raise ValueError(f"Document not found: {document_id}")

    # Guard on status
    if doc.status != "ready":
        raise ValueError(
            f"Cannot chunk document {document_id}: status is {doc.status}, expected 'ready'"
        )

    # Guard on canonical_text
    if not doc.canonical_text:
        raise ValueError(f"Cannot chunk document {document_id}: canonical_text is empty")

    # Idempotency check: if already chunked with current version, skip
    if doc.chunk_version == CHUNK_VERSION_DOCUMENT:
        existing_chunks = (
            session.execute(
                select(ContentChunk).where(
                    ContentChunk.media_type == "document",
                    ContentChunk.media_id == document_id,
                )
            )
            .scalars()
            .all()
        )
        if existing_chunks:
            logger.info(
                f"Document {document_id} already chunked with version {CHUNK_VERSION_DOCUMENT}, "
                f"skipping (found {len(existing_chunks)} existing chunks)"
            )
            return 0

    # Delete old chunks for this document
    session.execute(
        ContentChunk.__table__.delete().where(
            (ContentChunk.media_type == "document") & (ContentChunk.media_id == document_id)
        )
    )
    session.flush()

    # Generate new chunks
    spans = chunk_canonical_text(doc.canonical_text)
    chunks = []
    for span in spans:
        chunk = ContentChunk(
            media_type="document",
            media_id=document_id,
            chunk_version=CHUNK_VERSION_DOCUMENT,
            embedding_model=None,  # No embeddings yet
            text_start=span.start,
            text_end=span.end,
            text=span.text,
            chunk_metadata=span.metadata,
        )
        chunks.append(chunk)
        session.add(chunk)

    # Update document
    doc.chunk_version = CHUNK_VERSION_DOCUMENT
    session.flush()

    logger.info(
        f"Successfully chunked document {document_id} into {len(chunks)} chunks "
        f"(version {CHUNK_VERSION_DOCUMENT})"
    )

    return len(chunks)
