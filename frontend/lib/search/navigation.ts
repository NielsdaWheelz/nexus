/**
 * Search result navigation utilities.
 *
 * This module handles navigation from search results to the appropriate
 * document reader, including setting up any necessary UI state.
 */

import type { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";
import type { SearchResult } from "./useSearch";

/**
 * UI store setter type for activeHighlightId.
 * Matches the shape from lib/state/ui.ts.
 */
export type SetActiveHighlightId = (id: string | null) => void;

/**
 * Navigate to the document reader for a search result.
 *
 * Behavior based on result kind:
 * - chunk: Opens document reader at the top (no highlight scrolling)
 *
 * Future extensions could include:
 * - highlight: Open document reader and scroll to highlight via activeHighlightId
 * - document: Open document reader at the top
 *
 * @param result - The search result to navigate to
 * @param router - Next.js App Router instance
 * @param setActiveHighlightId - Optional store setter for highlight scrolling
 *
 * @example
 * ```tsx
 * const router = useRouter();
 * const setActiveHighlightId = useUIStore((s) => s.setActiveHighlightId);
 *
 * const handleResultClick = (result: SearchResult) => {
 *   navigateToSearchResult(result, router, setActiveHighlightId);
 * };
 * ```
 */
export function navigateToSearchResult(
  result: SearchResult,
  router: AppRouterInstance,
  setActiveHighlightId?: SetActiveHighlightId
): void {
  // Clear any active highlight before navigating
  if (setActiveHighlightId) {
    setActiveHighlightId(null);
  }

  // Navigate to the document reader
  // The document ID is typed (doc_<uuid>), which is what the route expects
  router.push(`/app/documents/${result.documentId}`);
}

/**
 * Build the URL for a search result without navigating.
 *
 * Useful for:
 * - Rendering links with href
 * - Copying URLs
 * - Opening in new tab
 *
 * @param result - The search result
 * @returns URL path to the document
 */
export function getSearchResultUrl(result: SearchResult): string {
  return `/app/documents/${result.documentId}`;
}

