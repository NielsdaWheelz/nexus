"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSearch, navigateToSearchResult, type SearchResult } from "@/lib/search";
import { SearchResultList } from "@/components/search";
import { useUIStore } from "@/lib/state/ui";

/**
 * Debounce delay for search input (ms).
 */
const DEBOUNCE_MS = 300;

/**
 * Custom hook for debounced value.
 */
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}

/**
 * Search page.
 *
 * Features:
 * - URL-based query state (/app/search?q=...)
 * - Debounced search input
 * - Results list with loading/error/empty states
 * - Click-to-navigate to document reader
 */
export default function SearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setActiveHighlightId = useUIStore((s) => s.setActiveHighlightId);

  // Initialize input from URL query param
  const initialQuery = searchParams.get("q") ?? "";
  const [inputValue, setInputValue] = useState(initialQuery);

  // Debounce the input value for search
  const debouncedQuery = useDebounce(inputValue, DEBOUNCE_MS);

  // Track whether user has initiated a search
  const [hasSearched, setHasSearched] = useState(initialQuery.length > 0);

  // Perform search with debounced query
  const { results, isLoading, error } = useSearch({
    query: debouncedQuery,
    limit: 20,
  });

  // Update URL when debounced query changes
  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    if (trimmed.length > 0) {
      // Update URL without navigation
      const newUrl = `/app/search?q=${encodeURIComponent(trimmed)}`;
      window.history.replaceState({}, "", newUrl);
      setHasSearched(true);
    } else if (hasSearched) {
      // Clear URL param if query is empty but we've searched before
      window.history.replaceState({}, "", "/app/search");
    }
  }, [debouncedQuery, hasSearched]);

  // Handle input change
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
  };

  // Handle form submit (for Enter key)
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Search happens automatically via debounce, but mark as searched
    if (inputValue.trim().length > 0) {
      setHasSearched(true);
    }
  };

  // Handle result click
  const handleResultClick = useCallback(
    (result: SearchResult) => {
      navigateToSearchResult(result, router, setActiveHighlightId);
    },
    [router, setActiveHighlightId]
  );

  // Handle clear search
  const handleClear = () => {
    setInputValue("");
    setHasSearched(false);
    window.history.replaceState({}, "", "/app/search");
  };

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Search</h1>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="mb-8">
        <div className="relative">
          {/* Search icon */}
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <svg
              className="h-5 w-5 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>

          {/* Input */}
          <input
            type="text"
            value={inputValue}
            onChange={handleInputChange}
            placeholder="Search your documents..."
            className="block w-full pl-10 pr-10 py-3 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            autoFocus
          />

          {/* Clear button */}
          {inputValue.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
            >
              <svg
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          )}
        </div>

        {/* Helper text */}
        <p className="mt-2 text-xs text-gray-500">
          Semantic search across all document content. Results are ranked by relevance.
        </p>
      </form>

      {/* Results */}
      <SearchResultList
        results={results}
        isLoading={isLoading}
        error={error}
        hasSearched={hasSearched && debouncedQuery.trim().length > 0}
        onResultClick={handleResultClick}
      />
    </div>
  );
}

