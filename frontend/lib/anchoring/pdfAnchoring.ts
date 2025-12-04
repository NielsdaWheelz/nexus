/**
 * PDF Anchoring Module
 *
 * Maps highlight anchors to PDF text layer spans and decorates them
 * with highlight styling. Works with global character offsets that
 * match the `data-char-offset` attributes on text layer spans.
 *
 * DESIGN NOTES
 * ------------
 * The PDF text layer uses global character offsets (across all pages),
 * computed by concatenating all text items from page 1 to N in order.
 * This matches the `text_start` and `text_end` fields in highlights.
 *
 * For rendering, we:
 * 1. Scan all text spans in the page's text layer
 * 2. For each highlight, find spans that intersect with [text_start, text_end)
 * 3. Wrap the intersecting character ranges with highlight markup
 *
 * SPAN STRUCTURE
 * --------------
 * Each text span in the PDF text layer has:
 * - data-char-offset: global character offset of the span's start
 * - data-page-number: page number (1-based)
 * - textContent: the text string
 *
 * A highlight with [text_start, text_end) intersects a span with
 * [spanOffset, spanOffset + spanLength) if:
 *   text_start < spanOffset + spanLength && text_end > spanOffset
 *
 * CSS CLASSES
 * -----------
 * - pdf-highlight: base highlight styling
 * - pdf-highlight-active: active highlight styling
 * - pdf-highlight-[color]: color-specific styling (yellow, blue, etc.)
 */

/**
 * Anchor data for a single highlight to apply to the PDF text layer.
 */
export interface PdfHighlightAnchor {
  /** Unique highlight ID (hl_<uuid>) */
  highlightId: string;
  /** Global character offset start (matches text_start) */
  charStart: number;
  /** Global character offset end (matches text_end) */
  charEnd: number;
  /** Highlight color */
  color: string;
  /** Whether this highlight is currently active/focused */
  isActive: boolean;
}

/**
 * Result of applying highlights to a page.
 */
export interface ApplyHighlightsResult {
  /** Number of highlights successfully anchored */
  anchored: number;
  /** Number of highlights that couldn't be anchored */
  failed: number;
  /** Highlight IDs that were successfully anchored */
  anchoredIds: string[];
}

/** CSS class for highlight wrapper spans */
const HIGHLIGHT_CLASS = "pdf-highlight";
/** CSS class for active highlight */
const ACTIVE_CLASS = "pdf-highlight-active";
/** Data attribute for highlight ID */
const HIGHLIGHT_ID_ATTR = "data-highlight-id";
/** Data attribute for char offset (from PdfReader) */
const CHAR_OFFSET_ATTR = "data-char-offset";

/**
 * Apply PDF highlights to a page's text layer.
 *
 * This function scans the text layer DOM, identifies spans that intersect
 * with the given highlight anchors, and wraps the relevant text portions
 * with highlight markup.
 *
 * @param pageRoot - The root element of the page's text layer (has class pdf-text-layer)
 * @param anchors - Array of highlight anchors to apply
 * @returns Result indicating how many highlights were anchored
 */
export function applyPdfHighlightsToPage(
  pageRoot: HTMLElement,
  anchors: PdfHighlightAnchor[]
): ApplyHighlightsResult {
  const result: ApplyHighlightsResult = {
    anchored: 0,
    failed: 0,
    anchoredIds: [],
  };

  if (anchors.length === 0) {
    return result;
  }

  // Get all text spans in the text layer
  const spans = pageRoot.querySelectorAll<HTMLSpanElement>(`span[${CHAR_OFFSET_ATTR}]`);
  if (spans.length === 0) {
    // No text spans in this layer; all highlights fail
    result.failed = anchors.length;
    return result;
  }

  // Build a sorted list of span info for efficient lookup
  const spanInfos = Array.from(spans).map((span) => {
    const offset = parseInt(span.getAttribute(CHAR_OFFSET_ATTR) || "0", 10);
    const text = span.textContent || "";
    return { span, offset, length: text.length, text };
  });

  // Sort by offset (should already be sorted, but be defensive)
  spanInfos.sort((a, b) => a.offset - b.offset);

  // For each anchor, find intersecting spans and apply highlight
  for (const anchor of anchors) {
    const intersecting = findIntersectingSpans(spanInfos, anchor.charStart, anchor.charEnd);

    if (intersecting.length === 0) {
      result.failed++;
      if (process.env.NODE_ENV === "development") {
        console.debug(
          `[pdfAnchoring] Could not anchor highlight ${anchor.highlightId}: ` +
            `no spans intersect [${anchor.charStart}, ${anchor.charEnd})`
        );
      }
      continue;
    }

    // Apply highlight to each intersecting span
    for (const { span, offset, length, text } of intersecting) {
      // Calculate which portion of this span to highlight
      const spanEnd = offset + length;
      const highlightStart = Math.max(anchor.charStart, offset);
      const highlightEnd = Math.min(anchor.charEnd, spanEnd);

      // Convert to relative indices within the span
      const relStart = highlightStart - offset;
      const relEnd = highlightEnd - offset;

      // Wrap the highlighted portion
      wrapTextWithHighlight(span, relStart, relEnd, anchor);
    }

    result.anchored++;
    result.anchoredIds.push(anchor.highlightId);
  }

  return result;
}

/**
 * Find spans that intersect with a character range.
 */
function findIntersectingSpans(
  spanInfos: Array<{ span: HTMLSpanElement; offset: number; length: number; text: string }>,
  start: number,
  end: number
): Array<{ span: HTMLSpanElement; offset: number; length: number; text: string }> {
  return spanInfos.filter((info) => {
    const spanEnd = info.offset + info.length;
    // Spans intersect if: start < spanEnd && end > spanOffset
    return start < spanEnd && end > info.offset;
  });
}

