/**
 * Tests for HTTP utility layer.
 *
 * These tests verify:
 * - DataEnvelope unwrapping works correctly
 * - Error normalization to ClientError
 * - Error type guards
 */

import { describe, test, expect, vi } from "vitest";
import { ApiError } from "@/lib/generated-api";
import {
  callApi,
  createClientError,
  unwrapResponse,
  isClientError,
  isAuthError,
  isNotFoundError,
  isRateLimitError,
  type ClientError,
} from "./http";

describe("unwrapResponse", () => {
  test("unwraps DataEnvelope response correctly", () => {
    const envelope = {
      data: {
        items: [{ id: "doc_123", title: "Test" }],
        next_cursor: null,
        has_more: false,
      },
    };

    const result = unwrapResponse(envelope);

    expect(result).toEqual({
      items: [{ id: "doc_123", title: "Test" }],
      next_cursor: null,
      has_more: false,
    });
  });

  test("returns already unwrapped response as-is", () => {
    const response = {
      items: [{ id: "doc_123", title: "Test" }],
      next_cursor: null,
      has_more: false,
    };

    const result = unwrapResponse(response);

    expect(result).toEqual(response);
  });

  test("handles nested data envelope", () => {
    const envelope = {
      data: {
        id: "doc_123",
        title: "My Document",
        source_kind: "pdf",
        processing_status: "ready",
        created_at: "2025-01-01T00:00:00Z",
        updated_at: "2025-01-01T00:00:00Z",
      },
    };

    const result = unwrapResponse(envelope);

    expect(result.id).toBe("doc_123");
    expect(result.title).toBe("My Document");
  });
});

describe("createClientError", () => {
  test("creates ClientError from ApiError with error envelope", () => {
    const mockApiError = new ApiError(
      { method: "GET", url: "/documents" },
      {
        url: "http://localhost:8000/documents",
        ok: false,
        status: 404,
        statusText: "Not Found",
        body: {
          error: {
            code: "NOT_FOUND",
            message: "Document not found",
            details: { document_id: "doc_123" },
            trace_id: "req_abc123",
          },
        },
      },
      "Not Found"
    );

    const result = createClientError(mockApiError);

    expect(result.httpStatus).toBe(404);
    expect(result.code).toBe("NOT_FOUND");
    expect(result.message).toBe("Document not found");
    expect(result.details).toEqual({ document_id: "doc_123" });
    expect(result.traceId).toBe("req_abc123");
  });

  test("creates ClientError from ApiError without proper envelope", () => {
    const mockApiError = new ApiError(
      { method: "GET", url: "/documents" },
      {
        url: "http://localhost:8000/documents",
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        body: "Something went wrong",
      },
      "Internal Server Error"
    );

    const result = createClientError(mockApiError);

    expect(result.httpStatus).toBe(500);
    expect(result.code).toBe("INTERNAL_ERROR");
    expect(result.message).toBe("Internal Server Error");
    expect(result.details).toBe("Something went wrong");
    expect(result.traceId).toBeNull();
  });

  test("creates ClientError from generic Error", () => {
    const error = new Error("Network error");

    const result = createClientError(error);

    expect(result.httpStatus).toBe(0);
    expect(result.code).toBe("UNKNOWN_ERROR");
    expect(result.message).toBe("Network error");
    expect(result.traceId).toBeNull();
  });

  test("creates ClientError from non-Error value", () => {
    const result = createClientError("string error");

    expect(result.httpStatus).toBe(0);
    expect(result.code).toBe("UNKNOWN_ERROR");
    expect(result.message).toBe("An unexpected error occurred");
    expect(result.details).toBe("string error");
  });

  test("maps 401 status to AUTH_REQUIRED code", () => {
    const mockApiError = new ApiError(
      { method: "GET", url: "/documents" },
      {
        url: "http://localhost:8000/documents",
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        body: null,
      },
      "Unauthorized"
    );

    const result = createClientError(mockApiError);

    expect(result.code).toBe("AUTH_REQUIRED");
  });

  test("maps 429 status to RATE_LIMITED code", () => {
    const mockApiError = new ApiError(
      { method: "GET", url: "/documents" },
      {
        url: "http://localhost:8000/documents",
        ok: false,
        status: 429,
        statusText: "Too Many Requests",
        body: null,
      },
      "Too Many Requests"
    );

    const result = createClientError(mockApiError);

    expect(result.code).toBe("RATE_LIMITED");
  });
});

describe("callApi", () => {
  test("unwraps successful DataEnvelope response", async () => {
    const mockApiCall = vi.fn().mockResolvedValue({
      data: {
        items: [{ id: "doc_123" }],
        next_cursor: null,
        has_more: false,
      },
    });

    const result = await callApi(mockApiCall);

    expect(result).toEqual({
      items: [{ id: "doc_123" }],
      next_cursor: null,
      has_more: false,
    });
  });

  test("throws ClientError on API failure", async () => {
    const mockApiError = new ApiError(
      { method: "GET", url: "/documents" },
      {
        url: "http://localhost:8000/documents",
        ok: false,
        status: 404,
        statusText: "Not Found",
        body: {
          error: {
            code: "NOT_FOUND",
            message: "Document not found",
            details: null,
            trace_id: "req_xyz",
          },
        },
      },
      "Not Found"
    );

    const mockApiCall = vi.fn().mockRejectedValue(mockApiError);

    await expect(callApi(mockApiCall)).rejects.toMatchObject({
      httpStatus: 404,
      code: "NOT_FOUND",
      message: "Document not found",
    });
  });
});

describe("error type guards", () => {
  const baseError: ClientError = {
    httpStatus: 500,
    code: "INTERNAL_ERROR",
    message: "Test error",
    details: null,
    traceId: null,
  };

  test("isClientError identifies ClientError objects", () => {
    expect(isClientError(baseError)).toBe(true);
    expect(isClientError(new Error("test"))).toBe(false);
    expect(isClientError(null)).toBe(false);
    expect(isClientError({ httpStatus: 500 })).toBe(false);
  });

  test("isAuthError identifies auth errors by code", () => {
    expect(isAuthError({ ...baseError, code: "AUTH_REQUIRED" })).toBe(true);
    expect(isAuthError({ ...baseError, code: "AUTH_INVALID" })).toBe(true);
    expect(isAuthError({ ...baseError, httpStatus: 401 })).toBe(true);
    expect(isAuthError({ ...baseError, code: "NOT_FOUND" })).toBe(false);
  });

  test("isNotFoundError identifies not found errors", () => {
    expect(isNotFoundError({ ...baseError, code: "NOT_FOUND" })).toBe(true);
    expect(isNotFoundError({ ...baseError, httpStatus: 404 })).toBe(true);
    expect(isNotFoundError({ ...baseError, code: "AUTH_REQUIRED" })).toBe(false);
  });

  test("isRateLimitError identifies rate limit errors", () => {
    expect(isRateLimitError({ ...baseError, code: "RATE_LIMITED" })).toBe(true);
    expect(isRateLimitError({ ...baseError, httpStatus: 429 })).toBe(true);
    expect(isRateLimitError({ ...baseError, code: "NOT_FOUND" })).toBe(false);
  });
});

