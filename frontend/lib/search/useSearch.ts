/**
 * React Query hook for semantic search.
 *
 * This hook provides typed, cached access to search results with:
 * - Automatic caching and background refetching
 * - Loading and error states
 * - Debounce-friendly design (only queries when query is non-empty)
 */

import { useQuery } from "@tanstack/react-query";
import {
  searchChunks,
  type SearchChunksResult,
  type ChunkSearchHit,
} from "@/lib/api/search";
import type { ClientError } from "@/lib/api/http";

/** Query key prefix for search queries. */
export const SEARCH_KEY = ["search"] as const;

/** Query key factory for search queries. */
export const searchQueryKey = (
  query: string,
  documentIds?: string[]
) => [...SEARCH_KEY, { query, documentIds: documentIds ?? null }] as const;

/**
 * Options for useSearch hook.
 */
export interface UseSearchOptions {
  /** Search query string. Empty string disables the query. */
  query: string;
  /** Max results to return (default: 20) */
  limit?: number;
  /** Optional list of document IDs to restrict search */
  documentIds?: string[];
  /** Whether the query is enabled (in addition to non-empty query check) */
  enabled?: boolean;
}

/**
 * Normalized search result for frontend consumption.
 *
 * This extends the backend ChunkSearchHit with computed/derived fields
 * useful for rendering.
 */
export interface SearchResult {
  /** Unique ID for this result (chunk_id) */
  id: string;
  /** Result kind - currently only 'chunk' is supported by backend */
  kind: "chunk";
  /** Document this chunk belongs to (typed ID: doc_<uuid>) */
  documentId: string;
  /** Similarity score (0-1, higher is more similar) */
  score: number;
  /** Chunk text content (the snippet) */
  text: string;
  /** Byte offset start in canonical text */
  textStart: number;
  /** Byte offset end in canonical text */
  textEnd: number;
}

/**
 * Transform backend ChunkSearchHit to frontend SearchResult.
 */
function toSearchResult(hit: ChunkSearchHit): SearchResult {
  return {
    id: hit.chunk_id,
    kind: "chunk",
    documentId: hit.document_id,
    score: hit.score,
    text: hit.text,
    textStart: hit.text_start,
    textEnd: hit.text_end,
  };
}

/**
 * Hook result shape with explicit types.
 */
export interface UseSearchResult {
  /** Search results (transformed to frontend shape) */
  results: SearchResult[];
  /** Whether the query is currently loading */
  isLoading: boolean;
  /** Whether there was an error */
  isError: boolean;
  /** The error if any */
  error: ClientError | null;
  /** Whether the query completed successfully */
  isSuccess: boolean;
  /** Whether there are more results (pagination, currently always false) */
  hasMore: boolean;
  /** Next cursor for pagination (currently always null) */
  nextCursor: string | null;
  /** Refetch the search */
  refetch: () => void;
}

/**
 * Hook to search document chunks by semantic similarity.
 *
 * The query is only executed when:
 * - query is a non-empty string (after trimming)
 * - enabled option is true (default)
 *
 * @param options - Search options including query string
 * @returns Search result with loading/error states
 *
 * @example
 * ```tsx
 * const { results, isLoading, error } = useSearch({ query: debouncedQuery });
 *
 * if (isLoading) return <Spinner />;
 * if (error) return <ErrorMessage error={error} />;
 *
 * return (
 *   <ul>
 *     {results.map(result => (
 *       <SearchResultItem key={result.id} result={result} />
 *     ))}
 *   </ul>
 * );
 * ```
 */
export function useSearch(options: UseSearchOptions): UseSearchResult {
  const { query, limit = 20, documentIds, enabled = true } = options;

  const trimmedQuery = query.trim();
  const shouldFetch = enabled && trimmedQuery.length > 0;

  const queryResult = useQuery<SearchChunksResult, ClientError>({
    queryKey: searchQueryKey(trimmedQuery, documentIds),
    queryFn: async () => {
      return searchChunks({
        query: trimmedQuery,
        limit,
        documentIds,
      });
    },
    enabled: shouldFetch,
  });

  // Transform results to frontend shape
  const results = queryResult.data?.items.map(toSearchResult) ?? [];

  return {
    results,
    isLoading: queryResult.isLoading && shouldFetch,
    isError: queryResult.isError,
    error: queryResult.error ?? null,
    isSuccess: queryResult.isSuccess,
    hasMore: queryResult.data?.has_more ?? false,
    nextCursor: queryResult.data?.next_cursor ?? null,
    refetch: () => void queryResult.refetch(),
  };
}

