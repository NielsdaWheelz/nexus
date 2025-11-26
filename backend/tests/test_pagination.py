"""Tests for pagination primitives (encode/decode cursor, PaginationParams, response shape).

This module tests:
- Cursor round-trip (encode → decode consistency)
- Invalid cursor rejection with proper error codes
- Limit validation (min/max bounds)
- PaginatedResponse model shape
- Test-only route for dependency testing
"""

import json

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.errors import ErrorCode, ValidationAppError
from app.core.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
    PaginationParams,
    decode_cursor,
    encode_cursor,
)

# ============================================================================
# TEST 1: ROUND-TRIP CURSOR ENCODING/DECODING
# ============================================================================


class TestCursorRoundTrip:
    """Verify cursor encode → decode round-trip consistency."""

    def test_round_trip_simple_keyset(self):
        """Cursor payload round-trips through encode/decode."""
        original = {
            "created_at": "2025-01-01T12:00:00Z",
            "id": "doc_11111111-2222-3333-4444-555555555555",
        }

        # Encode
        cursor = encode_cursor(original)
        assert isinstance(cursor, str)
        assert len(cursor) > 0

        # Decode
        decoded = decode_cursor(cursor)

        # Should match exactly
        assert decoded == original

    def test_round_trip_multiple_fields(self):
        """Cursor with multiple fields round-trips correctly."""
        original = {
            "created_at": "2025-01-01T12:00:00Z",
            "id": "doc_123",
            "user_id": "usr_456",
            "status": "active",
        }

        cursor = encode_cursor(original)
        decoded = decode_cursor(cursor)
        assert decoded == original

    def test_round_trip_nested_dict(self):
        """Cursor with nested values round-trips correctly."""
        original = {
            "created_at": "2025-01-01T12:00:00Z",
            "metadata": {"section": "intro", "page": 5},
        }

        cursor = encode_cursor(original)
        decoded = decode_cursor(cursor)
        assert decoded == original

    def test_cursor_is_opaque(self):
        """Cursor string doesn't reveal keyset values in plaintext."""
        payload = {"id": "doc_secret123"}

        cursor = encode_cursor(payload)

        # Cursor should not contain the secret value
        assert "secret123" not in cursor
        assert "doc_" not in cursor

    def test_cursor_is_deterministic(self):
        """Same payload always produces same cursor."""
        payload = {"created_at": "2025-01-01T12:00:00Z", "id": "doc_123"}

        cursor1 = encode_cursor(payload)
        cursor2 = encode_cursor(payload)

        assert cursor1 == cursor2


# ============================================================================
# TEST 2: INVALID CURSOR REJECTION
# ============================================================================


class TestInvalidCursors:
    """Verify invalid cursors are rejected with VALIDATION_ERROR."""

    def test_invalid_base64_rejected(self):
        """Invalid base64 raises ValidationAppError (422)."""
        with pytest.raises(ValidationAppError) as exc_info:
            decode_cursor("!!!invalid_base64!!!")

        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert exc_info.value.http_status == 422

    def test_empty_cursor_rejected(self):
        """Empty cursor raises ValidationAppError."""
        with pytest.raises(ValidationAppError) as exc_info:
            decode_cursor("")

        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert "empty" in exc_info.value.message.lower()

    def test_invalid_json_rejected(self):
        """Base64 that decodes to invalid JSON raises ValidationAppError."""
        # "not json" in base64
        invalid_json_b64 = "bm90IGpzb24="

        with pytest.raises(ValidationAppError) as exc_info:
            decode_cursor(invalid_json_b64)

        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    def test_json_array_rejected(self):
        """JSON array instead of object raises ValidationAppError."""
        # Encode a JSON array
        array_payload = ["item1", "item2"]
        array_json = json.dumps(array_payload)
        array_b64 = (
            __import__("base64")
            .urlsafe_b64encode(array_json.encode("utf-8"))
            .rstrip(b"=")
            .decode("ascii")
        )

        with pytest.raises(ValidationAppError) as exc_info:
            decode_cursor(array_b64)

        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert "object" in exc_info.value.message.lower()

    def test_empty_json_object_rejected(self):
        """Empty JSON object raises ValidationAppError."""
        empty_obj_json = json.dumps({})
        empty_obj_b64 = (
            __import__("base64")
            .urlsafe_b64encode(empty_obj_json.encode("utf-8"))
            .rstrip(b"=")
            .decode("ascii")
        )

        with pytest.raises(ValidationAppError) as exc_info:
            decode_cursor(empty_obj_b64)

        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert "empty" in exc_info.value.message.lower()


# ============================================================================
# TEST 3: LIMIT VALIDATION
# ============================================================================


