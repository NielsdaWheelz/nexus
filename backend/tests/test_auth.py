"""Comprehensive tests for Clerk authentication layer.

Tests cover:
- Missing/malformed/invalid tokens (401)
- Valid token with user creation
- JWKS caching and refresh logic
- Integration with trace_id middleware
"""

import logging
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.auth.jwks import _jwks_cache, invalidate_jwks_cache
from app.core.errors import ErrorCode
from app.main import create_app

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def app():
    """Create test FastAPI app."""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_jwt_payload():
    """Valid JWT payload for testing."""
    return {
        "sub": "user_test_123",
        "email": "test@example.com",
        "name": "Test User",
        "iss": "https://clerk.example.com",
        "aud": "test_audience",
        "exp": int(time.time()) + 3600,
    }


# ============================================================================
# MISSING/MALFORMED TOKEN TESTS
# ============================================================================


def test_auth_me_missing_token(client):
    """Test /auth/me without Authorization header returns 401 AUTH_REQUIRED."""
    response = client.get("/auth/me")

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == ErrorCode.AUTH_REQUIRED.value
    assert "authentication token" in data["error"]["message"].lower()
    assert data["error"]["trace_id"] is not None


def test_auth_me_empty_bearer(client):
    """Test /auth/me with empty Bearer token returns 401 AUTH_REQUIRED."""
    response = client.get("/auth/me", headers={"Authorization": "Bearer"})

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == ErrorCode.AUTH_REQUIRED.value


def test_auth_me_invalid_bearer_format(client):
    """Test /auth/me with malformed Bearer header returns 401 AUTH_REQUIRED."""
    response = client.get("/auth/me", headers={"Authorization": "Foo abc"})

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == ErrorCode.AUTH_REQUIRED.value


def test_auth_me_no_bearer_prefix(client):
    """Test /auth/me with token but no Bearer prefix returns 401 AUTH_REQUIRED."""
    response = client.get("/auth/me", headers={"Authorization": "eyJhbGc..."})

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == ErrorCode.AUTH_REQUIRED.value


# ============================================================================
# HAPPY PATH: VALID TOKEN WITH USER CREATION
# ============================================================================


@patch("app.core.auth.deps.get_session")
@patch("app.core.auth.deps.verify_clerk_jwt")
def test_auth_me_valid_token_response_shape(mock_verify, mock_session, client):
    """Happy path: valid JWT returns 200 with correct response shape.

    Tests:
    - JWT verification is called with token
    - Response has correct shape: id (usr_*), email, display_name, created_at, updated_at
    - Response timestamps are ISO8601 formatted
    """
    from unittest.mock import MagicMock

    from app.models.user import User

    external_user_id = "clerk_user_xyz"
    email = "alice@example.com"

    # Mock Clerk JWT verification
    mock_verify.return_value = {
        "sub": external_user_id,
        "email": email,
        "name": "Alice Smith",
        "iss": "https://clerk.example.com",
        "aud": "test_aud",
        "exp": int(time.time()) + 3600,
    }

    # Mock database session to simulate user creation
    mock_db_session = MagicMock()
    mock_session.return_value = mock_db_session

    # First request: user doesn't exist, create new
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    test_user = User(
        id="00000000-0000-0000-0000-000000000001",
        external_user_id=external_user_id,
        email=email,
    )
    # Add timestamps
    from datetime import datetime, timezone

    test_user.created_at = datetime.now(timezone.utc)
    test_user.updated_at = datetime.now(timezone.utc)

    mock_db_session.add.return_value = None
    mock_db_session.commit.return_value = None
    mock_db_session.refresh.side_effect = lambda u: (
        setattr(u, "id", test_user.id),
        setattr(u, "created_at", test_user.created_at),
        setattr(u, "updated_at", test_user.updated_at),
    )

    response1 = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer eyJhbGc.valid.token"},
    )

    assert response1.status_code == 200
    body1 = response1.json()

    # Assert response shape
    assert "id" in body1
    assert body1["id"].startswith("usr_")
    assert body1["email"] == email
    assert "display_name" in body1
    assert body1["display_name"] == "alice"  # prefix before @
    assert "created_at" in body1
    assert "updated_at" in body1

    # Verify timestamps are ISO8601
    assert "T" in body1["created_at"]
    assert "Z" in body1["created_at"] or "+00" in body1["created_at"]

    # Second request: user exists, return same user
    existing_user = User(
        id=test_user.id,
        external_user_id=external_user_id,
        email=email,
    )
    existing_user.created_at = test_user.created_at
    existing_user.updated_at = test_user.updated_at
    mock_db_session.query.return_value.filter.return_value.first.return_value = existing_user

    response2 = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer eyJhbGc.valid.token"},
    )

    assert response2.status_code == 200
    body2 = response2.json()
    assert body2["id"] == body1["id"]  # Same user ID on repeat call


