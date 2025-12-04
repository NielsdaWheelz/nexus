/**
 * React Query hooks for annotation operations.
 *
 * These hooks provide typed, cached access to annotation data with:
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
  listAnnotationsForHighlight,
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
  type AnnotationsListResult,
  type AnnotationItem,
  type CreateAnnotationParams,
  type UpdateAnnotationParams,
} from "@/lib/api/annotations";
import type { ClientError } from "@/lib/api/http";

/** Query key factory for highlight annotations queries. */
export const highlightAnnotationsKey = (highlightId: string) =>
  ["annotations", { highlightId }] as const;

/**
 * Options for useAnnotations hook.
 */
export interface UseAnnotationsOptions {
  /** Whether the query should execute. Defaults to true. */
  enabled?: boolean;
  /** Number of items per page. Defaults to 100. */
  pageSize?: number;
}

/**
 * Return type for useAnnotations hook.
 */
export interface UseAnnotationsResult {
  /** Flattened array of all annotations loaded so far */
  annotations: AnnotationItem[];
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
 * Hook to fetch paginated annotations for a highlight.
 *
 * Uses infinite query for automatic pagination handling.
 * Annotations are flattened into a single array for convenient access.
 *
 * @param highlightId - The highlight ID to fetch annotations for
 * @param options - Optional enabled flag and page size
 * @returns Flattened annotations array and query state
 *
 * @example
 * ```tsx
 * const { annotations, isLoading, hasNextPage, fetchNextPage } =
 *   useAnnotations(highlightId);
 *
 * return (
 *   <div>
 *     {annotations.map(a => <AnnotationItem key={a.id} annotation={a} />)}
 *     {hasNextPage && <button onClick={fetchNextPage}>Load More</button>}
 *   </div>
 * );
 * ```
 */
export function useAnnotations(
  highlightId: string,
  options?: UseAnnotationsOptions
): UseAnnotationsResult {
  const pageSize = options?.pageSize ?? 100;
  const enabled = options?.enabled ?? true;

  const query = useInfiniteQuery<AnnotationsListResult, Error>({
    queryKey: highlightAnnotationsKey(highlightId),
    queryFn: async ({ pageParam }) => {
      return listAnnotationsForHighlight(
        highlightId,
        pageParam as string | undefined,
        pageSize
      );
    },
    getNextPageParam: (lastPage) => {
      return lastPage.has_more ? lastPage.next_cursor : undefined;
    },
    initialPageParam: undefined as string | undefined,
    enabled: enabled && !!highlightId,
  });

  // Flatten pages into a single array
  const annotations = useMemo(() => {
    return query.data?.pages.flatMap((page) => page.items) ?? [];
  }, [query.data?.pages]);

  return {
    annotations,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    hasNextPage: query.hasNextPage ?? false,
    fetchNextPage: query.fetchNextPage,
    isFetchingNextPage: query.isFetchingNextPage,
  };
}

/**
 * Return type for useCreateAnnotation hook.
 */
export interface UseCreateAnnotationResult {
  /** Trigger annotation creation */
  createAnnotation: (content: string) => Promise<AnnotationItem>;
  /** Whether a creation is in progress */
  isPending: boolean;
  /** Whether the last creation failed */
  isError: boolean;
  /** Error from the last creation attempt */
  error: ClientError | null;
  /** The last successfully created annotation */
  data: AnnotationItem | null;
  /** Reset the mutation state */
  reset: () => void;
}

/**
 * Hook for creating annotations on a highlight.
 *
 * On successful creation:
 * - Invalidates the highlight annotations query to refresh the list
 * - Returns the newly created annotation
 *
 * @param highlightId - The highlight ID to create annotations on
 * @returns Mutation controls and state
 *
 * @example
 * ```tsx
 * const { createAnnotation, isPending, isError } = useCreateAnnotation(highlightId);
 *
 * const handleSubmit = async (content: string) => {
 *   try {
 *     const annotation = await createAnnotation(content);
 *     console.log("Created:", annotation.id);
 *   } catch (error) {
 *     console.error("Failed:", error);
 *   }
 * };
 * ```
 */
export function useCreateAnnotation(highlightId: string): UseCreateAnnotationResult {
  const queryClient = useQueryClient();

  const mutation = useMutation<AnnotationItem, ClientError, string>({
    mutationFn: async (content) => {
      return createAnnotation({
        highlightId,
        content,
      });
    },
    onSuccess: () => {
      // Invalidate the annotations list to trigger refetch
      queryClient.invalidateQueries({
        queryKey: highlightAnnotationsKey(highlightId),
      });
    },
  });

  // Wrap mutateAsync in a stable callback
  const createAnnotationFn = useCallback(
    async (content: string) => {
      return mutation.mutateAsync(content);
    },
    [mutation]
  );

  return {
    createAnnotation: createAnnotationFn,
    isPending: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error ?? null,
    data: mutation.data ?? null,
    reset: mutation.reset,
  };
}

/**
 * Return type for useUpdateAnnotation hook.
 */
export interface UseUpdateAnnotationResult {
  /** Trigger annotation update */
  updateAnnotation: (params: UpdateAnnotationParams) => Promise<AnnotationItem>;
  /** Whether an update is in progress */
  isPending: boolean;
  /** Whether the last update failed */
  isError: boolean;
  /** Error from the last update attempt */
  error: ClientError | null;
  /** The last successfully updated annotation */
  data: AnnotationItem | null;
  /** Reset the mutation state */
  reset: () => void;
}

/**
 * Hook for updating annotations on a highlight.
 *
 * On successful update:
 * - Invalidates the highlight annotations query to refresh the list
 * - Returns the updated annotation
 *
 * @param highlightId - The highlight ID (used for cache invalidation)
 * @returns Mutation controls and state
 *
 * @example
 * ```tsx
 * const { updateAnnotation, isPending } = useUpdateAnnotation(highlightId);
 *
 * const handleSave = async (annotationId: string, content: string) => {
 *   await updateAnnotation({ annotationId, content });
 * };
 * ```
 */
export function useUpdateAnnotation(highlightId: string): UseUpdateAnnotationResult {
  const queryClient = useQueryClient();

  const mutation = useMutation<AnnotationItem, ClientError, UpdateAnnotationParams>({
    mutationFn: async (params) => {
      return updateAnnotation(params);
    },
    onSuccess: () => {
      // Invalidate the annotations list to trigger refetch
      queryClient.invalidateQueries({
        queryKey: highlightAnnotationsKey(highlightId),
      });
    },
  });

  // Wrap mutateAsync in a stable callback
  const updateAnnotationFn = useCallback(
    async (params: UpdateAnnotationParams) => {
      return mutation.mutateAsync(params);
    },
    [mutation]
  );

  return {
    updateAnnotation: updateAnnotationFn,
    isPending: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error ?? null,
    data: mutation.data ?? null,
    reset: mutation.reset,
  };
}

/**
 * Return type for useDeleteAnnotation hook.
 */
export interface UseDeleteAnnotationResult {
  /** Trigger annotation deletion */
  deleteAnnotation: (annotationId: string) => Promise<void>;
  /** Whether a deletion is in progress */
  isPending: boolean;
  /** Whether the last deletion failed */
  isError: boolean;
  /** Error from the last deletion attempt */
  error: ClientError | null;
  /** Reset the mutation state */
  reset: () => void;
}

/**
 * Hook for deleting annotations on a highlight.
 *
 * On successful deletion:
 * - Invalidates the highlight annotations query to refresh the list
 *
 * @param highlightId - The highlight ID (used for cache invalidation)
 * @returns Mutation controls and state
 *
 * @example
 * ```tsx
 * const { deleteAnnotation, isPending } = useDeleteAnnotation(highlightId);
 *
 * const handleDelete = async (annotationId: string) => {
 *   if (window.confirm("Delete this annotation?")) {
 *     await deleteAnnotation(annotationId);
 *   }
 * };
 * ```
 */
export function useDeleteAnnotation(highlightId: string): UseDeleteAnnotationResult {
  const queryClient = useQueryClient();

  const mutation = useMutation<void, ClientError, string>({
    mutationFn: async (annotationId) => {
      return deleteAnnotation(annotationId);
    },
    onSuccess: () => {
      // Invalidate the annotations list to trigger refetch
      queryClient.invalidateQueries({
        queryKey: highlightAnnotationsKey(highlightId),
      });
    },
  });

  // Wrap mutateAsync in a stable callback
  const deleteAnnotationFn = useCallback(
    async (annotationId: string) => {
      return mutation.mutateAsync(annotationId);
    },
    [mutation]
  );

  return {
    deleteAnnotation: deleteAnnotationFn,
    isPending: mutation.isPending,
    isError: mutation.isError,
    error: mutation.error ?? null,
    reset: mutation.reset,
  };
}