class TestLimitValidation:
    """Verify limit parameter validation in PaginationParams."""

    def test_limit_default(self):
        """Default limit is DEFAULT_PAGE_SIZE."""
        params = PaginationParams()
        assert params.limit == DEFAULT_PAGE_SIZE

    def test_limit_custom_valid(self):
        """Custom limit within range accepted."""
        params = PaginationParams(limit=50)
        assert params.limit == 50

    def test_limit_min_boundary(self):
        """limit=1 is valid (minimum)."""
        params = PaginationParams(limit=1)
        assert params.limit == 1

    def test_limit_max_boundary(self):
        """limit=MAX_PAGE_SIZE is valid (maximum)."""
        params = PaginationParams(limit=MAX_PAGE_SIZE)
        assert params.limit == MAX_PAGE_SIZE

    def test_limit_below_minimum_rejected(self):
        """limit < 1 raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            PaginationParams(limit=0)

        # Pydantic validation error
        assert len(exc_info.value.errors()) > 0

    def test_limit_above_maximum_rejected(self):
        """limit > MAX_PAGE_SIZE raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            PaginationParams(limit=MAX_PAGE_SIZE + 1)

        assert len(exc_info.value.errors()) > 0

    def test_limit_negative_rejected(self):
        """Negative limit rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PaginationParams(limit=-1)

        assert len(exc_info.value.errors()) > 0

    def test_cursor_optional(self):
        """Cursor parameter optional (defaults to None)."""
        params = PaginationParams()
        assert params.cursor is None

    def test_cursor_with_value(self):
        """Cursor parameter can be set."""
        test_cursor = encode_cursor({"id": "test123"})
        params = PaginationParams(cursor=test_cursor)
        assert params.cursor == test_cursor


# ============================================================================
# TEST 4: PAGINATED RESPONSE MODEL SHAPE
# ============================================================================


class TestPaginatedResponseShape:
    """Verify PaginatedResponse model produces correct shape."""

    def test_response_model_shape_with_items(self):
        """PaginatedResponse produces correct JSON shape with items."""
        response = PaginatedResponse[str](
            items=["a", "b", "c"],
            next_cursor="cursor_xyz",
            has_more=True,
        )

        data = response.model_dump()

        assert data == {
            "items": ["a", "b", "c"],
            "next_cursor": "cursor_xyz",
            "has_more": True,
        }

    def test_response_model_shape_end_of_results(self):
        """PaginatedResponse shape when at end (next_cursor null)."""
        response = PaginatedResponse[str](
            items=["a"],
            next_cursor=None,
            has_more=False,
        )

        data = response.model_dump()

        assert data == {
            "items": ["a"],
            "next_cursor": None,
            "has_more": False,
        }

    def test_response_model_shape_empty(self):
        """PaginatedResponse shape with empty items."""
        response = PaginatedResponse[str](
            items=[],
            next_cursor=None,
            has_more=False,
        )

        data = response.model_dump()

        assert data == {
            "items": [],
            "next_cursor": None,
            "has_more": False,
        }

    def test_response_model_generic_with_dict(self):
        """PaginatedResponse generic works with dict items."""
        response = PaginatedResponse[dict](
            items=[{"id": "doc_123", "title": "Test"}],
            next_cursor=None,
            has_more=False,
        )

        data = response.model_dump()

        assert data["items"][0] == {"id": "doc_123", "title": "Test"}

    def test_response_model_json_serializable(self):
        """PaginatedResponse can be serialized to JSON."""
        response = PaginatedResponse[str](
            items=["a", "b"],
            next_cursor="xyz",
            has_more=True,
        )

        json_str = response.model_dump_json()
        # Should not raise, and should be valid JSON
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["items"] == ["a", "b"]


# ============================================================================
# TEST 5: TEST-ONLY ROUTE (DEPENDENCY TESTING)
# ============================================================================


def test_pagination_params_dependency_fastapi():
    """PaginationParams works as FastAPI dependency."""

    # Create test app with pagination dependency
    app = FastAPI()

    @app.get("/test-pagination")
    async def test_route(params: PaginationParams = Depends(PaginationParams)):  # noqa: B008
        """Test route that depends on PaginationParams."""
        if params.cursor:
            # Verify cursor can be decoded
            try:
                decode_cursor(params.cursor)
            except ValidationAppError as e:
                raise HTTPException(status_code=e.http_status, detail=str(e.message)) from e

        return {"limit": params.limit, "cursor": params.cursor}

    client = TestClient(app)

    # Test: valid request
    response = client.get("/test-pagination?limit=20")
    assert response.status_code == 200
    assert response.json() == {"limit": 20, "cursor": None}

    # Test: custom limit with valid cursor
    valid_cursor = encode_cursor({"id": "doc_123"})
    response = client.get(f"/test-pagination?limit=50&cursor={valid_cursor}")
    assert response.status_code == 200
    assert response.json()["limit"] == 50

    # Test: limit too high
    response = client.get(f"/test-pagination?limit={MAX_PAGE_SIZE + 1}")
    assert response.status_code == 422  # Validation error from Pydantic


def test_invalid_cursor_with_fastapi():
    """Invalid cursor in FastAPI dependency raises proper error."""

    app = FastAPI()

    @app.get("/test-pagination")
    async def test_route(params: PaginationParams = Depends(PaginationParams)):  # noqa: B008
        """Test route that validates cursor."""
        if params.cursor:
            try:
                decode_cursor(params.cursor)
            except ValidationAppError as e:
                raise HTTPException(
                    status_code=e.http_status, detail={"error": str(e.message)}
                ) from e

        return {"ok": True}

    client = TestClient(app)

    # Test: invalid cursor is detected
    response = client.get("/test-pagination?cursor=!!!invalid!!!")
    assert response.status_code == 422


def test_cursor_decode_in_handler():
    """Cursor decoding in handler properly raises ValidationAppError."""

    def decode_cursor_from_query(cursor: str | None) -> dict:
        """Decode cursor if present."""
        if not cursor:
            return {}
        return decode_cursor(cursor)

    # Valid cursor
    valid_payload = {"id": "doc_123", "created_at": "2025-01-01T00:00:00Z"}
    cursor = encode_cursor(valid_payload)
    result = decode_cursor_from_query(cursor)
    assert result == valid_payload

    # Invalid cursor raises ValidationAppError
    with pytest.raises(ValidationAppError) as exc_info:
        decode_cursor_from_query("invalid!!!")

    assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
