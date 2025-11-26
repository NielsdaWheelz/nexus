"""Tests for rate limiting functionality.

Tests cover:
- Authenticated rate limiting (per-user, GLOBAL_USER scope)
- Anonymous rate limiting (per-IP, GLOBAL_ANON scope)
- Rate limit enforcement and 429 responses
- Error envelope shape with rate limit details
- Health check exempt from rate limiting
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import (
    RATE_LIMITS,
    RateLimitScope,
    clear_rate_limit_store,
)
from app.main import create_app
from app.models.user import User


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Clear rate limit store before each test."""
    clear_rate_limit_store()
    yield
    clear_rate_limit_store()


def create_mock_user(user_id: str, external_user_id: str, email: str) -> User:
    """Helper to create a mock user."""
    from datetime import datetime, timezone

    user = User(
        id=user_id,
        external_user_id=external_user_id,
        email=email,
    )
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


class TestAuthenticatedRateLimiting:
    """Test rate limiting for authenticated endpoints (per-user)."""

    @patch("app.core.auth.deps.get_session")
    @patch("app.core.auth.deps.verify_clerk_jwt")
    def test_authenticated_requests_within_limit(
        self, mock_verify, mock_session, client, auth_token
    ):
        """Test that authenticated requests within limit succeed.

        Args:
            mock_verify: Mocked JWT verification
            mock_session: Mocked database session
            client: TestClient fixture
            auth_token: Valid JWT token from fixture
        """
        # Setup JWT verification mock
        mock_verify.return_value = {
            "sub": "user_test_1",
            "email": "test1@example.com",
        }

        # Setup database mock
        mock_db_session = MagicMock()
        mock_session.return_value = mock_db_session

        user = create_mock_user(
            "00000000-0000-0000-0000-000000000001", "user_test_1", "test1@example.com"
        )
        mock_db_session.query.return_value.filter.return_value.first.return_value = user

        # Get limit for authenticated scope
        limit = RATE_LIMITS[RateLimitScope.GLOBAL_USER].limit

        # Make requests up to the limit
        for i in range(limit):
            response = client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 200, f"Request {i+1} failed: {response.text}"

    @patch("app.core.auth.deps.get_session")
    @patch("app.core.auth.deps.verify_clerk_jwt")
    def test_authenticated_requests_exceed_limit(
        self, mock_verify, mock_session, client, auth_token
    ):
        """Test that authenticated requests exceeding limit return 429.

        Args:
            mock_verify: Mocked JWT verification
            mock_session: Mocked database session
            client: TestClient fixture
            auth_token: Valid JWT token from fixture
        """
        # Setup JWT verification mock
        mock_verify.return_value = {
            "sub": "user_test_1",
            "email": "test1@example.com",
        }

        # Setup database mock
        mock_db_session = MagicMock()
        mock_session.return_value = mock_db_session

        user = create_mock_user(
            "00000000-0000-0000-0000-000000000001", "user_test_1", "test1@example.com"
        )
        mock_db_session.query.return_value.filter.return_value.first.return_value = user

        # Get limit for authenticated scope
        limit = RATE_LIMITS[RateLimitScope.GLOBAL_USER].limit

        # Make requests up to and exceeding the limit
        for i in range(limit + 1):
            response = client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            if i < limit:
                assert response.status_code == 200, f"Request {i+1} failed: {response.text}"
            else:
                # This should be rate limited
                assert response.status_code == 429
                data = response.json()
                assert "error" in data
                assert data["error"]["code"] == "RATE_LIMITED"

    @patch("app.core.auth.deps.get_session")
    @patch("app.core.auth.deps.verify_clerk_jwt")
    def test_authenticated_rate_limit_error_envelope(
        self, mock_verify, mock_session, client, auth_token
    ):
        """Test that rate limit error includes proper envelope and details.

        Args:
            mock_verify: Mocked JWT verification
            mock_session: Mocked database session
            client: TestClient fixture
            auth_token: Valid JWT token from fixture
        """
        # Setup JWT verification mock
        mock_verify.return_value = {
            "sub": "user_test_1",
            "email": "test1@example.com",
        }

        # Setup database mock
        mock_db_session = MagicMock()
        mock_session.return_value = mock_db_session

        user = create_mock_user(
            "00000000-0000-0000-0000-000000000001", "user_test_1", "test1@example.com"
        )
        mock_db_session.query.return_value.filter.return_value.first.return_value = user

        # Get limit for authenticated scope
        limit = RATE_LIMITS[RateLimitScope.GLOBAL_USER].limit
        window_seconds = RATE_LIMITS[RateLimitScope.GLOBAL_USER].window_seconds

        # Exhaust the limit
        for _ in range(limit):
            response = client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 429

        data = response.json()
        assert "error" in data
        error = data["error"]
        assert error["code"] == "RATE_LIMITED"
        assert "Rate limit exceeded" in error["message"]
        assert "details" in error
        assert error["details"]["scope"] == "global_user"
        assert error["details"]["limit"] == limit
        assert error["details"]["window_seconds"] == window_seconds
        assert "trace_id" in error


