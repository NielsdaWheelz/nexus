/**
 * React Query hooks for highlight operations.
 *
 * These hooks provide typed, cached access to highlight data with:
 * - Automatic caching and background refetching
 * - Loading and error states
 * - Infinite pagination for lists
 * - Mutations with automatic cache invalidation
 *
 * Use these hooks instead of manual useState/useEffect patterns.
 */

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useCallback } from "react";
import {
  fetchDocumentHighlights,
  createHighlight,
  type HighlightsListResult,
  type HighlightItem,
  type CreateHighlightParams,
} from "@/lib/api/highlights";
import type { ClientError } from "@/lib/api/http";

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

/**
 * Parameters for creating a highlight via the hook (documentId provided separately).
 */
export type CreateHighlightHookParams =
  | { anchorType: "text"; textStart: number; textEnd: number }
  | {
      anchorType: "pdf";
      textStart: number;
      textEnd: number;
      pdfPageNumber: number;
      pdfCharOffset: number;
      quote: string;
      prefix?: string;
      suffix?: string;
    };

/**
 * Return type for useCreateHighlight hook.
 */
export interface UseCreateHighlightResult {
  /** Trigger highlight creation */
  createHighlight: (params: CreateHighlightHookParams) => Promise<HighlightItem>;
  /** Whether a creation is in progress */
  isPending: boolean;
  /** Whether the last creation failed */
  isError: boolean;
  /** Error from the last creation attempt */
  error: ClientError | null;
  /** The last successfully created highlight */
  data: HighlightItem | null;
  /** Reset the mutation state */
  reset: () => void;
}

/**
 * Hook for creating highlights on a document.
 *
 * On successful creation:
 * - Invalidates the document highlights query to refresh the list
 * - Returns the newly created highlight
 *
 * @param documentId - The document ID to create highlights on
 * @returns Mutation controls and state
 *
 * @example Text highlight (HTML/EPUB):
 * ```tsx
 * const { createHighlight, isPending } = useCreateHighlight(documentId);
 * const highlight = await createHighlight({
 *   anchorType: "text",
 *   textStart: 100,
 *   textEnd: 150,
 * });
 * ```
 *
 * @example PDF highlight:
 * ```tsx
 * const { createHighlight, isPending } = useCreateHighlight(documentId);
 * const highlight = await createHighlight({
 *   anchorType: "pdf",
 *   textStart: 500,
 *   textEnd: 550,
 *   pdfPageNumber: 3,
 *   pdfCharOffset: 100,
 *   quote: "selected text",
 *   prefix: "before ",
 *   suffix: " after",
 * });
 * ```
 */
export function useCreateHighlight(documentId: string): UseCreateHighlightResult {
  const queryClient = useQueryClient();

  const mutation = useMutation<HighlightItem, ClientError, CreateHighlightHookParams>({
    mutationFn: async (params) => {
      if (params.anchorType === "text") {
        return createHighlight({
          documentId,
          anchorType: "text",
          textStart: params.textStart,
          textEnd: params.textEnd,
        });
      } else {
        return createHighlight({
          documentId,
          anchorType: "pdf",
          textStart: params.textStart,
          textEnd: params.textEnd,
          pdfPageNumber: params.pdfPageNumber,
          pdfCharOffset: params.pdfCharOffset,
          quote: params.quote,
          prefix: params.prefix,
          suffix: params.suffix,
        });
      }
    },
    onSuccess: () => {
      // Invalidate the highlights list to trigger refetch
      queryClient.invalidateQueries({
        queryKey: documentHighlightsKey(documentId),
      });
    },
  });

  // Wrap mutateAsync in a stable callback
  const createHighlightFn = useCallback(
    async (params: CreateHighlightHookParams) => {
      return mutation.mutateAsync(params);
    },
    [mutation]
  );

  return {
    createHighlight: createHighlightFn,
    isPending: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error ?? null,
    data: mutation.data ?? null,
    reset: mutation.reset,
  };
}

