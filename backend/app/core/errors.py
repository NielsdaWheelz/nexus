"""Centralized error code registry and exception classes.

This module defines canonical error codes and base exception classes used throughout
the application. All errors are mapped to HTTP status codes and canonical error envelopes.

Error codes are organized by category:
- AUTH: Authentication and authorization errors
- VALIDATION: Request validation errors
- NOT_FOUND: Resource not found errors
- RATE_LIMIT: Rate limiting errors
- INTERNAL: Unexpected server errors
"""

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Canonical error code registry.

    All error responses use one of these codes. Codes are stable across API versions.
    """

    # ========================================================================
    # AUTHENTICATION & AUTHORIZATION (40x)
    # ========================================================================

    AUTH_REQUIRED = "AUTH_REQUIRED"
    """Missing, malformed, expired, or invalid JWT."""

    AUTH_INVALID = "AUTH_INVALID"
    """JWT token is structurally invalid or from untrusted issuer."""

    PERMISSION_DENIED = "PERMISSION_DENIED"
    """Authenticated but not permitted (ACL violation, insufficient plan)."""

    # ========================================================================
    # VALIDATION (400, 422)
    # ========================================================================

    VALIDATION_ERROR = "VALIDATION_ERROR"
    """Request payload constraints violated (type mismatch, missing required field)."""

    BAD_REQUEST = "BAD_REQUEST"
    """Generic bad request (cannot parse, invalid format)."""

    CONFLICT = "CONFLICT"
    """Resource conflict (duplicate, state violation)."""

    # ========================================================================
    # NOT FOUND (404)
    # ========================================================================

    NOT_FOUND = "NOT_FOUND"
    """Resource does not exist."""

    # ========================================================================
    # RATE LIMITING (429)
    # ========================================================================

    RATE_LIMITED = "RATE_LIMITED"
    """API rate limit exceeded."""

    # ========================================================================
    # INTERNAL SERVER ERRORS (500, 503)
    # ========================================================================

    INTERNAL_ERROR = "INTERNAL_ERROR"
    """Unexpected server error."""

    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    """Document content extraction failed (PDF/EPUB/HTML parsing, node helper, etc.)."""

    UNAVAILABLE = "UNAVAILABLE"
    """Service unavailable (LLM API down, database unreachable, etc.)."""


class AppError(Exception):
    """Base exception class for all application errors.

    All errors raised in the application should inherit from this class.
    This ensures consistent error envelope generation and logging.

    Attributes:
        code: Canonical error code from ErrorCode enum
        http_status: HTTP status code (400, 401, 403, 404, 422, 429, 500, 503)
        message: Human-readable error message (≤140 chars, shown to client)
        details: Optional structured error details (shown to client)
    """

    def __init__(
        self,
        code: ErrorCode | str,
        http_status: int,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        """Initialize AppError.

        Args:
            code: Error code from ErrorCode enum or string
            http_status: HTTP status code (400, 401, 403, 404, 422, 429, 500, 503)
            message: Human-readable error message
            details: Optional structured error details (shown to client)
        """
        if isinstance(code, str):
            code = ErrorCode(code)

        self.code = code
        self.http_status = http_status
        self.message = message
        self.details = details or {}

        super().__init__(self.message)


# ============================================================================
# CONVENIENCE SUBCLASSES
# ============================================================================


class AuthError(AppError):
    """Authentication error (401 Unauthorized)."""

    def __init__(
        self, message: str = "Authentication required", details: dict[str, Any] | None = None
    ):
        """Initialize AuthError with 401 status.

        Args:
            message: Human-readable error message
            details: Optional structured error details
        """
        super().__init__(
            code=ErrorCode.AUTH_REQUIRED,
            http_status=401,
            message=message,
            details=details,
        )


class PermissionDeniedError(AppError):
    """Permission denied error (403 Forbidden)."""

    def __init__(self, message: str = "Permission denied", details: dict[str, Any] | None = None):
        """Initialize PermissionDeniedError with 403 status.

        Args:
            message: Human-readable error message
            details: Optional structured error details
        """
        super().__init__(
            code=ErrorCode.PERMISSION_DENIED,
            http_status=403,
            message=message,
            details=details,
        )


class NotFoundError(AppError):
    """Resource not found error (404 Not Found)."""

    def __init__(self, message: str = "Resource not found", details: dict[str, Any] | None = None):
        """Initialize NotFoundError with 404 status.

        Args:
            message: Human-readable error message
            details: Optional structured error details
        """
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            http_status=404,
            message=message,
            details=details,
        )


class ValidationAppError(AppError):
    """Validation error (422 Unprocessable Entity).

    All semantic input validation failures return 422, per RFC 4918.
    This includes field-level validation, format validation, constraint violations, etc.
    """

    def __init__(
        self,
        message: str = "Validation failed",
        details: dict[str, Any] | None = None,
        http_status: int = 422,
    ):
        """Initialize ValidationAppError with validation error code.

        Args:
            message: Human-readable error message
            details: Optional structured error details
            http_status: HTTP status code (default 422 per RFC 4918)
        """
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            http_status=http_status,
            message=message,
            details=details,
        )


class ExternalDependencyError(AppError):
    """External dependency error (503 Service Unavailable).

    Used for errors from external APIs, services, or infrastructure that should be retried.
    Celery task decorators can use this exception type for autoretry logic.
    """

    def __init__(
        self, message: str = "External service unavailable", details: dict[str, Any] | None = None
    ):
        """Initialize ExternalDependencyError with 503 status.

        Args:
            message: Human-readable error message
            details: Optional structured error details
        """
        super().__init__(
            code=ErrorCode.UNAVAILABLE,
            http_status=503,
            message=message,
            details=details,
        )
