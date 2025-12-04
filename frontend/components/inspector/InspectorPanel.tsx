"use client";

import { useMemo, useCallback } from "react";
import { sortHighlights } from "@/lib/highlights/sort";
import type { HighlightItem } from "@/lib/generated-api";

/**
 * Props for the InspectorPanel component.
 *
 * The component is designed to be reusable and agnostic about how
 * scrolling/focusing works in the parent reader. The parent handles
 * the activeHighlightId state and responds to onHighlightClick.
 */
export interface InspectorPanelProps {
  /** Document ID being inspected */
  documentId: string;
  /** Array of highlights to display */
  highlights: HighlightItem[];
  /** Whether highlights are currently loading */
  isLoading?: boolean;
  /** Error message if loading failed */
  error?: string | null;
  /** Currently active/focused highlight ID */
  activeHighlightId?: string | null;
  /** Callback when a highlight is clicked in the inspector */
  onHighlightClick?: (highlightId: string) => void;
  /** Callback when a highlight is hovered (optional) */
  onHighlightHover?: (highlightId: string | null) => void;
  /** Currently hovered highlight ID (optional) */
  hoveredHighlightId?: string | null;
}

/**
 * InspectorPanel - Unified side panel for document inspection.
 *
 * Displays highlights in document order (sorted by position).
 * Clicking a highlight calls onHighlightClick, which the parent
 * uses to update activeHighlightId and scroll the reader.
 *
 * This component is presentational and does not:
 * - Fetch data (highlights are passed as props)
 * - Know how scrolling works (that's the reader's job)
 * - Use React Query directly
 *
 * Future: Will include tabs for Annotations and Chat.
 */
export function InspectorPanel({
  highlights,
  isLoading = false,
  error = null,
  activeHighlightId = null,
  onHighlightClick,
  onHighlightHover,
  hoveredHighlightId = null,
}: InspectorPanelProps) {
  // Sort highlights by document position for consistent display order
  // Uses centralized sorting logic from lib/highlights/sort.ts
  const sortedHighlights = useMemo(() => sortHighlights(highlights), [highlights]);

  // Handle click on a highlight row
  const handleClick = useCallback(
    (highlightId: string) => {
      onHighlightClick?.(highlightId);
    },
    [onHighlightClick]
  );

  // Handle mouse enter on a highlight row
  const handleMouseEnter = useCallback(
    (highlightId: string) => {
      onHighlightHover?.(highlightId);
    },
    [onHighlightHover]
  );

  // Handle mouse leave on a highlight row
  const handleMouseLeave = useCallback(() => {
    onHighlightHover?.(null);
  }, [onHighlightHover]);

  // Loading state (only show if no highlights yet)
  if (isLoading && highlights.length === 0) {
    return (
      <div
        data-testid="inspector-panel-loading"
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
        data-testid="inspector-panel-error"
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
        data-testid="inspector-panel-empty"
        className="text-sm text-gray-500 text-center py-8"
      >
        <p className="font-medium text-gray-700">No highlights yet</p>
        <p className="mt-1">
          Select text in the document to create your first highlight.
        </p>
      </div>
    );
  }

  // Highlights list
  return (
    <div data-testid="inspector-panel" className="space-y-2">
      {/* Header with count */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-500">
          {sortedHighlights.length} highlight
          {sortedHighlights.length !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Highlight list */}
      <div className="space-y-2" data-testid="inspector-panel-list">
        {sortedHighlights.map((highlight) => (
          <HighlightListItem
            key={highlight.id}
            highlight={highlight}
            isActive={highlight.id === activeHighlightId}
            isHovered={highlight.id === hoveredHighlightId}
            onClick={() => handleClick(highlight.id)}
            onMouseEnter={() => handleMouseEnter(highlight.id)}
            onMouseLeave={handleMouseLeave}
          />
        ))}
      </div>

      {/* Placeholder sections for future features */}
      <div className="mt-6 pt-4 border-t border-gray-200">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">
          Annotations
        </p>
        <p className="text-sm text-gray-400">
          {/* TODO: Wire up AnnotationsInspectorTab when highlight is selected */}
          Select a highlight to view annotations.
        </p>
      </div>

      <div className="mt-4 pt-4 border-t border-gray-200">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">
          Chat
        </p>
        <p className="text-sm text-gray-400">
          {/* TODO: Wire up chat interface */}
          Coming soon.
        </p>
      </div>
    </div>
  );
}

/**
 * Props for individual highlight list items.
 */
interface HighlightListItemProps {
  highlight: HighlightItem;
  isActive: boolean;
  isHovered: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

/**
 * Individual highlight item in the inspector list.
 */
function HighlightListItem({
  highlight,
  isActive,
  isHovered,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: HighlightListItemProps) {
  const displayQuote = truncateQuote(highlight.quote, 80);
  const positionLabel = getPositionLabel(highlight);
  const colorClass = getHighlightColorClass(highlight.color, isActive);

  return (
    <button
      data-testid={`inspector-highlight-${highlight.id}`}
      data-highlight-id={highlight.id}
      data-active={isActive}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
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
            ${colorClass}
          `}
        />
        <div className="flex-1 min-w-0">
          {/* Position label (page number for PDF, ordinal for text) */}
          {positionLabel && (
            <span className="text-xs text-gray-400 font-medium">
              {positionLabel}
            </span>
          )}
          <p className="text-sm text-gray-900 line-clamp-2">{displayQuote}</p>
          <p className="text-xs text-gray-500 mt-1">
            {formatDate(highlight.created_at)}
          </p>
        </div>
      </div>
    </button>
  );
}

/**
 * Truncate text to a maximum length with ellipsis.
 */
function truncateQuote(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 1) + "…";
}

/**
 * Get a position label for display (e.g., "p. 3" for PDF, or nothing for text).
 *
 * For PDF anchors, shows the page number.
 * For text anchors, currently shows nothing.
 *
 * TODO(future): For long HTML/EPUB documents, add position hints for text anchors:
 *   - Ordinal number (e.g., "#5") based on sorted position
 *   - Section/chapter info when structure_json is available
 *   - Percentage through document
 */
function getPositionLabel(highlight: HighlightItem): string | null {
  if (highlight.anchor_type === "pdf" && highlight.pdf_page_number != null) {
    return `p. ${highlight.pdf_page_number}`;
  }
  // Text anchors: no position label for now (see TODO above)
  return null;
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

