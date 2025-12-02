/**
 * React Query hooks for highlight operations.
 *
 * These hooks provide typed, cached access to highlight data with:
 * - Automatic caching and background refetching
 * - Loading and error states
 * - Infinite pagination for lists
 *
 * Use these hooks instead of manual useState/useEffect patterns.
 */

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import {
  fetchDocumentHighlights,
  type HighlightsListResult,
  type HighlightItem,
} from "@/lib/api/highlights";

/** Query key factory for document highlights queries. */
export const documentHighlightsKey = (documentId: string) =>
  ["document", documentId, "highlights"] as const;

/**
 * Options for useDocumentHighlights hook.
 */
export interface UseDocumentHighlightsOptions {
  /** Whether the query should execute. Defaults to true. */
  enabled?: boolean;
  /** Number of items per page. Defaults to 100. */
  pageSize?: number;
}

/**
 * Return type for useDocumentHighlights hook.
 */
export interface UseDocumentHighlightsResult {
  /** Flattened array of all highlights loaded so far */
  highlights: HighlightItem[];
  /** Whether the initial load is in progress */
  isLoading: boolean;
  /** Whether there was an error */
  isError: boolean;
  /** The error if any */
  error: Error | null;
  /** Whether there are more pages to fetch */
  hasNextPage: boolean;
  /** Function to fetch the next page */
  fetchNextPage: () => void;
  /** Whether a next page fetch is in progress */
  isFetchingNextPage: boolean;
}

/**
 * Hook to fetch paginated highlights for a document.
 *
 * Uses infinite query for automatic pagination handling.
 * Highlights are flattened into a single array for convenient access.
 *
 * @param documentId - The document ID to fetch highlights for
 * @param options - Optional enabled flag and page size
 * @returns Flattened highlights array and query state
 *
 * @example
 * ```tsx
 * const { highlights, isLoading, hasNextPage, fetchNextPage } =
 *   useDocumentHighlights(documentId);
 *
 * return (
 *   <div>
 *     {highlights.map(h => <HighlightItem key={h.id} highlight={h} />)}
 *     {hasNextPage && <button onClick={fetchNextPage}>Load More</button>}
 *   </div>
 * );
 * ```
 */
export function useDocumentHighlights(
  documentId: string,
  options?: UseDocumentHighlightsOptions
): UseDocumentHighlightsResult {
  const pageSize = options?.pageSize ?? 100;
  const enabled = options?.enabled ?? true;

  const query = useInfiniteQuery<HighlightsListResult, Error>({
    queryKey: documentHighlightsKey(documentId),
    queryFn: async ({ pageParam }) => {
      return fetchDocumentHighlights({
        documentId,
        cursor: pageParam as string | undefined,
        limit: pageSize,
      });
    },
    getNextPageParam: (lastPage) => {
      return lastPage.has_more ? lastPage.next_cursor : undefined;
    },
    initialPageParam: undefined as string | undefined,
    enabled: enabled && !!documentId,
  });

  // Flatten pages into a single array
  const highlights = useMemo(() => {
    return query.data?.pages.flatMap((page) => page.items) ?? [];
  }, [query.data?.pages]);

  return {
    highlights,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    hasNextPage: query.hasNextPage ?? false,
    fetchNextPage: query.fetchNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
  };
}

