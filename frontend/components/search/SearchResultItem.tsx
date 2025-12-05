/**
 * Individual search result item component.
 *
 * Displays a single search result with:
 * - Result kind badge
 * - Text snippet
 * - Relevance score
 * - Position metadata (text offsets)
 *
 * This is a presentational component - no queries or navigation logic inside.
 */

import type { SearchResult } from "@/lib/search";

export interface SearchResultItemProps {
  /** The search result to display */
  result: SearchResult;
  /** Callback when the result is clicked */
  onClick: (result: SearchResult) => void;
}

/**
 * Format a similarity score as a percentage.
 */
function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

/**
 * Truncate text to a maximum length with ellipsis.
 */
function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + "...";
}

/**
 * Get a readable label for the result kind.
 */
function getKindLabel(kind: SearchResult["kind"]): string {
  switch (kind) {
    case "chunk":
      return "Chunk";
    default:
      return kind;
  }
}

/**
 * Get CSS classes for the kind badge.
 */
function getKindBadgeClasses(kind: SearchResult["kind"]): string {
  switch (kind) {
    case "chunk":
      return "bg-blue-100 text-blue-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

export function SearchResultItem({ result, onClick }: SearchResultItemProps) {
  const handleClick = () => {
    onClick(result);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick(result);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className="group p-4 border border-gray-200 rounded-lg hover:border-blue-300 hover:bg-blue-50/50 cursor-pointer transition-all focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
    >
      {/* Header row: kind badge + score */}
      <div className="flex items-center justify-between mb-2">
        <span
          className={`inline-block px-2 py-0.5 text-xs font-medium rounded-full ${getKindBadgeClasses(result.kind)}`}
        >
          {getKindLabel(result.kind)}
        </span>
        <span className="text-xs text-gray-500" title="Relevance score">
          {formatScore(result.score)} match
        </span>
      </div>

      {/* Text snippet */}
      <p className="text-sm text-gray-700 leading-relaxed mb-2">
        {truncateText(result.text, 300)}
      </p>

      {/* Metadata row */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        <span title="Character position in document">
          Position: {result.textStart.toLocaleString()} - {result.textEnd.toLocaleString()}
        </span>
        <span className="text-gray-300">•</span>
        <span
          className="font-mono truncate max-w-[200px]"
          title={`Document ID: ${result.documentId}`}
        >
          {result.documentId}
        </span>
      </div>
    </div>
  );
}