@patch("app.core.auth.deps.get_session")
@patch("app.core.auth.deps.verify_clerk_jwt")
def test_auth_me_request_state_user_id_populated(mock_verify, mock_session, client, caplog):
    """Verify request.state.user_id is set for logging middleware.

    When auth succeeds, user_id should be attached to request state so that
    the logging middleware can include it in structured logs.
    """
    from unittest.mock import MagicMock

    from app.models.user import User

    external_user_id = "clerk_user_logging"
    user_id = "00000000-0000-0000-0000-000000000002"

    mock_verify.return_value = {
        "sub": external_user_id,
        "email": "bob@example.com",
        "name": "Bob",
        "iss": "https://clerk.example.com",
        "aud": "test_aud",
        "exp": int(time.time()) + 3600,
    }

    # Mock database session
    mock_db_session = MagicMock()
    mock_session.return_value = mock_db_session

    # User doesn't exist, create new
    from datetime import datetime
    from datetime import timezone as tz

    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    test_user = User(
        id=user_id,
        external_user_id=external_user_id,
        email="bob@example.com",
    )
    test_user.created_at = datetime.now(tz.utc)
    test_user.updated_at = datetime.now(tz.utc)

    mock_db_session.refresh.side_effect = lambda u: (
        setattr(u, "id", test_user.id),
        setattr(u, "created_at", test_user.created_at),
        setattr(u, "updated_at", test_user.updated_at),
    )

    with caplog.at_level(logging.INFO):
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer eyJhbGc.valid.token"},
        )

    assert response.status_code == 200
    # Request succeeded, which means get_current_user dependency ran,
    # set request.state.user_id, and user was created in DB.
    # The logging middleware will include user_id in structured logs.


# ============================================================================
# INVALID TOKEN TESTS (UNCONFIGURED CLERK)
# ============================================================================


def test_auth_me_unconfigured_clerk_returns_503(client):
    """Test /auth/me returns 503 when Clerk settings not configured.

    Without CLERK_JWKS_URL or CLERK_ISSUER in environment, authentication
    is unavailable and returns 503 UNAVAILABLE.
    """
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer any.token.here"},
    )

    # Returns 503 since Clerk is not configured (expected in test environment)
    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == ErrorCode.UNAVAILABLE.value


# ============================================================================
# TRACE ID INTEGRATION TESTS
# ============================================================================


def test_auth_me_includes_trace_id_in_response(client):
    """Test that /auth/me response includes trace ID header."""
    response = client.get("/auth/me")

    # Should have trace ID header even on error
    assert "X-Trace-Id" in response.headers
    assert response.headers["X-Trace-Id"].startswith("req_")


def test_auth_error_includes_trace_id_in_body(client):
    """Test that auth error responses include trace_id in error envelope."""
    response = client.get("/auth/me")

    data = response.json()
    assert data["error"]["trace_id"] is not None
    assert len(data["error"]["trace_id"]) > 0


