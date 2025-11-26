"""In-process rate limiting with fixed-window implementation.

This module provides:
- Simple in-memory rate limiter with fixed-window counters
- Per-user (authenticated) and per-IP (anonymous) rate limiting
- Integration with FastAPI dependencies and error envelope
- Per-process only (not distributed across instances)

Rate limiting is implemented using fixed-window counters. For each (scope, key) pair,
we maintain a counter that resets at the start of each window.

Note: This implementation is per-process only. In multi-instance deployments,
we'll need a Redis-backed limiter in a future PR. The current approach is suitable
for Phase 1 single-instance deployments and development.
"""

import time
from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import AppError, ErrorCode


class RateLimitScope(StrEnum):
    """Rate limiting scope defines the dimension of rate limiting.

    GLOBAL_USER: Per-user rate limit for authenticated endpoints
    GLOBAL_ANON: Per-IP rate limit for unauthenticated endpoints
    """

    GLOBAL_USER = "global_user"
    GLOBAL_ANON = "global_anon"


@dataclass
class RateLimitConfig:
    """Configuration for a rate limit scope.

    Attributes:
        limit: Maximum number of requests allowed in window
        window_seconds: Size of the rate limit window in seconds
    """

    limit: int
    window_seconds: int


# Rate limit configuration for each scope
RATE_LIMITS: dict[RateLimitScope, RateLimitConfig] = {
    RateLimitScope.GLOBAL_USER: RateLimitConfig(
        limit=60,  # 60 requests per minute for authenticated users
        window_seconds=60,
    ),
    RateLimitScope.GLOBAL_ANON: RateLimitConfig(
        limit=30,  # 30 requests per minute for anonymous clients
        window_seconds=60,
    ),
}


@dataclass
class _WindowCounter:
    """In-memory counter for a rate limit window.

    Attributes:
        count: Number of requests in current window
        window_start: Timestamp when current window started
    """

    count: int
    window_start: float


# Module-level store for rate limit counters
# Structure: {(scope, key): _WindowCounter}
_rate_limit_store: dict[tuple[RateLimitScope, str], _WindowCounter] = {}


def check_rate_limit(scope: RateLimitScope, key: str) -> None:
    """Check rate limit and increment counter.

    Checks if the (scope, key) pair has exceeded its rate limit. If not,
    increments the counter. If exceeded, raises AppError with RATE_LIMITED code.

    Uses fixed-window implementation: each window is window_seconds long,
    starting at the epoch. When a new window begins, the counter resets.

    Args:
        scope: Rate limit scope (GLOBAL_USER or GLOBAL_ANON)
        key: Rate limit key (user_id for GLOBAL_USER, client_ip for GLOBAL_ANON)

    Raises:
        AppError: If rate limit exceeded (HTTP 429)
    """
    config = RATE_LIMITS[scope]
    current_time = time.time()
    cache_key = (scope, key)

    # Get or initialize counter for this (scope, key) pair
    counter = _rate_limit_store.get(cache_key)

    if counter is None:
        # First request in this window for this key
        _rate_limit_store[cache_key] = _WindowCounter(
            count=1,
            window_start=current_time,
        )
        return

    # Check if we're still in the same window
    window_elapsed = current_time - counter.window_start
    if window_elapsed >= config.window_seconds:
        # New window, reset counter
        _rate_limit_store[cache_key] = _WindowCounter(
            count=1,
            window_start=current_time,
        )
        return

    # Still in same window: check limit
    if counter.count >= config.limit:
        # Rate limit exceeded
        raise AppError(
            code=ErrorCode.RATE_LIMITED,
            http_status=429,
            message="Rate limit exceeded",
            details={
                "scope": scope.value,
                "limit": config.limit,
                "window_seconds": config.window_seconds,
            },
        )

    # Increment counter and allow request
    counter.count += 1


def clear_rate_limit_store() -> None:
    """Clear all rate limit counters.

    This is primarily useful for testing. In production, counters
    naturally expire when windows elapse.
    """
    global _rate_limit_store
    _rate_limit_store.clear()
