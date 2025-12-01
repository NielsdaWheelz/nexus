"""OpenAI embeddings abstraction layer for PR 6.3.

Provides a simple interface for generating embeddings via OpenAI API.
Handles API key validation, batching, and error propagation.
"""

from collections.abc import Sequence
from typing import Protocol

from openai import APIError, OpenAI

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode, ExternalDependencyError


class EmbeddingClient(Protocol):
    """Protocol for embedding clients.

    Implementations must provide a single method to embed texts.
    """

    def embed_texts(self, texts: Sequence[str], model: str) -> list[list[float]]:
        """Embed a sequence of texts.

        Args:
            texts: List of text strings to embed
            model: Model name (e.g., "text-embedding-3-small")

        Returns:
            List of embedding vectors (one per input text)

        Raises:
            AppError: If API key is missing or API call fails
        """
        ...


class OpenAIEmbeddingClient:
    """OpenAI embeddings client using the official Python SDK."""

    def __init__(self, api_key: str | None = None):
        """Initialize OpenAI client.

        Args:
            api_key: Optional OpenAI API key. If not provided, uses OPENAI_API_KEY from settings.

        Raises:
            AppError: If API key is missing
        """
        if api_key is None:
            settings = get_settings()
            api_key = settings.OPENAI_API_KEY

        if not api_key or api_key.strip() == "":
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                http_status=500,
                message="OpenAI API key is not configured",
                details={"reason": "OPENAI_API_KEY not set in environment"},
            )

        self.client = OpenAI(api_key=api_key)

    def embed_texts(self, texts: Sequence[str], model: str) -> list[list[float]]:
        """Embed texts using OpenAI API.

        Args:
            texts: List of texts to embed
            model: Model name (e.g., "text-embedding-3-small")

        Returns:
            List of embedding vectors

        Raises:
            AppError: If API call fails (API error, network issue, etc.)
        """
        if not texts:
            return []

        try:
            response = self.client.embeddings.create(
                input=list(texts),
                model=model,
            )

            # Extract embeddings from response
            # OpenAI returns embeddings in the same order as input
            embeddings = [item.embedding for item in response.data]
            return embeddings

        except APIError as e:
            # OpenAI API error (quota, rate limit, auth, etc.)
            # These should be retried, so use ExternalDependencyError
            raise ExternalDependencyError(
                message="Embeddings API error",
                details={"reason": str(e)},
            ) from e
        except Exception as e:
            # Other errors (network, parsing, etc.)
            # These are typically temporary and should be retried
            raise ExternalDependencyError(
                message="Failed to generate embeddings",
                details={"reason": str(e)},
            ) from e


def get_default_embedding_client() -> EmbeddingClient:
    """Get the default embedding client.

    Returns:
        Initialized OpenAI embedding client

    Raises:
        AppError: If API key is not configured
    """
    return OpenAIEmbeddingClient()


def embed_texts_with_default_client(
    texts: Sequence[str],
    model: str,
) -> list[list[float]]:
    """Embed texts using the default client.

    Convenience function for services that don't need to manage client lifecycle.

    Args:
        texts: List of texts to embed
        model: Model name (e.g., "text-embedding-3-small")

    Returns:
        List of embedding vectors

    Raises:
        AppError: If embedding fails
    """
    client = get_default_embedding_client()
    return client.embed_texts(texts, model)
