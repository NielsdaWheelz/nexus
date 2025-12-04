"use client";

import { useCallback } from "react";
import { useUIStore } from "@/lib/state/ui";
import { scrollToHighlight } from "./HtmlHighlightReader";
import type { HighlightItem } from "@/lib/api/highlights";

/**
 * Props for the HighlightsInspectorTab component.
 */
export interface HighlightsInspectorTabProps {
  /** Array of highlights to display */
  highlights: HighlightItem[];
  /** Whether highlights are currently loading */
  isLoading?: boolean;
  /** Error message if loading failed */
  error?: string | null;
}

/**
 * Truncate text to a maximum length with ellipsis.
 */
function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 1) + "…";
}

/**
 * Format a date string for display.
 */
function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Get the display quote from a highlight.
 * Now that HighlightItem includes quote, we just truncate it.
 */
function getDisplayQuote(highlight: HighlightItem): string {
  return truncate(highlight.quote, 80);
}

/**
 * Get Tailwind color class for highlight marker based on highlight color.
 */
function getHighlightColorClass(color: string, isActive: boolean): string {
  const colorMap: Record<string, { active: string; inactive: string }> = {
    yellow: { active: "bg-yellow-400", inactive: "bg-yellow-200" },
    blue: { active: "bg-blue-400", inactive: "bg-blue-200" },
    green: { active: "bg-green-400", inactive: "bg-green-200" },
    pink: { active: "bg-pink-400", inactive: "bg-pink-200" },
    purple: { active: "bg-purple-400", inactive: "bg-purple-200" },
  };
  
  const colors = colorMap[color] || colorMap.yellow;
  return isActive ? colors.active : colors.inactive;
}

/**
 * HighlightsInspectorTab - Inspector panel content for the highlights tab.
 *
 * Displays a scrollable list of highlights with:
 * - Quote snippet (from highlight.quote field)
 * - Creation date
 * - Active/hover state styling
 * - Click to focus highlight in reader
 */
export function HighlightsInspectorTab({
  highlights,
  isLoading = false,
  error = null,
}: HighlightsInspectorTabProps) {
  const activeHighlightId = useUIStore((s) => s.activeHighlightId);
  const hoveredHighlightId = useUIStore((s) => s.hoveredHighlightId);
  const setActiveHighlightId = useUIStore((s) => s.setActiveHighlightId);
  const setHoveredHighlightId = useUIStore((s) => s.setHoveredHighlightId);

  // Handle click on a highlight row
  const handleClick = useCallback(
    (highlightId: string) => {
      setActiveHighlightId(highlightId);
      // Scroll the reader to this highlight
      scrollToHighlight(highlightId);
    },
    [setActiveHighlightId]
  );

  // Handle mouse enter on a highlight row
  const handleMouseEnter = useCallback(
    (highlightId: string) => {
      setHoveredHighlightId(highlightId);
    },
    [setHoveredHighlightId]
  );

  // Handle mouse leave on a highlight row
  const handleMouseLeave = useCallback(() => {
    setHoveredHighlightId(null);
  }, [setHoveredHighlightId]);

  // Loading state
  if (isLoading && highlights.length === 0) {
    return (
      <div
        data-testid="highlights-inspector-loading"
        className="text-sm text-gray-500 text-center py-8"
      >
        <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-gray-400 mb-2"></div>
        <p>Loading highlights...</p>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        data-testid="highlights-inspector-error"
        className="text-sm text-red-600 bg-red-50 rounded-lg p-4"
      >
        <p className="font-medium">Failed to load highlights</p>
        <p className="text-red-500 mt-1">{error}</p>
      </div>
    );
  }

  // Empty state
  if (highlights.length === 0) {
    return (
      <div
        data-testid="highlights-inspector-empty"
        className="text-sm text-gray-500 text-center py-8"
      >
        <p className="font-medium text-gray-700">No highlights yet</p>
        <p className="mt-1">
          Select text in the document to create your first highlight.
        </p>
      </div>
    );
  }

  // List of highlights
  return (
    <div data-testid="highlights-inspector-list" className="space-y-2">
      <p className="text-xs text-gray-500 mb-3">
        {highlights.length} highlight{highlights.length !== 1 ? "s" : ""}
      </p>

      {highlights.map((highlight) => {
        const isActive = highlight.id === activeHighlightId;
        const isHovered = highlight.id === hoveredHighlightId;

        return (
          <button
            key={highlight.id}
            data-highlight-id={highlight.id}
            data-active={isActive}
            onClick={() => handleClick(highlight.id)}
            onMouseEnter={() => handleMouseEnter(highlight.id)}
            onMouseLeave={handleMouseLeave}
            className={`
              w-full text-left p-3 rounded-lg border transition-all
              ${
                isActive
                  ? "bg-yellow-50 border-yellow-300 ring-2 ring-yellow-400 ring-offset-1"
                  : isHovered
                  ? "bg-gray-100 border-gray-300"
                  : "bg-white border-gray-200 hover:bg-gray-50"
              }
            `}
          >
            {/* Quote snippet with highlight marker (color from highlight) */}
            <div className="flex items-start gap-2">
              <div
                className={`
                  w-1 h-full min-h-[2rem] rounded-full flex-shrink-0
                  ${getHighlightColorClass(highlight.color, isActive)}
                `}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-900 line-clamp-2">
                  {getDisplayQuote(highlight)}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {formatDate(highlight.created_at)}
                </p>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

