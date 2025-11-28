"""Common response schemas for all API endpoints.

This module defines canonical response envelopes used consistently across all API responses:
- Success responses: {"data": <resource-or-list>}
- Error responses: {"error": {code, message, details, trace_id}} (handled by error_handlers.py)

Spec reference:
- spec/api_contracts.md (response shape consistency)
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class DataEnvelope(BaseModel, Generic[T]):
    """Generic success response envelope wrapping any response data.

    All successful API responses must be wrapped in this envelope.

    Attributes:
        data: The actual response data (resource, list, or custom object)

    Example:
        {
            "data": {
                "id": "usr_...",
                "email": "...",
                ...
            }
        }
    """

    data: T = Field(description="Response data (resource, list, or object)")


class HealthStatus(BaseModel):
    """Health check response data.

    Attributes:
        ok: Whether the service is healthy
        status: Human-readable status message
    """

    ok: bool = Field(description="Service health status")
    status: str = Field(description="Status message (e.g., 'healthy')")
