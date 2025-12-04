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
import type {
  HighlightItem,
  HighlightListResponse,
  CreateHighlightRequest,
} from "@/lib/generated-api";
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

/**
 * Parameters for creating a highlight.
 */
export interface CreateHighlightParams {
  /** Typed document ID (doc_<uuid>) */
  documentId: string;
  /** Character offset start in canonical_text (>= 0) */
  textStart: number;
  /** Character offset end in canonical_text (> textStart) */
  textEnd: number;
}

/**
 * Create a new highlight on a document.
 *
 * DESIGN DECISION (PR6):
 * The backend computes quote/prefix/suffix from canonical_text at the given offsets.
 * Client sends (media_type, media_id, anchor_type, text_start, text_end).
 *
 * Rationale:
 * - Single source of truth: canonical text lives in DB
 * - No risk of client/server quote mismatch due to DOM vs canonical differences
 * - Generic API shape supports future media types (episodes, videos)
 *
 * Implication: remap jobs assume quote/prefix/suffix are derived from canonical text,
 * not from browser DOM.
 *
 * v1 constraints:
 * - media_type: only "document" supported
 * - anchor_type: only "text" supported for html/epub
 *
 * @param params - Document ID and text offsets
 * @returns The created highlight item
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * const highlight = await createHighlight({
 *   documentId: "doc_abc123...",
 *   textStart: 100,
 *   textEnd: 150,
 * });
 * console.log(highlight.id); // "hl_xyz..."
 * ```
 */
export async function createHighlight(
  params: CreateHighlightParams
): Promise<HighlightItem> {
  const request: CreateHighlightRequest = {
    media_type: "document",
    media_id: params.documentId,
    anchor_type: "text",
    text_start: params.textStart,
    text_end: params.textEnd,
  };

  const response = await callApi<HighlightItem>(() =>
    HighlightsService.createHighlightEndpointHighlightsPost(request)
  );

  return response;
}

// Re-export types for convenience
export type { HighlightItem, HighlightListResponse };

