"""Tests for health endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    """Test health endpoint returns 200 with correct response."""
    response = client.get("/health")
    assert response.status_code == 200
    response_data = response.json()
    assert "data" in response_data
    data = response_data["data"]
    assert data["ok"] is True
    assert data["status"] == "healthy"


def test_health_endpoint_has_trace_id_header(client: TestClient) -> None:
    """Test health endpoint response includes X-Trace-Id header."""
    response = client.get("/health")
    assert "X-Trace-Id" in response.headers
    assert response.headers["X-Trace-Id"]  # Should be non-empty


def test_health_endpoint_trace_id_format(client: TestClient) -> None:
    """Test trace ID has expected format (req_<hex>)."""
    response = client.get("/health")
    trace_id = response.headers["X-Trace-Id"]
    assert trace_id.startswith("req_")
    assert len(trace_id) > 4  # Should have content after prefix
