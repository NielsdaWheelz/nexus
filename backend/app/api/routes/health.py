"""Health check endpoint.

Provides:
- GET /health: Public health check (no auth, not rate-limited)
"""

from fastapi import APIRouter, Response

from app.schemas.common import DataEnvelope, HealthStatus

router = APIRouter()


@router.get("/health", response_model=DataEnvelope[HealthStatus])
def health(response: Response) -> DataEnvelope[HealthStatus]:
    """Health check endpoint.

    Returns 200 OK without authentication and is NOT rate-limited.
    This endpoint is always available for health monitoring.

    Returns:
        DataEnvelope wrapping HealthStatus with ok=True and status="healthy"
    """
    return DataEnvelope(data=HealthStatus(ok=True, status="healthy"))
