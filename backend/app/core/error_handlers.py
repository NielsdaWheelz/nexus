"""Global exception handlers for FastAPI.

This module provides exception handlers for all error types, ensuring consistent
error envelope generation and response formatting across all endpoints.

All handlers:
- Return canonical error envelope with code, message, details, and trace_id
- Include HTTP status code matching error type
- Log errors with appropriate level (WARNING for client errors, ERROR for server errors)
- Preserve trace_id for request correlation
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


def create_error_response(
    code: ErrorCode | str,
    message: str,
    http_status: int,
    trace_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create canonical error envelope response.

    Args:
        code: Error code from ErrorCode enum
        message: Human-readable error message
        http_status: HTTP status code
        trace_id: Request trace ID for correlation
        details: Optional structured error details

    Returns:
        Error envelope dict with canonical shape
    """
    return {
        "error": {
            "code": code if isinstance(code, str) else code.value,
            "message": message,
            "details": details or None,
            "trace_id": trace_id,
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers with FastAPI app.

    This function should be called during app initialization to wire error handlers.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Handle AppError exceptions (application errors).

        Logs at WARNING level for client errors (4xx) or ERROR for server errors (5xx).
        Returns canonical error envelope with code, message, details, and trace_id.

        Args:
            request: FastAPI request
            exc: AppError exception

        Returns:
            JSONResponse with error envelope and appropriate HTTP status
        """
        trace_id = getattr(request.state, "trace_id", "unknown")

        log_level = logging.WARNING if exc.http_status < 500 else logging.ERROR
        logger.log(
            log_level,
            f"AppError: code={exc.code.value} status={exc.http_status} message={exc.message} trace_id={trace_id}",
            extra={"trace_id": trace_id, "error_code": exc.code.value},
        )

        response_body = create_error_response(
            code=exc.code,
            message=exc.message,
            http_status=exc.http_status,
            trace_id=trace_id,
            details=exc.details if exc.details else None,
        )

        return JSONResponse(status_code=exc.http_status, content=response_body)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle FastAPI validation errors (RequestValidationError).

        Maps validation errors to VALIDATION_ERROR code with structured field-level details.
        Returns 422 Unprocessable Entity.

        Args:
            request: FastAPI request
            exc: RequestValidationError exception

        Returns:
            JSONResponse with error envelope and 422 status
        """
        trace_id = getattr(request.state, "trace_id", "unknown")

        # Extract field-level error messages
        field_errors: dict[str, list[str]] = {}
        for error in exc.errors():
            field_path = ".".join(str(loc) for loc in error["loc"][1:])
            if field_path not in field_errors:
                field_errors[field_path] = []
            field_errors[field_path].append(error["msg"])

        logger.warning(
            f"Validation error: fields={list(field_errors.keys())} trace_id={trace_id}",
            extra={"trace_id": trace_id, "error_code": ErrorCode.VALIDATION_ERROR.value},
        )

        response_body = create_error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            trace_id=trace_id,
            details={"fields": field_errors} if field_errors else None,
        )

        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=response_body)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle Starlette HTTPException.

        Maps HTTP exception status codes to canonical error codes using the mapping rules:
        - 400 → BAD_REQUEST
        - 404 → NOT_FOUND
        - 409 → CONFLICT
        - 429 → RATE_LIMITED
        - 500 → INTERNAL_ERROR
        - 503 → UNAVAILABLE
        - etc.

        Args:
            request: FastAPI request
            exc: HTTPException from Starlette

        Returns:
            JSONResponse with error envelope and original HTTP status
        """
        trace_id = getattr(request.state, "trace_id", "unknown")

        # Map HTTP status codes to canonical error codes
        status_code_map = {
            400: ErrorCode.BAD_REQUEST,
            401: ErrorCode.AUTH_REQUIRED,
            403: ErrorCode.PERMISSION_DENIED,
            404: ErrorCode.NOT_FOUND,
            409: ErrorCode.CONFLICT,
            422: ErrorCode.VALIDATION_ERROR,
            429: ErrorCode.RATE_LIMITED,
            500: ErrorCode.INTERNAL_ERROR,
            503: ErrorCode.UNAVAILABLE,
        }

        error_code = status_code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

        logger.warning(
            f"HTTPException: code={error_code.value} status={exc.status_code} detail={exc.detail} trace_id={trace_id}",
            extra={"trace_id": trace_id, "error_code": error_code.value},
        )

        response_body = create_error_response(
            code=error_code,
            message=exc.detail or "An error occurred",
            http_status=exc.status_code,
            trace_id=trace_id,
            details=None,
        )

        return JSONResponse(status_code=exc.status_code, content=response_body)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all handler for unexpected exceptions.

        Maps all unhandled exceptions to INTERNAL_ERROR with 500 status.
        Does NOT leak internal error details to client (logged server-side only).
        Logs full traceback for debugging.

        Args:
            request: FastAPI request
            exc: Unexpected exception

        Returns:
            JSONResponse with error envelope and 500 status
        """
        trace_id = getattr(request.state, "trace_id", "unknown")

        logger.exception(
            f"Unhandled exception: type={type(exc).__name__} trace_id={trace_id}",
            extra={"trace_id": trace_id, "error_code": ErrorCode.INTERNAL_ERROR.value},
        )

        response_body = create_error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected error occurred",
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            trace_id=trace_id,
            details=None,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=response_body
        )
