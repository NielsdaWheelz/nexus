"""Tests for security headers middleware.

Tests cover:
- Security headers present on all responses
- Headers present on success responses (/health)
- Headers present on authenticated responses (/auth/me)
- Headers present on error responses (4xx, 5xx)
- Header values are correct and follow security standards
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.security_headers import SECURITY_HEADERS
from app.main import create_app
from app.models.user import User


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


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


class TestSecurityHeadersPresent:
    """Test that security headers are present on all responses."""

    @pytest.mark.parametrize("header_name", SECURITY_HEADERS.keys())
    def test_security_headers_on_health(self, client, header_name):
        """Test that security headers are present on /health response.

        Args:
            client: TestClient fixture
            header_name: Name of security header to check
        """
        response = client.get("/health")
        assert response.status_code == 200
        assert header_name in response.headers, f"Header {header_name} missing"

    @pytest.mark.parametrize("header_name", SECURITY_HEADERS.keys())
    @patch("app.core.auth.deps.get_session")
    @patch("app.core.auth.deps.verify_clerk_jwt")
    def test_security_headers_on_authenticated_endpoint(
        self, mock_verify, mock_session, client, header_name, auth_token
    ):
        """Test that security headers are present on authenticated endpoint response.

        Args:
            mock_verify: Mocked JWT verification
            mock_session: Mocked database session
            client: TestClient fixture
            header_name: Name of security header to check
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

        user = create_mock_user("00000000-0000-0000-0000-000000000001", "user_test_1", "test1@example.com")
        mock_db_session.query.return_value.filter.return_value.first.return_value = user

        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200
        assert header_name in response.headers, f"Header {header_name} missing"

    @pytest.mark.parametrize("header_name", SECURITY_HEADERS.keys())
    def test_security_headers_on_error_response(self, client, header_name):
        """Test that security headers are present on error response (401).

        Args:
            client: TestClient fixture
            header_name: Name of security header to check
        """
        # Call /auth/me without authentication to get 401 error
        response = client.get("/auth/me")
        assert response.status_code in (401, 503)  # 401 or 503 depending on Clerk config
        assert header_name in response.headers, f"Header {header_name} missing on error"

    @pytest.mark.parametrize("header_name", SECURITY_HEADERS.keys())
    def test_security_headers_on_404(self, client, header_name):
        """Test that security headers are present on 404 response.

        Args:
            client: TestClient fixture
            header_name: Name of security header to check
        """
        response = client.get("/nonexistent")
        assert response.status_code == 404
        assert header_name in response.headers, f"Header {header_name} missing on 404"


class TestSecurityHeaderValues:
    """Test that security header values are correct."""

    def test_x_content_type_options(self, client):
        """Test X-Content-Type-Options header value.

        Args:
            client: TestClient fixture
        """
        response = client.get("/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client):
        """Test X-Frame-Options header value.

        Args:
            client: TestClient fixture
        """
        response = client.get("/health")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_referrer_policy(self, client):
        """Test Referrer-Policy header value.

        Args:
            client: TestClient fixture
        """
        response = client.get("/health")
        assert (
            response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        )

    def test_x_xss_protection(self, client):
        """Test X-XSS-Protection header value.

        Note: Modern browsers prefer CSP, so this is set to '0' (disable the filter).

        Args:
            client: TestClient fixture
        """
        response = client.get("/health")
        assert response.headers.get("X-XSS-Protection") == "0"

    def test_strict_transport_security(self, client):
        """Test Strict-Transport-Security header value.

        Args:
            client: TestClient fixture
        """
        response = client.get("/health")
        hsts = response.headers.get("Strict-Transport-Security")
        assert hsts is not None
        assert "max-age=" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts


class TestSecurityHeadersDoNotClobber:
    """Test that security headers don't clobber existing headers."""

    def test_trace_id_header_preserved(self, client):
        """Test that X-Trace-Id header is preserved.

        Args:
            client: TestClient fixture
        """
        response = client.get("/health")
        assert response.status_code == 200
        # Both trace ID and security headers should be present
        assert "X-Trace-Id" in response.headers
        assert "X-Content-Type-Options" in response.headers

    def test_content_type_header_preserved(self, client):
        """Test that Content-Type header is preserved.

        Args:
            client: TestClient fixture
        """
        response = client.get("/health")
        assert response.status_code == 200
        # Both content type and security headers should be present
        assert "content-type" in response.headers or "Content-Type" in response.headers
        assert "X-Content-Type-Options" in response.headers
