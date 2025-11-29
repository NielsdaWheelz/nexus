/**
 * HTTP utility layer for API communication.
 *
 * This module provides:
 * - ClientError type for normalized error handling
 * - Response unwrapping for DataEnvelope responses
 * - Centralized error normalization from ApiError to ClientError
 *
 * All API calls from pages should go through this layer (via domain-specific wrappers)
 * to ensure consistent error handling and response unwrapping.
 */

import { ApiError } from "@/lib/generated-api";

/**
 * Normalized client error type.
 *
 * All API errors are converted to this shape, providing consistent
 * error handling across the frontend. This matches the backend's
 * error envelope structure.
 */
export type ClientError = {
  /** HTTP status code (e.g., 401, 404, 500) */
  httpStatus: number;
  /** Canonical error code from backend (e.g., "NOT_FOUND", "AUTH_REQUIRED") */
  code: string;
  /** Human-readable error message */
  message: string;
  /** Structured error details (field errors, etc.) */
  details: unknown;
  /** Request trace ID for debugging/support */
  traceId: string | null;
  /** Original error for debugging */
  raw?: unknown;
};

/**
 * Backend error envelope shape (matches backend error_handlers.py).
 */
interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: unknown;
    trace_id: string | null;
  };
}

/**
 * Backend success envelope shape (matches backend DataEnvelope[T]).
 */
interface DataEnvelope<T> {
  data: T;
}

/**
 * Type guard to check if a value is an ErrorEnvelope.
 */
function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ErrorEnvelope).error === "object" &&
    (value as ErrorEnvelope).error !== null &&
    "code" in (value as ErrorEnvelope).error &&
    "message" in (value as ErrorEnvelope).error
  );
}

/**
 * Type guard to check if a value is a DataEnvelope.
 */
function isDataEnvelope<T>(value: unknown): value is DataEnvelope<T> {
  return typeof value === "object" && value !== null && "data" in value;
}

/**
 * Create a ClientError from any error.
 *
 * Handles:
 * - ApiError with backend error envelope in body
 * - ApiError without proper envelope (synthesizes error)
 * - Generic errors (synthesizes UNKNOWN_ERROR)
 */
export function createClientError(error: unknown): ClientError {
  // Handle ApiError from generated client
  if (error instanceof ApiError) {
    const body = error.body;

    // Check if body contains our error envelope
    if (isErrorEnvelope(body)) {
      return {
        httpStatus: error.status,
        code: body.error.code,
        message: body.error.message,
        details: body.error.details,
        traceId: body.error.trace_id,
        raw: error,
      };
    }

    // ApiError without proper envelope - synthesize error
    return {
      httpStatus: error.status,
      code: mapHttpStatusToCode(error.status),
      message: error.message || error.statusText || "An error occurred",
      details: body,
      traceId: null,
      raw: error,
    };
  }

  // Generic error fallback
  if (error instanceof Error) {
    return {
      httpStatus: 0,
      code: "UNKNOWN_ERROR",
      message: error.message || "An unexpected error occurred",
      details: null,
      traceId: null,
      raw: error,
    };
  }

  // Non-Error thrown value
  return {
    httpStatus: 0,
    code: "UNKNOWN_ERROR",
    message: "An unexpected error occurred",
    details: error,
    traceId: null,
    raw: error,
  };
}

/**
 * Map HTTP status codes to canonical error codes.
 * Used as fallback when error envelope is missing.
 */
function mapHttpStatusToCode(status: number): string {
  const statusCodeMap: Record<number, string> = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "UNAVAILABLE",
  };

  return statusCodeMap[status] || "UNKNOWN_ERROR";
}

/**
 * Unwrap a DataEnvelope response and return the inner data.
 *
 * Handles both:
 * - Properly wrapped responses: { data: T }
 * - Legacy unwrapped responses: T (for backwards compatibility during migration)
 *
 * @param response - The response from the API (may or may not be wrapped)
 * @returns The unwrapped data of type T
 */
export function unwrapResponse<T>(response: DataEnvelope<T> | T): T {
  if (isDataEnvelope<T>(response)) {
    return response.data;
  }
  // Handle case where response is already unwrapped (legacy or different endpoint)
  return response;
}

/**
 * Execute an API call, unwrap the response, and normalize errors.
 *
 * This is the primary interface for making API calls. It:
 * 1. Executes the provided API call
 * 2. Unwraps DataEnvelope on success
 * 3. Converts errors to ClientError
 *
 * @param apiCall - A function that returns a Promise from a service method
 * @returns The unwrapped response data
 * @throws ClientError on any failure
 *
 * @example
 * ```ts
 * const result = await callApi(() =>
 *   DocumentsService.listDocumentsDocumentsGet(undefined, 20, cursor)
 * );
 * // result is the unwrapped { items, next_cursor, has_more }
 * ```
 */
export async function callApi<T>(apiCall: () => Promise<DataEnvelope<T> | T>): Promise<T> {
  try {
    const response = await apiCall();
    return unwrapResponse(response);
  } catch (error) {
    throw createClientError(error);
  }
}

/**
 * Check if an error is a ClientError.
 */
export function isClientError(error: unknown): error is ClientError {
  return (
    typeof error === "object" &&
    error !== null &&
    "httpStatus" in error &&
    "code" in error &&
    "message" in error
  );
}

/**
 * Check if a ClientError indicates an authentication issue.
 */
export function isAuthError(error: ClientError): boolean {
  return error.code === "AUTH_REQUIRED" || error.code === "AUTH_INVALID" || error.httpStatus === 401;
}

/**
 * Check if a ClientError indicates a not found error.
 */
export function isNotFoundError(error: ClientError): boolean {
  return error.code === "NOT_FOUND" || error.httpStatus === 404;
}

/**
 * Check if a ClientError indicates a rate limit error.
 */
export function isRateLimitError(error: ClientError): boolean {
  return error.code === "RATE_LIMITED" || error.httpStatus === 429;
}

