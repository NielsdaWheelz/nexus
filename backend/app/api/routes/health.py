"""Health check endpoint.

Provides:
- GET /health: Public health check (no auth, not rate-limited)
"""

from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/health")
def health(response: Response) -> dict[str, bool | str]:
    """Health check endpoint.

    Returns 200 OK without authentication and is NOT rate-limited.
    This endpoint is always available for health monitoring.

    Returns:
        JSON response with health status
    """
    return {"ok": True, "status": "healthy"}