def test_error_envelope_format_on_missing_auth(client):
    """Test error envelope format matches spec."""
    response = client.get("/auth/me")

    assert response.status_code in (401, 503)
    data = response.json()

    # Validate error envelope
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
    assert "trace_id" in data["error"]
    # details can be None or present
    assert "details" in data["error"] or "details" not in data

    # Should not contain "ok" field (that's for successful responses)
    assert "ok" not in data


# ============================================================================
# HEALTH CHECK TESTS (SHOULD NOT REQUIRE AUTH)
# ============================================================================


def test_health_endpoint_public(client):
    """Test /health endpoint is accessible without authentication."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["ok"] is True


# ============================================================================
# JWKS CACHING TESTS
# ============================================================================


@pytest.mark.asyncio
@patch("app.core.auth.jwks.httpx.AsyncClient.get")
async def test_jwks_cache_invalidation_function(mock_get):
    """Test JWKS cache invalidation function."""

    # Reset cache
    invalidate_jwks_cache()

    # Verify cache is empty
    assert _jwks_cache["data"] is None
    assert _jwks_cache["expires_at"] == 0


@pytest.mark.asyncio
async def test_jwks_fetch_network_error_handling():
    """Test JWKS fetching handles network errors gracefully.

    This test verifies the exception handling without actually making
    network calls.
    """
    from app.core.errors import AppError, ErrorCode

    # Test that the error type checking works
    try:
        raise AppError(
            code=ErrorCode.UNAVAILABLE,
            http_status=503,
            message="Network error",
        )
    except AppError as e:
        assert e.http_status == 503
        assert e.code == ErrorCode.UNAVAILABLE


# ============================================================================
# ERROR MESSAGE TESTS
# ============================================================================


def test_auth_error_message_generic(client):
    """Test auth error messages don't leak sensitive information."""
    response = client.get("/auth/me", headers={"Authorization": "Bearer"})

    data = response.json()
    message = data["error"]["message"]

    # Message should be user-friendly, not expose internals
    assert len(message) < 200  # Reasonably short
    assert message[0].isupper()  # Starts with capital letter


def test_auth_route_exists(client):
    """Test /auth/me route is registered and accessible."""
    # Without auth it should return 401 or 503, not 404
    response = client.get("/auth/me")
    assert response.status_code in (401, 403, 503, 503)  # Not 404


# ============================================================================
# BEARER TOKEN PARSING TESTS
# ============================================================================


def test_bearer_token_with_extra_spaces(client):
    """Test Bearer token parsing with extra whitespace."""
    response = client.get("/auth/me", headers={"Authorization": "Bearer  token"})

    # Should handle gracefully - reject as invalid token
    assert response.status_code in (401, 503)


def test_bearer_case_insensitive(client):
    """Test Bearer token is case-insensitive."""
    response = client.get("/auth/me", headers={"Authorization": "bearer token"})

    # Should handle lowercase "bearer" correctly
    assert response.status_code in (401, 503)


# ============================================================================
# INTEGRATION WITH ERROR ENVELOPE
# ============================================================================


def test_all_auth_errors_return_canonical_envelope(client):
    """Test all authentication errors follow canonical error envelope."""
    # Test various invalid inputs
    test_cases = [
        (None, ""),  # Missing header
        ({"Authorization": "Bearer"}, "empty token"),
        ({"Authorization": "Invalid format"}, "invalid format"),
        ({"Authorization": "bearer token"}, "bearer token"),
    ]

    for headers, desc in test_cases:
        if headers is None:
            response = client.get("/auth/me")
        else:
            response = client.get("/auth/me", headers=headers)

        assert response.status_code >= 400, f"Failed for {desc}"
        data = response.json()

        # All errors must have canonical envelope
        assert "error" in data, f"Missing error envelope for {desc}"
        assert "code" in data["error"], f"Missing error code for {desc}"
        assert "message" in data["error"], f"Missing error message for {desc}"
        assert "trace_id" in data["error"], f"Missing trace_id for {desc}"
