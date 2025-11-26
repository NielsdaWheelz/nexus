"""FastAPI application factory and entry point."""

import uuid
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import get_settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import request_logging_middleware

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI instance.
    """
    settings = get_settings()

    # Configure structured logging
    configure_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
    )

    # Add CORS middleware (must be first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add trace ID middleware (must be before request logging)
    @app.middleware("http")
    async def add_trace_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Add trace ID to all requests and responses.

        Trace IDs are generated server-side and propagated through:
        - Request state (for access in handlers)
        - Response headers (X-Trace-Id)
        - All log entries (for request tracing)
        """
        trace_id = f"req_{uuid.uuid4().hex}"
        request.state.trace_id = trace_id

        # Call the next middleware/handler
        response: Response = await call_next(request)

        # Add trace ID header to response
        response.headers["X-Trace-Id"] = trace_id

        return response

    # Add request logging middleware (must be after trace ID middleware)
    # Using app.middleware instead of add_middleware to ensure proper ordering
    @app.middleware("http")
    async def logging_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Request logging middleware wrapper."""
        return await request_logging_middleware(request, call_next)

    # Register global exception handlers
    # These must be registered after middleware to catch all exceptions
    register_error_handlers(app)

    # Include routers
    app.include_router(health.router)

    return app


# Create app instance for uvicorn
app = create_app()
