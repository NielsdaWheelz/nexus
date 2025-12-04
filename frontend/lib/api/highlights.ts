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
 * Base parameters for creating any highlight.
 */
interface CreateHighlightParamsBase {
  /** Typed document ID (doc_<uuid>) */
  documentId: string;
  /** Character offset start (>= 0) */
  textStart: number;
  /** Character offset end (> textStart) */
  textEnd: number;
}

/**
 * Parameters for creating a text highlight (HTML/EPUB).
 * Backend computes quote/prefix/suffix from canonical_text.
 */
export interface CreateTextHighlightParams extends CreateHighlightParamsBase {
  anchorType: "text";
}

/**
 * Parameters for creating a PDF highlight.
 * Frontend provides quote/prefix/suffix from pdf.js text layer.
 */
export interface CreatePdfHighlightParams extends CreateHighlightParamsBase {
  anchorType: "pdf";
  /** PDF page number (1-based) */
  pdfPageNumber: number;
  /** Character offset within the page */
  pdfCharOffset: number;
  /** Selected text from pdf.js text layer */
  quote: string;
  /** Context before quote (up to 64 chars) */
  prefix?: string;
  /** Context after quote (up to 64 chars) */
  suffix?: string;
}

/**
 * Union type for creating highlights.
 */
export type CreateHighlightParams = CreateTextHighlightParams | CreatePdfHighlightParams;

/**
 * Create a new highlight on a document.
 *
 * DESIGN DECISIONS:
 *
 * For TEXT anchors (HTML/EPUB - PR6):
 * - Backend computes quote/prefix/suffix from canonical_text at given offsets
 * - Single source of truth: canonical text lives in DB
 * - No risk of client/server quote mismatch
 *
 * For PDF anchors (PR10):
 * - Frontend provides quote/prefix/suffix from pdf.js text layer
 * - Backend cannot access pdf.js extraction, so client must send the text
 * - Offsets are in pdf.js text stream coordinates, not canonical_text
 *
 * @param params - Document ID, offsets, and anchor-type-specific fields
 * @returns The created highlight item
 * @throws {ClientError} On API failure
 *
 * @example Text highlight (HTML/EPUB):
 * ```ts
 * const highlight = await createHighlight({
 *   documentId: "doc_abc123...",
 *   anchorType: "text",
 *   textStart: 100,
 *   textEnd: 150,
 * });
 * ```
 *
 * @example PDF highlight:
 * ```ts
 * const highlight = await createHighlight({
 *   documentId: "doc_abc123...",
 *   anchorType: "pdf",
 *   textStart: 500,
 *   textEnd: 550,
 *   pdfPageNumber: 3,
 *   pdfCharOffset: 100,
 *   quote: "selected text",
 *   prefix: "text before ",
 *   suffix: " text after",
 * });
 * ```
 */
export async function createHighlight(
  params: CreateHighlightParams
): Promise<HighlightItem> {
  let request: CreateHighlightRequest;

  if (params.anchorType === "text") {
    // Text anchor: backend computes quote/prefix/suffix
    request = {
      media_type: "document",
      media_id: params.documentId,
      anchor_type: "text",
      text_start: params.textStart,
      text_end: params.textEnd,
    };
  } else {
    // PDF anchor: frontend provides quote/prefix/suffix from pdf.js
    request = {
      media_type: "document",
      media_id: params.documentId,
      anchor_type: "pdf",
      text_start: params.textStart,
      text_end: params.textEnd,
      pdf_page_number: params.pdfPageNumber,
      pdf_char_offset: params.pdfCharOffset,
      quote: params.quote,
      prefix: params.prefix ?? null,
      suffix: params.suffix ?? null,
    };
  }

  const response = await callApi<HighlightItem>(() =>
    HighlightsService.createHighlightEndpointHighlightsPost(request)
  );

  return response;
}

// Re-export types for convenience
export type { HighlightItem, HighlightListResponse };

