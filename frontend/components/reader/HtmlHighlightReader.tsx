"use client";

import { useMemo, useCallback, useRef, useEffect, useState } from "react";
import { useUIStore } from "@/lib/state/ui";
import { useCreateHighlight } from "@/lib/hooks/useHighlights";
import { resolveSelectionToCanonicalOffsets } from "@/lib/anchoring/core";
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

/** Maximum selection length in characters for highlight creation */
const MAX_SELECTION_LENGTH = 10000;

/**
 * Props for the HtmlHighlightReader component.
 */
export interface HtmlHighlightReaderProps {
  /** The canonical text content to render */
  canonicalText: string;
  /** Array of highlights to render on the text */
  highlights: HighlightItem[];
  /** Document ID for highlight creation (required for selection handling) */
  documentId?: string;
  /** Callback when a highlight is created */
  onHighlightCreated?: (highlight: HighlightItem) => void;
  /** Callback when highlight creation fails */
  onHighlightError?: (error: Error) => void;
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
 * Pending selection state for highlight creation.
 */
interface PendingSelection {
  /** Start offset in canonical text */
  textStart: number;
  /** End offset in canonical text */
  textEnd: number;
  /** The selected quote text */
  quote: string;
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
 * - Text selection → highlight creation flow
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
  documentId,
  onHighlightCreated,
  onHighlightError,
}: HtmlHighlightReaderProps) {
  const activeHighlightId = useUIStore((s) => s.activeHighlightId);
  const hoveredHighlightId = useUIStore((s) => s.hoveredHighlightId);
  const setActiveHighlightId = useUIStore((s) => s.setActiveHighlightId);
  const setHoveredHighlightId = useUIStore((s) => s.setHoveredHighlightId);

  // Ref to the container for scroll-to-highlight functionality
  const containerRef = useRef<HTMLDivElement>(null);

  // Selection state for highlight creation
  const [pendingSelection, setPendingSelection] = useState<PendingSelection | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);

  // Highlight creation mutation (only if documentId provided)
  const { createHighlight, isPending: isCreating } = useCreateHighlight(documentId ?? "");

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

  /**
   * Handle text selection (mouseup) to detect highlight-worthy selections.
   *
   * Flow:
   * 1. Get the current selection from window
   * 2. Verify selection is non-collapsed and within our container
   * 3. Resolve selection text to canonical offsets
   * 4. Set pending selection state (UI will show "Add Highlight" button)
   */
  const handleMouseUp = useCallback(() => {
    // Clear any previous selection/error state
    setPendingSelection(null);
    setSelectionError(null);

    // Skip if highlight creation is not enabled (no documentId)
    if (!documentId) return;

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;

    // Check if selection is within our container
    const container = containerRef.current;
    if (!container) return;

    // Verify selection is within our reader container
    const anchorNode = selection.anchorNode;
    const focusNode = selection.focusNode;
    if (!anchorNode || !focusNode) return;
    if (!container.contains(anchorNode) || !container.contains(focusNode)) return;

    // Get the selected text
    const selectionText = selection.toString();
    if (!selectionText.trim()) return;

    // Check selection length
    if (selectionText.length > MAX_SELECTION_LENGTH) {
      setSelectionError(`Selection too long (max ${MAX_SELECTION_LENGTH} characters)`);
      return;
    }

    // Resolve selection to canonical offsets using anchoring core
    const resolution = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText: selectionText,
    });

    if (resolution.status === "unresolved") {
      // Selection could not be mapped to canonical text
      // This can happen with browser quirks or whitespace normalization issues
      setSelectionError("Could not map selection to document text");
      return;
    }

    // Set pending selection for UI
    setPendingSelection({
      textStart: resolution.start!,
      textEnd: resolution.end!,
      quote: selectionText.trim(),
    });
  }, [documentId, canonicalText]);

  /**
   * Handle confirm highlight creation.
   */
  const handleCreateHighlight = useCallback(async () => {
    if (!pendingSelection || !documentId) return;

    try {
      const highlight = await createHighlight({
        textStart: pendingSelection.textStart,
        textEnd: pendingSelection.textEnd,
      });

      // Clear selection state
      setPendingSelection(null);
      window.getSelection()?.removeAllRanges();

      // Set the new highlight as active
      setActiveHighlightId(highlight.id);

      // Notify parent
      onHighlightCreated?.(highlight);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Failed to create highlight";
      setSelectionError(errorMessage);
      onHighlightError?.(error instanceof Error ? error : new Error(errorMessage));
    }
  }, [pendingSelection, documentId, createHighlight, setActiveHighlightId, onHighlightCreated, onHighlightError]);

  /**
   * Handle cancel selection.
   */
  const handleCancelSelection = useCallback(() => {
    setPendingSelection(null);
    setSelectionError(null);
    window.getSelection()?.removeAllRanges();
  }, []);

  /**
   * Handle escape key to cancel selection.
   */
  useEffect(() => {
    if (!pendingSelection) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleCancelSelection();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [pendingSelection, handleCancelSelection]);

  /**
   * Handle click outside the selection action bar to dismiss.
   * We listen for mousedown outside the action bar when selection is pending.
   */
  const actionBarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!pendingSelection) return;

    const handleClickOutside = (e: MouseEvent) => {
      const actionBar = actionBarRef.current;
      if (actionBar && !actionBar.contains(e.target as Node)) {
        // Click was outside the action bar - clear selection
        handleCancelSelection();
      }
    };

    // Use mousedown so we catch clicks before they potentially create a new selection
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [pendingSelection, handleCancelSelection]);

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
    <div className="relative">
      {/* Selection action bar (shows when text is selected) */}
      {pendingSelection && documentId && (
        <div
          ref={actionBarRef}
          data-testid="selection-action-bar"
          className="sticky top-0 z-10 bg-white border-b border-gray-200 shadow-sm py-2 px-4 mb-4 flex items-center justify-between gap-4"
        >
          <div className="flex-1 min-w-0">
            <p className="text-sm text-gray-600 truncate">
              Selected: &ldquo;{pendingSelection.quote.slice(0, 50)}
              {pendingSelection.quote.length > 50 ? "..." : ""}&rdquo;
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCancelSelection}
              disabled={isCreating}
              className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 disabled:opacity-50"
              data-testid="cancel-selection-btn"
            >
              Cancel
            </button>
            <button
              onClick={handleCreateHighlight}
              disabled={isCreating}
              className="px-3 py-1.5 text-sm font-medium text-white bg-yellow-500 hover:bg-yellow-600 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="create-highlight-btn"
            >
              {isCreating ? "Creating..." : "Add Highlight"}
            </button>
          </div>
        </div>
      )}

      {/* Selection error message */}
      {selectionError && (
        <div
          data-testid="selection-error"
          className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700"
        >
          {selectionError}
          <button
            onClick={() => setSelectionError(null)}
            className="ml-2 text-red-500 hover:text-red-700 underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main reader content */}
      <div
        ref={containerRef}
        data-testid="html-reader"
        onMouseUp={handleMouseUp}
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

