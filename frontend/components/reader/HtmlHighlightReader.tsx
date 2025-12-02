"use client";

import { useMemo, useCallback, useRef, useEffect } from "react";
import { useUIStore } from "@/lib/state/ui";
import type { HighlightItem } from "@/lib/api/highlights";

/**
 * Text segment types for the rendering algorithm.
 *
 * The renderer splits canonical text into segments:
 * - "text": Plain text with no highlight
 * - "highlight": Text covered by a highlight span
 */
type TextSegment =
  | { kind: "text"; text: string }
  | { kind: "highlight"; text: string; highlightId: string };

/**
 * Props for the HtmlHighlightReader component.
 */
export interface HtmlHighlightReaderProps {
  /** The canonical text content to render */
  canonicalText: string;
  /** Array of highlights to render on the text */
  highlights: HighlightItem[];
}

/**
 * Validate and normalize highlight ranges.
 *
 * - Clamps ranges to [0, textLength]
 * - Filters out invalid ranges where start >= end after clamping
 *
 * @param highlights - Raw highlights from API
 * @param textLength - Length of canonical text in characters (codepoints)
 * @returns Validated highlights with clamped ranges
 */
function validateAndClampHighlights(
  highlights: HighlightItem[],
  textLength: number
): HighlightItem[] {
  return highlights
    .map((h) => ({
      ...h,
      text_start: Math.max(0, Math.min(h.text_start, textLength)),
      text_end: Math.max(0, Math.min(h.text_end, textLength)),
    }))
    .filter((h) => h.text_start < h.text_end);
}

/**
 * Sort highlights for deterministic rendering.
 *
 * Order: text_start ASC, text_end ASC, id ASC
 *
 * @param highlights - Highlights to sort
 * @returns Sorted copy of highlights
 */
function sortHighlights(highlights: HighlightItem[]): HighlightItem[] {
  return [...highlights].sort((a, b) => {
    if (a.text_start !== b.text_start) return a.text_start - b.text_start;
    if (a.text_end !== b.text_end) return a.text_end - b.text_end;
    return a.id.localeCompare(b.id);
  });
}

/**
 * Build text segments from canonical text and highlights.
 *
 * OVERLAP POLICY (v1): "First wins"
 * When highlights overlap, the first highlight (by sort order) takes
 * precedence. Later highlights that would overlap are skipped entirely.
 * This avoids nested spans and keeps rendering simple.
 *
 * ALGORITHM:
 * 1. Maintain a cursor into canonical text
 * 2. Iterate sorted highlights:
 *    - If highlight starts before cursor (overlap), skip it
 *    - If cursor < highlight.start, emit plain text segment
 *    - Emit highlight segment
 *    - Advance cursor to highlight.end
 * 3. Emit trailing plain text if any
 *
 * TIME COMPLEXITY: O(n) where n = number of highlights
 * No nested loops, no reparsing.
 *
 * NOTE: text_start and text_end are character offsets (codepoint indices),
 * which align with JavaScript string indices. This is consistent with
 * Python string slicing used in the backend.
 *
 * @param text - Canonical text
 * @param highlights - Sorted, validated highlights
 * @returns Array of text segments for rendering
 */
function buildSegments(text: string, highlights: HighlightItem[]): TextSegment[] {
  const segments: TextSegment[] = [];
  let cursor = 0;

  for (const h of highlights) {
    // Skip highlights that would overlap with already-processed regions
    // (first wins policy)
    if (h.text_start < cursor) {
      continue;
    }

    // Add plain text before this highlight
    if (cursor < h.text_start) {
      segments.push({
        kind: "text",
        text: text.slice(cursor, h.text_start),
      });
    }

    // Add the highlight segment
    segments.push({
      kind: "highlight",
      text: text.slice(h.text_start, h.text_end),
      highlightId: h.id,
    });

    cursor = h.text_end;
  }

  // Add trailing text after last highlight
  if (cursor < text.length) {
    segments.push({
      kind: "text",
      text: text.slice(cursor),
    });
  }

  return segments;
}

