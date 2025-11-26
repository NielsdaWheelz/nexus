"""Security headers middleware.

This middleware injects standard HTTP security headers into all responses.
Headers are applied to all responses including success, error, and health check.

Headers applied:
- X-Content-Type-Options: nosniff (prevent MIME sniffing)
- X-Frame-Options: DENY (prevent clickjacking)
- Referrer-Policy: strict-origin-when-cross-origin (privacy)
- X-XSS-Protection: 0 (disable XSS filter, modern browsers use CSP instead)
- Strict-Transport-Security: max-age=63072000; includeSubDomains; preload (HTTPS only)

Note: HSTS has max-age of 2 years (63072000 seconds) which is appropriate
for production. In development with HTTP, the header is benign and ignored
by browsers.
"""

from typing import Awaitable, Callable

from fastapi import Request, Response

# Callable is used in the type hint for call_next parameter
# Awaitable is used in the return type annotation for async functions
__all__ = ["security_headers_middleware"]


# Security headers to add to all responses
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "0",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
}


async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Add security headers to all responses.

    This middleware is applied after other middleware and handlers, ensuring
    that all responses (success, error, redirect) include security headers.

    The headers are set unconditionally and do not overwrite existing headers
    unless necessary for security.

    Args:
        request: FastAPI request object
        call_next: Next middleware/handler in chain

    Returns:
        Response with security headers added
    """
    # Call the next middleware/handler
    response: Response = await call_next(request)

    # Add security headers to response
    for header_name, header_value in SECURITY_HEADERS.items():
        response.headers[header_name] = header_value

    return response
