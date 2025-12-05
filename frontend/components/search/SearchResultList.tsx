/**
 * Search results list component.
 *
 * Handles rendering of search results with:
 * - Loading state
 * - Error state
 * - Empty state
 * - Results list
 *
 * This is a presentational component - no queries inside.
 */

import type { SearchResult } from "@/lib/search";
import type { ClientError } from "@/lib/api/http";
import { SearchResultItem } from "./SearchResultItem";

export interface SearchResultListProps {
  /** Search results to display */
  results: SearchResult[];
  /** Whether the search is currently loading */
  isLoading: boolean;
  /** Error from the search (if any) */
  error: ClientError | null;
  /** Whether a search has been executed (query was non-empty) */
  hasSearched: boolean;
  /** Callback when a result is clicked */
  onResultClick: (result: SearchResult) => void;
}

/**
 * Loading spinner component.
 */
function LoadingSpinner() {
  return (
    <div className="flex justify-center items-center py-12">
      <div className="text-center">
        <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        <p className="mt-3 text-sm text-gray-600">Searching...</p>
      </div>
    </div>
  );
}

/**
 * Error display component.
 */
function ErrorDisplay({ error }: { error: ClientError }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-red-900 mb-1">Search failed</h3>
      <p className="text-sm text-red-700">{error.message}</p>
      {error.code && (
        <p className="text-xs text-red-600 mt-1">Error code: {error.code}</p>
      )}
    </div>
  );
}

/**
 * Empty state component (after search with no results).
 */
function EmptyResults() {
  return (
    <div className="text-center py-12">
      <div className="text-gray-400 mb-3">
        <svg
          className="mx-auto h-12 w-12"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
      </div>
      <p className="text-gray-600 font-medium">No results found</p>
      <p className="text-sm text-gray-500 mt-1">
        Try a different search query or check your spelling
      </p>
    </div>
  );
}

/**
 * Initial state component (before any search).
 */
function InitialState() {
  return (
    <div className="text-center py-12">
      <div className="text-gray-400 mb-3">
        <svg
          className="mx-auto h-12 w-12"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
      </div>
      <p className="text-gray-600 font-medium">Search your documents</p>
      <p className="text-sm text-gray-500 mt-1">
        Enter a query to find relevant content across all your documents
      </p>
    </div>
  );
}

export function SearchResultList({
  results,
  isLoading,
  error,
  hasSearched,
  onResultClick,
}: SearchResultListProps) {
  // Loading state
  if (isLoading) {
    return <LoadingSpinner />;
  }

  // Error state
  if (error) {
    return <ErrorDisplay error={error} />;
  }

  // Initial state (no search yet)
  if (!hasSearched) {
    return <InitialState />;
  }

  // Empty results state
  if (results.length === 0) {
    return <EmptyResults />;
  }

  // Results list
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 mb-4">
        {results.length} result{results.length !== 1 ? "s" : ""} found
      </p>
      {results.map((result) => (
        <SearchResultItem
          key={result.id}
          result={result}
          onClick={onResultClick}
        />
      ))}
    </div>
  );
}

