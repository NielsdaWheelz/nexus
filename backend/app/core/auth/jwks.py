"""JWKS fetching and caching for Clerk JWT verification.

This module provides:
- Async JWKS fetching from Clerk OIDC endpoint
- In-memory caching with TTL
- Automatic refresh on verification failure
- Error handling with retries
"""

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

# Cache for JWKS response
_jwks_cache: dict[str, Any] = {
    "data": None,
    "expires_at": 0,
}
_cache_lock = asyncio.Lock()


async def fetch_jwks() -> dict[str, Any]:
    """Fetch and cache Clerk JWKS endpoint.

    Fetches JWKS from settings.CLERK_JWKS_URL and caches result for 1 hour (3600 seconds).
    On network error, raises AppError with UNAVAILABLE code and 503 status.
    Uses in-memory cache with timestamp-based TTL.

    Returns:
        JWKS response dict with 'keys' array.

    Raises:
        AppError: If JWKS endpoint is unreachable or misconfigured (503 UNAVAILABLE).
    """
    settings = get_settings()

    # Check if cache is still valid
    current_time = time.time()
    if _jwks_cache["data"] is not None and _jwks_cache["expires_at"] > current_time:
        logger.debug("Using cached JWKS")
        return _jwks_cache["data"]

    # Use lock to prevent multiple concurrent fetches
    async with _cache_lock:
        # Check again in case another task just updated it
        current_time = time.time()
        if _jwks_cache["data"] is not None and _jwks_cache["expires_at"] > current_time:
            logger.debug("Using cached JWKS (after lock acquired)")
            return _jwks_cache["data"]

        # Fetch from Clerk
        try:
            logger.debug(f"Fetching JWKS from {settings.CLERK_JWKS_URL}")
            async with httpx.AsyncClient() as client:
                response = await client.get(settings.CLERK_JWKS_URL, timeout=10.0)
                response.raise_for_status()
                jwks_data = response.json()

                # Validate response structure
                if "keys" not in jwks_data:
                    logger.error("Invalid JWKS response: missing 'keys' field")
                    raise AppError(
                        code=ErrorCode.UNAVAILABLE,
                        http_status=503,
                        message="JWKS endpoint returned invalid response",
                    )

                # Cache for 1 hour
                _jwks_cache["data"] = jwks_data
                _jwks_cache["expires_at"] = current_time + 3600
                logger.info("JWKS fetched and cached successfully")

                return jwks_data

        except httpx.HTTPStatusError as e:
            logger.error(f"JWKS fetch failed with HTTP {e.response.status_code}: {e}")
            raise AppError(
                code=ErrorCode.UNAVAILABLE,
                http_status=503,
                message="Clerk JWKS endpoint unavailable",
            ) from e
        except (httpx.RequestError, asyncio.TimeoutError) as e:
            logger.error(f"JWKS fetch network error: {e}")
            raise AppError(
                code=ErrorCode.UNAVAILABLE,
                http_status=503,
                message="Unable to reach Clerk JWKS endpoint",
            ) from e
        except ValueError as e:
            logger.error(f"JWKS response parsing error: {e}")
            raise AppError(
                code=ErrorCode.UNAVAILABLE,
                http_status=503,
                message="JWKS endpoint returned invalid JSON",
            ) from e


def invalidate_jwks_cache() -> None:
    """Invalidate JWKS cache to force refresh on next fetch.

    Used after signature verification failure to trigger JWKS refresh.
    """
    logger.debug("Invalidating JWKS cache")
    _jwks_cache["expires_at"] = 0
    _jwks_cache["data"] = None
