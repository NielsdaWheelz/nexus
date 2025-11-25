"""Health check endpoint."""

from fastapi import APIRouter, Response

router = APIRouter()


@router.get("/health")
def health(response: Response) -> dict[str, bool | str]:
    """Health check endpoint.

    Returns:
        JSON response with health status and trace ID header.
    """
    trace_id = getattr(response, "_trace_id", "")
    response.headers["X-Trace-Id"] = trace_id
    return {"ok": True, "status": "healthy"}