/**
 * HtmlHighlightReader - Read-only highlight renderer for HTML/EPUB documents.
 *
 * Renders canonical text with <span> wrappers for highlights.
 * Designed for efficiency with hundreds of highlights.
 *
 * Features:
 * - O(n) segment algorithm (no quadratic splitting)
 * - Click/hover handlers for highlight interaction
 * - Integrates with UI store for active/hovered state
 * - Data attributes for test selection and scroll targeting
 *
 * Offset Semantics (v1):
 * - text_start and text_end are character offsets (codepoint indices)
 * - These align with JavaScript string indices and Python string slicing
 * - Full Unicode support via consistent string semantics across frontend/backend
 *
 * Limitations (v1):
 * - Treats canonical text as plain text (no HTML preservation)
 * - Overlapping highlights use "first wins" policy
 */
export function HtmlHighlightReader({
  canonicalText,
  highlights,
}: HtmlHighlightReaderProps) {
  const activeHighlightId = useUIStore((s) => s.activeHighlightId);
  const hoveredHighlightId = useUIStore((s) => s.hoveredHighlightId);
  const setActiveHighlightId = useUIStore((s) => s.setActiveHighlightId);
  const setHoveredHighlightId = useUIStore((s) => s.setHoveredHighlightId);

  // Ref to the container for scroll-to-highlight functionality
  const containerRef = useRef<HTMLDivElement>(null);

  // Memoize segment computation (expensive for large texts)
  const segments = useMemo(() => {
    if (!canonicalText || highlights.length === 0) {
      // No highlights: return single text segment
      return canonicalText
        ? [{ kind: "text" as const, text: canonicalText }]
        : [];
    }

    const validated = validateAndClampHighlights(highlights, canonicalText.length);
    const sorted = sortHighlights(validated);
    return buildSegments(canonicalText, sorted);
  }, [canonicalText, highlights]);

  // Handle click on a highlight span
  const handleHighlightClick = useCallback(
    (highlightId: string) => {
      setActiveHighlightId(highlightId);
    },
    [setActiveHighlightId]
  );

  // Handle mouse enter on a highlight span
  const handleHighlightMouseEnter = useCallback(
    (highlightId: string) => {
      setHoveredHighlightId(highlightId);
    },
    [setHoveredHighlightId]
  );

  // Handle mouse leave on a highlight span
  const handleHighlightMouseLeave = useCallback(() => {
    setHoveredHighlightId(null);
  }, [setHoveredHighlightId]);

  // Scroll to active highlight when it changes (triggered externally)
  useEffect(() => {
    if (!activeHighlightId || !containerRef.current) return;

    const element = containerRef.current.querySelector(
      `[data-highlight-id="${activeHighlightId}"]`
    );
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeHighlightId]);

  // Empty state
  if (!canonicalText) {
    return (
      <div
        data-testid="html-reader"
        className="text-gray-400 text-center py-8"
      >
        No content available
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      data-testid="html-reader"
      className="prose prose-sm max-w-none leading-relaxed whitespace-pre-wrap"
    >
      {segments.map((segment, i) =>
        segment.kind === "text" ? (
          <span key={i}>{segment.text}</span>
        ) : (
          <span
            key={i}
            data-highlight-id={segment.highlightId}
            onClick={() => handleHighlightClick(segment.highlightId)}
            onMouseEnter={() => handleHighlightMouseEnter(segment.highlightId)}
            onMouseLeave={handleHighlightMouseLeave}
            className={`
              cursor-pointer transition-colors rounded-sm px-0.5 -mx-0.5
              ${
                segment.highlightId === activeHighlightId
                  ? "bg-yellow-300 ring-2 ring-yellow-500 ring-offset-1"
                  : segment.highlightId === hoveredHighlightId
                  ? "bg-yellow-200"
                  : "bg-yellow-100"
              }
            `}
          >
            {segment.text}
          </span>
        )
      )}
    </div>
  );
}

/**
 * Scroll to a specific highlight in the reader.
 *
 * Utility function that can be called from outside the component
 * (e.g., from the inspector panel) to scroll a highlight into view.
 *
 * @param highlightId - The highlight ID to scroll to
 */
export function scrollToHighlight(highlightId: string) {
  const element = document.querySelector(
    `[data-highlight-id="${highlightId}"]`
  );
  if (element) {
    element.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

