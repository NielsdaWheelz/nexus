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

// Re-export error utilities for convenience
export { isNotFoundError, isAuthError, isClientError, type ClientError } from "./http";