/**
 * Wrap a portion of a span's text with a highlight element.
 *
 * This function modifies the DOM to wrap the specified character range
 * with a highlight span. It handles partial highlighting (not the entire span).
 *
 * Strategy:
 * - If the entire span is highlighted, just add highlight classes
 * - If partial, split the text node and wrap the highlighted portion
 */
function wrapTextWithHighlight(
  span: HTMLSpanElement,
  relStart: number,
  relEnd: number,
  anchor: PdfHighlightAnchor
): void {
  const text = span.textContent || "";

  // Check if this span already has a highlight wrapper for this highlight
  const existingHighlight = span.querySelector(`[${HIGHLIGHT_ID_ATTR}="${anchor.highlightId}"]`);
  if (existingHighlight) {
    // Already highlighted, just update active state
    existingHighlight.classList.toggle(ACTIVE_CLASS, anchor.isActive);
    return;
  }

  // If highlighting the entire span, add classes directly
  if (relStart === 0 && relEnd >= text.length) {
    applyHighlightClasses(span, anchor);
    span.setAttribute(HIGHLIGHT_ID_ATTR, anchor.highlightId);
    return;
  }

  // Partial highlight: need to split the text and wrap
  const before = text.slice(0, relStart);
  const highlighted = text.slice(relStart, relEnd);
  const after = text.slice(relEnd);

  // Clear the span and rebuild with wrapped highlight
  span.textContent = "";

  if (before) {
    span.appendChild(document.createTextNode(before));
  }

  const highlightSpan = document.createElement("span");
  highlightSpan.textContent = highlighted;
  applyHighlightClasses(highlightSpan, anchor);
  highlightSpan.setAttribute(HIGHLIGHT_ID_ATTR, anchor.highlightId);
  span.appendChild(highlightSpan);

  if (after) {
    span.appendChild(document.createTextNode(after));
  }
}

/**
 * Apply highlight CSS classes to an element.
 */
function applyHighlightClasses(element: HTMLElement, anchor: PdfHighlightAnchor): void {
  element.classList.add(HIGHLIGHT_CLASS);
  element.classList.add(`pdf-highlight-${anchor.color}`);
  if (anchor.isActive) {
    element.classList.add(ACTIVE_CLASS);
  }
  // Add cursor and pointer events for interaction
  element.style.cursor = "pointer";
  element.style.pointerEvents = "auto";
}

/**
 * Clear all highlight decorations from a page's text layer.
 *
 * This removes highlight classes and restores the original span structure.
 * Call this before re-applying highlights to avoid duplicate decorations.
 */
export function clearPdfHighlightsFromPage(pageRoot: HTMLElement): void {
  // Find all highlight wrapper spans
  const highlightSpans = pageRoot.querySelectorAll<HTMLSpanElement>(`[${HIGHLIGHT_ID_ATTR}]`);

  for (const span of highlightSpans) {
    // If the highlight span is a child (partial highlight case), unwrap it
    const parent = span.parentElement;
    if (parent && parent !== pageRoot && parent.hasAttribute(CHAR_OFFSET_ATTR)) {
      // This is a nested highlight span, unwrap it
      const text = span.textContent || "";
      span.replaceWith(document.createTextNode(text));
      // Normalize the parent to merge adjacent text nodes
      parent.normalize();
    } else if (span.hasAttribute(CHAR_OFFSET_ATTR)) {
      // This is an original text span with highlight classes, just remove classes
      span.classList.remove(HIGHLIGHT_CLASS, ACTIVE_CLASS);
      // Remove color classes
      for (const cls of Array.from(span.classList)) {
        if (cls.startsWith("pdf-highlight-")) {
          span.classList.remove(cls);
        }
      }
      span.removeAttribute(HIGHLIGHT_ID_ATTR);
      span.style.cursor = "";
      span.style.pointerEvents = "";
    }
  }
}

/**
 * Update the active state of highlights on a page.
 *
 * More efficient than re-applying all highlights when only the active ID changes.
 */
export function updateActiveHighlight(
  pageRoot: HTMLElement,
  activeHighlightId: string | null
): void {
  // Remove active class from all highlights
  const allHighlights = pageRoot.querySelectorAll<HTMLElement>(`.${ACTIVE_CLASS}`);
  for (const el of allHighlights) {
    el.classList.remove(ACTIVE_CLASS);
  }

  // Add active class to the active highlight
  if (activeHighlightId) {
    const activeElements = pageRoot.querySelectorAll<HTMLElement>(
      `[${HIGHLIGHT_ID_ATTR}="${activeHighlightId}"]`
    );
    for (const el of activeElements) {
      el.classList.add(ACTIVE_CLASS);
    }
  }
}

/**
 * Find the first element for a highlight ID (for scrolling).
 */
export function findHighlightElement(
  root: HTMLElement,
  highlightId: string
): HTMLElement | null {
  return root.querySelector<HTMLElement>(`[${HIGHLIGHT_ID_ATTR}="${highlightId}"]`);
}

/**
 * Check if a highlight with given character range intersects with a page.
 *
 * @param pageMinOffset - Minimum char offset on this page
 * @param pageMaxOffset - Maximum char offset on this page (exclusive)
 * @param highlightStart - Highlight start offset
 * @param highlightEnd - Highlight end offset
 */
export function highlightIntersectsPage(
  pageMinOffset: number,
  pageMaxOffset: number,
  highlightStart: number,
  highlightEnd: number
): boolean {
  return highlightStart < pageMaxOffset && highlightEnd > pageMinOffset;
}

