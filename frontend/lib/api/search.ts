/**
 * Search API wrapper.
 *
 * This module provides domain-specific functions for search operations.
 * All functions:
 * - Use the HTTP layer for consistent error handling
 * - Unwrap DataEnvelope responses
 * - Throw ClientError on failure
 */

import { SearchService } from "@/lib/generated-api";
import type { ChunkSearchHit, ChunkSearchResponse } from "@/lib/generated-api";
import { callApi, type ClientError } from "./http";

/**
 * Parameters for chunk search.
 */
export interface SearchChunksParams {
  /** Search query text (required, 1-2000 chars) */
  query: string;
  /** Max results to return (optional, 1-100, default 20) */
  limit?: number;
  /** Optional list of document IDs to restrict search (typed IDs: doc_<uuid>) */
  documentIds?: string[];
}

/**
 * Response shape for chunk search.
 * This is the unwrapped inner content of DataEnvelope<ChunkSearchResponse>.
 */
export interface SearchChunksResult {
  items: ChunkSearchHit[];
  next_cursor: string | null;
  has_more: boolean;
}

/**
 * Search document chunks by semantic similarity.
 *
 * Performs vector similarity search over document content chunks using pgvector.
 * Results are restricted to documents owned by the authenticated user (ACL).
 *
 * @param params - Search parameters (query, limit, documentIds)
 * @returns Unwrapped search result with items and pagination info
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * const result = await searchChunks({ query: "existentialism", limit: 10 });
 * console.log(result.items); // ChunkSearchHit[]
 * ```
 */
export async function searchChunks(
  params: SearchChunksParams
): Promise<SearchChunksResult> {
  const { query, limit = 20, documentIds } = params;

  const response = await callApi<ChunkSearchResponse>(() =>
    SearchService.searchChunksSearchChunksPost({
      query,
      limit,
      document_ids: documentIds ?? null,
    })
  );

  return {
    items: response.items,
    next_cursor: response.next_cursor ?? null,
    has_more: response.has_more ?? false,
  };
}

// Re-export types for convenience
export type { ChunkSearchHit, ClientError };
export { isNotFoundError, isAuthError, isClientError } from "./http";

