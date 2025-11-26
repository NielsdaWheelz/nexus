"""Tests for CORS configuration.

Tests cover:
- Allowed origins: localhost:3000, 127.0.0.1:3000
- Disallowed origins: evil.example.com
- Preflight (OPTIONS) requests
- Allowed methods and headers
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = create_app()
    return TestClient(app)


class TestCORSAllowedOrigins:
    """Test that allowed origins can access the API."""

    @pytest.mark.parametrize(
        "origin",
        [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
        ],
    )
    def test_allowed_origin_health(self, client, origin):
        """Test that allowed origins can access /health.

        Args:
            client: TestClient fixture
            origin: Origin header value
        """
        response = client.get("/health", headers={"Origin": origin})
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == origin

    @pytest.mark.parametrize(
        "origin",
        [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )
    def test_allowed_origin_preflight(self, client, origin):
        """Test that preflight requests for allowed origins return correct headers.

        Args:
            client: TestClient fixture
            origin: Origin header value
        """
        response = client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == origin
        assert "GET" in response.headers.get("Access-Control-Allow-Methods", "")


class TestCORSDisallowedOrigins:
    """Test that disallowed origins are rejected."""

    def test_disallowed_origin_health(self, client):
        """Test that disallowed origins cannot access /health.

        An evil origin should not be echoed back in CORS headers.

        Args:
            client: TestClient fixture
        """
        response = client.get("/health", headers={"Origin": "https://evil.example.com"})
        assert response.status_code == 200
        # The origin should not be echoed back
        cors_header = response.headers.get("Access-Control-Allow-Origin")
        assert cors_header != "https://evil.example.com"


class TestCORSPreflight:
    """Test CORS preflight (OPTIONS) request handling."""

    def test_preflight_allowed_methods(self, client):
        """Test that preflight returns allowed methods.

        Args:
            client: TestClient fixture
        """
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        allowed_methods = response.headers.get("Access-Control-Allow-Methods", "")
        assert "POST" in allowed_methods

    def test_preflight_allowed_headers(self, client):
        """Test that preflight returns allowed headers.

        Args:
            client: TestClient fixture
        """
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert response.status_code == 200
        allowed_headers = response.headers.get("Access-Control-Allow-Headers", "")
        assert "Authorization" in allowed_headers or "*" in allowed_headers

    def test_preflight_credentials_false(self, client):
        """Test that credentials are not allowed (we use bearer tokens).

        Args:
            client: TestClient fixture
        """
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        # credentials should be False (we use bearer tokens, not cookies)
        credentials_header = response.headers.get("Access-Control-Allow-Credentials", "")
        assert credentials_header != "true"
