"""Tests for embeddings schema (pgvector column and index)."""

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session


class TestEmbeddingsSchema:
    """Validate pgvector schema additions."""

    def test_content_chunks_embedding_column_exists(self, db_session: Session) -> None:
        """Verify embedding column exists on content_chunks with correct type."""
        inspector = inspect(db_session.bind)
        columns = {col["name"]: col for col in inspector.get_columns("content_chunks")}

        assert "embedding" in columns, "embedding column should exist on content_chunks"

        embedding_col = columns["embedding"]
        assert embedding_col["nullable"] is True, "embedding column should be nullable"

    def test_content_chunks_embedding_index_exists(self, db_session: Session) -> None:
        """Verify IVFFlat cosine index exists on content_chunks.embedding."""
        inspector = inspect(db_session.bind)
        indexes = inspector.get_indexes("content_chunks")

        # Look for the embedding cosine index
        embedding_index = None
        for idx in indexes:
            if "embedding" in idx.get("column_names", []):
                embedding_index = idx
                break

        assert embedding_index is not None, "IVFFlat index should exist on content_chunks.embedding"
        assert embedding_index["name"] == "content_chunks_embedding_cosine_idx"

    def test_content_chunks_embedding_index_is_ivfflat(self, db_session: Session) -> None:
        """Verify the index uses IVFFlat algorithm with vector_cosine_ops."""
        # Query pg_indexes to check index definition
        result = db_session.execute(
            text(
                """
                SELECT indexdef FROM pg_indexes
                WHERE tablename = 'content_chunks'
                AND indexname = 'content_chunks_embedding_cosine_idx';
                """
            )
        ).scalar()

        assert result is not None, "Index definition should be found in pg_indexes"
        assert "ivfflat" in result.lower(), "Index should use ivfflat algorithm"
        assert "vector_cosine_ops" in result.lower(), "Index should use vector_cosine_ops"

    def test_pgvector_extension_exists(self, db_session: Session) -> None:
        """Verify pgvector extension is installed."""
        result = db_session.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector');")
        ).scalar()

        assert result is True, "pgvector extension should be installed"

    def test_vector_type_works(self, db_session: Session) -> None:
        """Verify vector type can be used in queries."""
        # Try to select from a table with vector column
        result = db_session.execute(
            text("SELECT COUNT(*) FROM content_chunks WHERE embedding IS NOT NULL;")
        ).scalar()

        assert result is not None, "Should be able to query embedding column"
        assert isinstance(result, int), "Query should return an integer count"
