/**
 * Document Content API wrapper.
 *
 * This module provides functions for fetching document content.
 * All functions:
 * - Use the HTTP layer for consistent error handling
 * - Unwrap DataEnvelope responses
 * - Throw ClientError on failure
 *
 * Pages should use these functions instead of DocumentsService directly.
 */

import { DocumentsService } from "@/lib/generated-api";
import type { DocumentContentResponse } from "@/lib/generated-api";
import { callApi } from "./http";

/**
 * Fetch the canonical text content of a document.
 *
 * Note: Document must be in 'ready' status to have content available.
 * For large documents (>5MB), expect response times of 1-3s.
 *
 * @param documentId - Typed document ID (doc_<uuid>)
 * @returns DocumentContentResponse with canonical text and metadata
 * @throws {ClientError} On API failure (including 422 if document not ready)
 *
 * @example
 * ```ts
 * const content = await fetchDocumentContent("doc_abc123...");
 * console.log(content.canonical_text); // Full text
 * console.log(content.text_length);    // Character count
 * ```
 */
export async function fetchDocumentContent(
  documentId: string
): Promise<DocumentContentResponse> {
  return callApi<DocumentContentResponse>(() =>
    DocumentsService.getDocumentContentDocumentsDocumentIdContentGet(documentId)
  );
}

// Re-export types for convenience
export type { DocumentContentResponse };

