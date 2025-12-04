/**
 * React Query hook for fetching document blob (binary data).
 *
 * This module provides:
 * - useDocumentBlob: Fetch raw PDF/EPUB/HTML binary for a document
 */

import { useQuery } from "@tanstack/react-query";
import { fetchDocumentBlob } from "@/lib/api/documents";
import type { ClientError } from "@/lib/api/http";

/**
 * Query key factory for document blob queries.
 */
export const documentBlobKey = (documentId: string) =>
  ["documentBlob", { documentId }] as const;

/**
 * Hook to fetch document blob (binary data).
 *
 * Returns the raw file content (PDF, EPUB, HTML) as an ArrayBuffer.
 * Used by PDF.js and other renderers that need the original binary.
 *
 * @param documentId - Typed document ID (doc_<uuid>), or null/undefined to disable
 * @returns Query result with ArrayBuffer data
 *
 * @example
 * ```tsx
 * const { data: pdfBuffer, isLoading, error } = useDocumentBlob(documentId);
 *
 * if (pdfBuffer) {
 *   // Load into PDF.js
 *   const pdf = await pdfjsLib.getDocument({ data: pdfBuffer }).promise;
 * }
 * ```
 */
export function useDocumentBlob(documentId: string | null | undefined) {
  return useQuery<ArrayBuffer, ClientError>({
    queryKey: documentBlobKey(documentId ?? ""),
    queryFn: async () => {
      if (!documentId) {
        throw new Error("documentId is required");
      }
      return fetchDocumentBlob(documentId);
    },
    enabled: !!documentId,
    // PDFs are large and unlikely to change, cache aggressively
    staleTime: 10 * 60 * 1000, // 10 minutes
    // Don't refetch on window focus for large binary content
    refetchOnWindowFocus: false,
    // Don't retry on failure (large files + retry = bad UX)
    retry: false,
  });
}

