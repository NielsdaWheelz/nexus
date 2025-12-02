/**
 * Highlights API wrapper.
 *
 * This module provides domain-specific functions for highlight operations.
 * All functions:
 * - Use the HTTP layer for consistent error handling
 * - Unwrap DataEnvelope responses
 * - Throw ClientError on failure
 *
 * Pages should use these functions instead of HighlightsService directly.
 */

import { HighlightsService } from "@/lib/generated-api";
import type { HighlightItem, HighlightListResponse } from "@/lib/generated-api";
import { callApi } from "./http";

/**
 * Parameters for fetching document highlights.
 */
export interface FetchDocumentHighlightsParams {
  /** Typed document ID (doc_<uuid>) */
  documentId: string;
  /** Pagination cursor (undefined for first page) */
  cursor?: string | null;
  /** Number of items per page (default: 100) */
  limit?: number;
}

/**
 * Response shape for highlights list.
 * This is the unwrapped inner content of DataEnvelope<HighlightListResponse>.
 */
export interface HighlightsListResult {
  items: HighlightItem[];
  next_cursor: string | null;
  has_more: boolean;
}

/**
 * Fetch paginated list of highlights for a document.
 *
 * @param params - Document ID, pagination cursor, and limit
 * @returns Unwrapped list result with items, cursor, and has_more
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * const result = await fetchDocumentHighlights({
 *   documentId: "doc_abc123...",
 *   limit: 100,
 * });
 * console.log(result.items); // HighlightItem[]
 * console.log(result.has_more); // boolean
 * ```
 */
export async function fetchDocumentHighlights(
  params: FetchDocumentHighlightsParams
): Promise<HighlightsListResult> {
  const { documentId, cursor, limit = 100 } = params;

  const response = await callApi<HighlightListResponse>(() =>
    HighlightsService.listDocumentHighlightsDocumentsDocumentIdHighlightsGet(
      documentId,
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

// Re-export types for convenience
export type { HighlightItem, HighlightListResponse };

