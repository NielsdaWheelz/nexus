"""Test-only endpoints for development and testing.

WARNING: This router should ONLY be mounted in development/test environments.
These endpoints are not part of the public API and may change without notice.

Provides:
- GET /test/rate-limited: Test endpoint for anonymous rate limiting
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth.deps import rate_limit_anonymous

router = APIRouter(prefix="/test", tags=["test"])


@router.get("/rate-limited")
async def test_rate_limited_endpoint(
    _: Annotated[None, Depends(rate_limit_anonymous)] = None,
) -> dict[str, str]:
    """Test endpoint for anonymous rate limiting.

    This endpoint is rate-limited per IP (GLOBAL_ANON scope).
    It's used for testing the rate limiting behavior without authentication.

    WARNING: Test-only endpoint. Should not be exposed in production.

    Returns:
        JSON object confirming the request was allowed
    """
    return {"message": "Request allowed (rate limit not exceeded)"}
