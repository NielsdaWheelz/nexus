/**
 * React Query hooks for document operations.
 *
 * These hooks provide typed, cached access to document data with:
 * - Automatic caching and background refetching
 * - Loading and error states
 * - Infinite pagination for lists
 *
 * Use these hooks instead of manual useState/useEffect patterns.
 */

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import {
  fetchDocumentsList,
  fetchDocument,
  type DocumentsListResult,
} from "@/lib/api/documents";
import type { DocumentListItem } from "@/lib/generated-api";

/** Query key prefix for documents list queries. */
export const DOCUMENTS_LIST_KEY = ["documents"] as const;

/** Query key factory for document detail queries. */
export const documentDetailKey = (id: string) => ["document", id] as const;

/**
 * Options for useDocumentsList hook.
 */
export interface UseDocumentsListOptions {
  /** Filter by processing status (e.g., "ready", "processing"). */
  status?: string;
  /** Number of items per page. Defaults to 20. */
  pageSize?: number;
}

/**
 * Hook to fetch a paginated list of documents.
 *
 * Uses infinite query for "load more" pagination pattern.
 *
 * @param options - Optional status filter and page size
 * @returns Infinite query result with pages of documents
 *
 * @example
 * ```tsx
 * const { data, isLoading, hasNextPage, fetchNextPage } = useDocumentsList();
 *
 * const documents = data?.pages.flatMap(page => page.items) ?? [];
 *
 * return (
 *   <div>
 *     {documents.map(doc => <DocumentRow key={doc.id} doc={doc} />)}
 *     {hasNextPage && <button onClick={() => fetchNextPage()}>Load More</button>}
 *   </div>
 * );
 * ```
 */
export function useDocumentsList(options?: UseDocumentsListOptions) {
  const pageSize = options?.pageSize ?? 20;

  return useInfiniteQuery<DocumentsListResult, Error>({
    queryKey: [...DOCUMENTS_LIST_KEY, { status: options?.status ?? null }],
    queryFn: async ({ pageParam }) => {
      return fetchDocumentsList({
        cursor: pageParam as string | undefined,
        limit: pageSize,
        status: options?.status,
      });
    },
    getNextPageParam: (lastPage) => {
      return lastPage.has_more ? lastPage.next_cursor : undefined;
    },
    initialPageParam: undefined as string | undefined,
  });
}

/**
 * Hook to fetch a single document by ID.
 *
 * @param documentId - The document ID to fetch. Pass null/undefined to disable.
 * @returns Query result with document data
 *
 * @example
 * ```tsx
 * const { data: document, isLoading, error } = useDocumentDetail(documentId);
 *
 * if (isLoading) return <Spinner />;
 * if (error) return <ErrorMessage error={error} />;
 * if (!document) return null;
 *
 * return <DocumentView document={document} />;
 * ```
 */
export function useDocumentDetail(documentId: string | null | undefined) {
  return useQuery<DocumentListItem, Error>({
    queryKey: documentDetailKey(documentId ?? ""),
    queryFn: async () => {
      if (!documentId) {
        throw new Error("documentId is required");
      }
      return fetchDocument(documentId);
    },
    enabled: !!documentId,
  });
}

