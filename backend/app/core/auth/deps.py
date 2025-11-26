"""FastAPI dependencies for authentication.

This module provides:
- Bearer token extraction from Authorization header
- JWT verification dependency
- User sync/creation on first authenticated request
- Request state population with user_id for logging
"""

import logging
from typing import Annotated

from fastapi import Header, Request

from app.core.errors import AppError, ErrorCode
from app.db.session import get_session
from app.models.user import User

from .jwt import verify_clerk_jwt

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
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

    # Get database session and look up or create user
    session = get_session()
    try:
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
            session.commit()
            session.refresh(user)

        # Attach user_id to request state for logging middleware
        request.state.user_id = str(user.id)

        logger.debug(f"Authenticated user: {user.id}")
        return user

    finally:
        session.close()
