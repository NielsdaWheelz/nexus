/**
 * Documents API wrapper.
 *
 * This module provides domain-specific functions for document operations.
 * All functions:
 * - Use the HTTP layer for consistent error handling
 * - Unwrap DataEnvelope responses
 * - Throw ClientError on failure
 *
 * Pages should use these functions instead of DocumentsService directly.
 */

import { DocumentsService } from "@/lib/generated-api";
import type { DocumentListItem, DocumentListResponse, DocumentUploadResponse } from "@/lib/generated-api";
import { callApi, type ClientError } from "./http";

/**
 * Parameters for fetching documents list.
 */
export interface FetchDocumentsListParams {
  /** Pagination cursor (undefined for first page) */
  cursor?: string;
  /** Number of items per page (default: 20) */
  limit?: number;
  /** Filter by processing status */
  status?: string;
}

/**
 * Response shape for documents list.
 * This is the unwrapped inner content of DataEnvelope<DocumentListResponse>.
 */
export interface DocumentsListResult {
  items: DocumentListItem[];
  next_cursor: string | null;
  has_more: boolean;
}

/**
 * Fetch paginated list of user's documents.
 *
 * @param params - Pagination and filter parameters
 * @returns Unwrapped list result with items, cursor, and has_more
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * const result = await fetchDocumentsList({ limit: 20 });
 * console.log(result.items); // DocumentListItem[]
 * console.log(result.has_more); // boolean
 * ```
 */
export async function fetchDocumentsList(
  params: FetchDocumentsListParams = {}
): Promise<DocumentsListResult> {
  const { cursor, limit = 20, status } = params;

  const response = await callApi<DocumentListResponse>(() =>
    DocumentsService.listDocumentsDocumentsGet(
      status ?? undefined,
      limit,
      cursor ?? undefined
    )
  );

  return {
    items: response.items,
    next_cursor: response.next_cursor ?? null,
    has_more: response.has_more,
  };
}

/**
 * Fetch a single document by ID.
 *
 * @param documentId - The typed document ID (e.g., "doc_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
 * @returns The document details
 * @throws {ClientError} On API failure (including NOT_FOUND for missing documents)
 *
 * @example
 * ```ts
 * try {
 *   const doc = await fetchDocument("doc_abc123...");
 *   console.log(doc.title);
 * } catch (error) {
 *   if (isNotFoundError(error)) {
 *     console.log("Document not found");
 *   }
 * }
 * ```
 */
export async function fetchDocument(documentId: string): Promise<DocumentListItem> {
  return callApi<DocumentListItem>(() =>
    DocumentsService.getDocumentDocumentsDocumentIdGet(documentId)
  );
}

/**
 * Upload parameters for document upload.
 */
export interface UploadDocumentParams {
  /** The file to upload (PDF, EPUB, or HTML) */
  file: File;
  /** Source type: pdf, epub, or html */
  sourceKind: "pdf" | "epub" | "html";
  /** Optional document title (defaults to filename if not provided) */
  title?: string;
}

/**
 * Upload a document file.
 *
 * @param params - Upload parameters (file, sourceKind, optional title)
 * @returns The created document metadata
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * const result = await uploadDocument({
 *   file: selectedFile,
 *   sourceKind: "pdf",
 *   title: "My Document",
 * });
 * console.log(result.id); // "doc_xxx..."
 * ```
 */
export async function uploadDocument(
  params: UploadDocumentParams
): Promise<DocumentUploadResponse> {
  const { file, sourceKind, title } = params;

  return callApi<DocumentUploadResponse>(() =>
    DocumentsService.uploadDocumentDocumentsPost({
      file: file,
      source_kind: sourceKind,
      title: title ?? null,
    })
  );
}

/**
 * Fetch the original binary blob of a document.
 *
 * This returns the raw file (PDF, EPUB, HTML) as an ArrayBuffer.
 * Used by PDF.js and other renderers that need the original binary content.
 *
 * NOTE: This intentionally bypasses the normal callApi/DataEnvelope pattern
 * because the blob endpoint returns raw binary data, not a JSON-wrapped response.
 * However, it still:
 * - Uses OpenAPI.BASE for the base URL (same as generated client)
 * - Uses OpenAPI.TOKEN for auth (same token resolution as generated client)
 * - Uses OpenAPI.CREDENTIALS for cookie handling
 * - Normalizes errors to ClientError shape (same as callApi)
 *
 * @param documentId - Typed document ID (doc_<uuid>)
 * @returns ArrayBuffer containing the binary file content
 * @throws {ClientError} On API failure (404, 401, etc.)
 *
 * @example
 * ```ts
 * const buffer = await fetchDocumentBlob("doc_abc123...");
 * // Use with PDF.js: pdfjsLib.getDocument({ data: buffer })
 * ```
 */
export async function fetchDocumentBlob(documentId: string): Promise<ArrayBuffer> {
  const { OpenAPI } = await import("@/lib/generated-api");

  // Build URL using the same base as the generated client
  const baseUrl = OpenAPI.BASE || "";
  const url = `${baseUrl}/documents/${documentId}/blob`;

  // Resolve auth token using the same machinery as the generated client
  // OpenAPI.TOKEN can be a string, a resolver function, or undefined
  let token: string | undefined;
  if (typeof OpenAPI.TOKEN === "function") {
    token = await OpenAPI.TOKEN({} as Parameters<typeof OpenAPI.TOKEN>[0]);
  } else if (typeof OpenAPI.TOKEN === "string") {
    token = OpenAPI.TOKEN;
  }

  // Build headers, including auth token if available
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    method: "GET",
    headers,
    credentials: OpenAPI.CREDENTIALS,
  });

  if (!response.ok) {
    // Try to parse error envelope from response (backend returns JSON error body)
    let errorData: {
      error?: {
        code?: string;
        message?: string;
        details?: unknown;
        trace_id?: string | null;
      };
    } | null = null;
    try {
      errorData = await response.json();
    } catch {
      // Response is not JSON (e.g., nginx error page), use status text
    }

    // Normalize to ClientError shape for consistent error handling
    const error: ClientError = {
      httpStatus: response.status,
      code: errorData?.error?.code ?? mapHttpStatusToCode(response.status),
      message:
        errorData?.error?.message ??
        response.statusText ??
        "Failed to fetch document blob",
      details: errorData?.error?.details ?? null,
      traceId: errorData?.error?.trace_id ?? null,
    };

    throw error;
  }

  return response.arrayBuffer();
}

/**
 * Map HTTP status codes to canonical error codes.
 * Used as fallback when error envelope is missing from response.
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

// Re-export error utilities for convenience
export { isNotFoundError, isAuthError, isClientError, type ClientError } from "./http";

