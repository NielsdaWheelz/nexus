"""Authentication routes for Clerk-protected endpoints.

This module provides:
- GET /auth/me: Authenticated endpoint returning current user profile (rate limited)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.auth.deps import rate_limit_authenticated
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_current_user_profile(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
) -> dict[str, str]:
    """Get current authenticated user profile.

    Returns user information for the authenticated user.
    This endpoint is rate-limited per user (GLOBAL_USER scope).

    Args:
        current_user: Authenticated user from rate-limited dependency

    Returns:
        User profile with typed ID and metadata
    """
    return {
        "id": f"usr_{current_user.id}",
        "email": current_user.email,
        "display_name": current_user.email.split("@")[0],
        "created_at": current_user.created_at.isoformat(),
        "updated_at": current_user.updated_at.isoformat(),
    }