class TestAnonymousRateLimiting:
    """Test rate limiting for anonymous endpoints (per-IP)."""

    def test_anonymous_requests_within_limit(self, client):
        """Test that anonymous requests within limit succeed.

        Args:
            client: TestClient fixture
        """
        # Get limit for anonymous scope
        limit = RATE_LIMITS[RateLimitScope.GLOBAL_ANON].limit

        # Make requests up to the limit
        for i in range(limit):
            response = client.get("/test/rate-limited", headers={})
            assert response.status_code == 200, f"Request {i+1} failed: {response.text}"

    def test_anonymous_requests_exceed_limit(self, client):
        """Test that anonymous requests exceeding limit return 429.

        Args:
            client: TestClient fixture
        """
        # Get limit for anonymous scope
        limit = RATE_LIMITS[RateLimitScope.GLOBAL_ANON].limit

        # Make requests up to and exceeding the limit
        for i in range(limit + 1):
            response = client.get("/test/rate-limited")
            if i < limit:
                assert response.status_code == 200, f"Request {i+1} failed: {response.text}"
            else:
                # This should be rate limited
                assert response.status_code == 429
                data = response.json()
                assert "error" in data
                assert data["error"]["code"] == "RATE_LIMITED"

    def test_anonymous_rate_limit_error_envelope(self, client):
        """Test that anonymous rate limit error includes proper envelope and details.

        Args:
            client: TestClient fixture
        """
        # Get limit for anonymous scope
        limit = RATE_LIMITS[RateLimitScope.GLOBAL_ANON].limit
        window_seconds = RATE_LIMITS[RateLimitScope.GLOBAL_ANON].window_seconds

        # Exhaust the limit
        for _ in range(limit):
            response = client.get("/test/rate-limited")
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get("/test/rate-limited")
        assert response.status_code == 429

        data = response.json()
        assert "error" in data
        error = data["error"]
        assert error["code"] == "RATE_LIMITED"
        assert "Rate limit exceeded" in error["message"]
        assert "details" in error
        assert error["details"]["scope"] == "global_anon"
        assert error["details"]["limit"] == limit
        assert error["details"]["window_seconds"] == window_seconds
        assert "trace_id" in error


class TestHealthCheckExempt:
    """Test that /health is not rate-limited."""

    def test_health_check_not_rate_limited(self, client):
        """Test that /health can be called many times without rate limiting.

        Args:
            client: TestClient fixture
        """
        # Get limit for anonymous scope
        limit = RATE_LIMITS[RateLimitScope.GLOBAL_ANON].limit

        # Call /health more times than the anonymous limit
        for i in range(limit * 2):
            response = client.get("/health")
            assert response.status_code == 200, f"Request {i+1} failed"

        # Should never return 429
        response = client.get("/health")
        assert response.status_code == 200
