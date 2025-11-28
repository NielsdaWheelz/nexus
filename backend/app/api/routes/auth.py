"""Authentication routes for Clerk-protected endpoints.

This module provides:
- GET /auth/me: Authenticated endpoint returning current user profile (rate limited)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth.deps import rate_limit_authenticated
from app.models.user import User
from app.schemas.common import DataEnvelope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class UserProfile(BaseModel):
    """Current user profile response."""

    id: str = Field(description="Typed user ID (usr_<uuid>)")
    email: str = Field(description="User email address")
    display_name: str = Field(description="Display name (derived from email)")
    created_at: str = Field(description="UTC timestamp of account creation")
    updated_at: str = Field(description="UTC timestamp of last update")


@router.get("/me", response_model=DataEnvelope[UserProfile])
async def get_current_user_profile(
    current_user: Annotated[User, Depends(rate_limit_authenticated)],
) -> DataEnvelope[UserProfile]:
    """Get current authenticated user profile.

    Returns user information for the authenticated user.
    This endpoint is rate-limited per user (GLOBAL_USER scope).

    Args:
        current_user: Authenticated user from rate-limited dependency

    Returns:
        DataEnvelope wrapping UserProfile with typed ID and metadata
    """
    return DataEnvelope(
        data=UserProfile(
            id=f"usr_{current_user.id}",
            email=current_user.email,
            display_name=current_user.email.split("@")[0],
            created_at=current_user.created_at.isoformat(),
            updated_at=current_user.updated_at.isoformat(),
        )
    )
