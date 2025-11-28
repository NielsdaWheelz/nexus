"""FastAPI dependencies for authentication and rate limiting.

This module provides:
- Bearer token extraction from Authorization header
- JWT verification dependency
- User sync/creation on first authenticated request
- Request state population with user_id for logging
- Rate limiting dependencies for authenticated and anonymous traffic
"""

import logging
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import RateLimitScope, check_rate_limit
from app.db.session import get_session
from app.models.user import User

from .jwt import verify_clerk_jwt

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """FastAPI dependency to get authenticated user.

    Steps:
    1. Extract Bearer token from Authorization header
    2. Verify JWT using Clerk JWKS
    3. Extract external_user_id from 'sub' claim
    4. Query user by external_user_id
    5. If not found, create new user row
    6. Attach user_id to request.state for logging
    7. Return ORM user instance

    Args:
        request: FastAPI request object
        session: Database session (injected via dependency)
        authorization: Authorization header value

    Returns:
        Authenticated User ORM instance

    Raises:
        AppError: If authorization header missing/malformed or JWT verification fails (401)
    """
    # Extract token from Authorization header
    if not authorization:
        logger.warning("Missing Authorization header")
        raise AppError(
            code=ErrorCode.AUTH_REQUIRED,
            http_status=401,
            message="Missing authentication token",
        )

    # Parse "Bearer <token>"
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning(f"Malformed Authorization header: {parts[0] if parts else 'empty'}")
        raise AppError(
            code=ErrorCode.AUTH_REQUIRED,
            http_status=401,
            message="Invalid authentication header format",
        )

    token = parts[1]

    # Verify JWT
    decoded = await verify_clerk_jwt(token)

    # Extract external user ID from 'sub' claim
    external_user_id = decoded["sub"]

    # Query for existing user
    user = session.query(User).filter(User.external_user_id == external_user_id).first()

    if user is None:
        # Create new user
        logger.info(f"Creating new user with external_user_id={external_user_id}")
        user = User(
            external_user_id=external_user_id,
            email=decoded.get("email") or f"{external_user_id}@clerk.local",
        )
        session.add(user)
        session.flush()  # Flush to generate ID, commit happens in get_session()
        session.refresh(user)

    # Attach user_id to request state for logging middleware
    request.state.user_id = str(user.id)

    logger.debug(f"Authenticated user: {user.id}")
    return user


async def rate_limit_authenticated(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Rate limit dependency for authenticated endpoints.

    This dependency applies GLOBAL_USER rate limiting (per-user limit).
    It should be used on endpoints that require authentication.

    The rate limit key is the user ID. If exceeded, raises AppError with
    429 status and RATE_LIMITED error code.

    Args:
        current_user: Authenticated user from dependency

    Returns:
        Authenticated user (same as input)

    Raises:
        AppError: If rate limit exceeded (HTTP 429)
    """
    # Apply rate limiting using the user's ID as the key
    check_rate_limit(RateLimitScope.GLOBAL_USER, str(current_user.id))
    return current_user


async def rate_limit_anonymous(request: Request) -> None:
    """Rate limit dependency for anonymous (unauthenticated) endpoints.

    This dependency applies GLOBAL_ANON rate limiting (per-IP limit).
    It should be used on endpoints that don't require authentication.

    The rate limit key is the client IP address. If exceeded, raises AppError
    with 429 status and RATE_LIMITED error code.

    Args:
        request: FastAPI request object

    Raises:
        AppError: If rate limit exceeded (HTTP 429)
    """
    # Extract client IP from request
    # In development/local, client.host may be None, so we default to "localhost"
    client_ip = request.client.host if request.client else "localhost"

    # Apply rate limiting using the client IP as the key
    check_rate_limit(RateLimitScope.GLOBAL_ANON, client_ip)
