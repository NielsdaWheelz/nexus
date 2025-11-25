"""FastAPI application factory and entry point."""

import logging
import uuid
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Returns:
        Configured FastAPI instance.
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add trace ID middleware
    @app.middleware("http")
    async def add_trace_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Add trace ID to all requests and responses."""
        trace_id = f"req_{uuid.uuid4().hex}"
        request.state.trace_id = trace_id

        # Call the next middleware/handler
        response: Response = await call_next(request)

        # Add trace ID header to response
        response.headers["X-Trace-Id"] = trace_id

        # Log request
        logger.info(
            f"method={request.method} path={request.url.path} "
            f"status={response.status_code} trace_id={trace_id}"
        )

        return response

    # Include routers
    app.include_router(health.router)

    return app


# Create app instance for uvicorn
app = create_app()
