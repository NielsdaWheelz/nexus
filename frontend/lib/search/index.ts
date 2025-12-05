/**
 * Search module exports.
 *
 * This module provides semantic search functionality:
 * - useSearch hook for React Query integration
 * - Navigation utilities for search result handling
 */

// Hook
export { useSearch, SEARCH_KEY, searchQueryKey } from "./useSearch";
export type {
  UseSearchOptions,
  UseSearchResult,
  SearchResult,
} from "./useSearch";

// Navigation
export {
  navigateToSearchResult,
  getSearchResultUrl,
} from "./navigation";
export type { SetActiveHighlightId } from "./navigation";

