"""Request logging middleware for structured request tracking.

This middleware logs all requests with structured JSON output including:
- HTTP method and path
- Response status code
- Request duration
- Trace ID for correlation
- User ID (if authenticated, null for now)

Each request produces exactly one log line after the response is complete.
"""

import logging
import time
from typing import Awaitable, Callable

from fastapi import Request, Response

logger = logging.getLogger(__name__)


async def request_logging_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log HTTP requests with structured JSON output.

    Logs one JSON line per request after response completes, including:
    - method: HTTP method (GET, POST, etc.)
    - path: Request path
    - status: Response status code
    - duration_ms: Request processing time in milliseconds
    - trace_id: Request trace ID for correlation
    - user_id: Authenticated user ID (null if not authenticated)

    Args:
        request: FastAPI request
        call_next: Next middleware/handler in chain

    Returns:
        Response from next handler
    """
    # Record start time
    start_time = time.monotonic()

    # Get trace ID from request state (set by trace ID middleware)
    trace_id = getattr(request.state, "trace_id", "unknown")

    # Get user ID if authenticated (will be null for unauthenticated requests)
    user_id = getattr(request.state, "user_id", None)

    # Call next handler
    response: Response = await call_next(request)

    # Calculate duration
    end_time = time.monotonic()
    duration_ms = int((end_time - start_time) * 1000)

    # Log request completion
    logger.info(
        "Request completed",
        extra={
            "event": "request_completed",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "trace_id": trace_id,
            "user_id": user_id,
        },
    )

    return response
