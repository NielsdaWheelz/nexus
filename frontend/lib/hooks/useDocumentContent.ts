/**
 * React Query hooks for document content.
 *
 * This module provides:
 * - useDocumentContent: Fetch canonical text for a document
 */

import { useQuery } from "@tanstack/react-query";
import { fetchDocumentContent } from "@/lib/api/content";
import type { DocumentContentResponse } from "@/lib/api/content";
import type { ClientError } from "@/lib/api/http";

/**
 * Query key factory for document content.
 */
export const documentContentKey = (documentId: string) =>
  ["document", documentId, "content"] as const;

/**
 * Hook to fetch document content (canonical text).
 *
 * @param documentId - Typed document ID (doc_<uuid>)
 * @param options - Query options
 * @returns Query result with content data
 *
 * @example
 * ```tsx
 * const { data, isLoading, error } = useDocumentContent("doc_abc123", {
 *   enabled: document.processing_status === "ready",
 * });
 *
 * if (data) {
 *   console.log(data.canonical_text);
 * }
 * ```
 */
export function useDocumentContent(
  documentId: string,
  options?: {
    enabled?: boolean;
  }
) {
  return useQuery<DocumentContentResponse, ClientError>({
    queryKey: documentContentKey(documentId),
    queryFn: () => fetchDocumentContent(documentId),
    enabled: options?.enabled ?? !!documentId,
    // Content is unlikely to change, so we can cache it aggressively
    staleTime: 5 * 60 * 1000, // 5 minutes
    // Don't refetch on window focus for large content
    refetchOnWindowFocus: false,
  });
}

