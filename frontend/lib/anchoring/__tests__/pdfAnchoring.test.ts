/**
 * Tests for PDF Anchoring Module
 *
 * These tests verify the PDF highlight anchoring logic for:
 * - applyPdfHighlightsToPage: decorating text layer spans with highlights
 * - clearPdfHighlightsFromPage: removing highlight decorations
 * - updateActiveHighlight: updating active state efficiently
 * - findHighlightElement: locating highlight elements for scrolling
 * - highlightIntersectsPage: checking if highlight overlaps a page
 *
 * Test philosophy:
 * - Synthetic DOM tests (no pdf.js required)
 * - Each test creates a minimal text layer structure
 * - Verify DOM mutations and class applications
 */

import { describe, test, expect, beforeEach } from "vitest";
import {
  applyPdfHighlightsToPage,
  clearPdfHighlightsFromPage,
  updateActiveHighlight,
  findHighlightElement,
  highlightIntersectsPage,
  type PdfHighlightAnchor,
} from "../pdfAnchoring";

/**
 * Helper to create a synthetic text layer div with spans.
 * Each span has data-char-offset and data-page-number attributes.
 */
function createTextLayer(
  spans: Array<{ text: string; charOffset: number; pageNumber?: number }>
): HTMLDivElement {
  const layer = document.createElement("div");
  layer.className = "pdf-text-layer";

  for (const { text, charOffset, pageNumber = 1 } of spans) {
    const span = document.createElement("span");
    span.textContent = text;
    span.setAttribute("data-char-offset", String(charOffset));
    span.setAttribute("data-page-number", String(pageNumber));
    layer.appendChild(span);
  }

  return layer;
}

// =============================================================================
// applyPdfHighlightsToPage Tests
// =============================================================================

describe("applyPdfHighlightsToPage", () => {
  test("single highlight covering entire span", () => {
    // Create a simple text layer with one span
    const layer = createTextLayer([{ text: "Hello World", charOffset: 0 }]);

    const anchors: PdfHighlightAnchor[] = [
      {
        highlightId: "hl_123",
        charStart: 0,
        charEnd: 11,
        color: "yellow",
        isActive: false,
      },
    ];

    const result = applyPdfHighlightsToPage(layer, anchors);

    expect(result.anchored).toBe(1);
    expect(result.failed).toBe(0);
    expect(result.anchoredIds).toContain("hl_123");

    // Verify the span has highlight classes
    const span = layer.querySelector("span");
    expect(span?.classList.contains("pdf-highlight")).toBe(true);
    expect(span?.classList.contains("pdf-highlight-yellow")).toBe(true);
    expect(span?.getAttribute("data-highlight-id")).toBe("hl_123");
  });

  test("single highlight covering partial span", () => {
    // "Hello World" - highlight only "World"
    const layer = createTextLayer([{ text: "Hello World", charOffset: 0 }]);

    const anchors: PdfHighlightAnchor[] = [
      {
        highlightId: "hl_456",
        charStart: 6, // "World" starts at index 6
        charEnd: 11,
        color: "blue",
        isActive: false,
      },
    ];

    const result = applyPdfHighlightsToPage(layer, anchors);

    expect(result.anchored).toBe(1);

    // The span should now contain:
    // - text node "Hello "
    // - <span class="pdf-highlight">World</span>
    const span = layer.querySelector("span[data-char-offset]");
    const highlightSpan = span?.querySelector("[data-highlight-id]");

    expect(highlightSpan).not.toBeNull();
    expect(highlightSpan?.textContent).toBe("World");
    expect(highlightSpan?.classList.contains("pdf-highlight-blue")).toBe(true);
  });

  test("highlight spanning multiple spans", () => {
    // Two spans: "Hello " (0-6) and "World" (6-11)
    // Highlight spans both: "lo Wor" (3-9)
    const layer = createTextLayer([
      { text: "Hello ", charOffset: 0 },
      { text: "World", charOffset: 6 },
    ]);

    const anchors: PdfHighlightAnchor[] = [
      {
        highlightId: "hl_789",
        charStart: 3,
        charEnd: 9,
        color: "green",
        isActive: false,
      },
    ];

    const result = applyPdfHighlightsToPage(layer, anchors);

    expect(result.anchored).toBe(1);

    // Both spans should have highlight elements
    const highlights = layer.querySelectorAll("[data-highlight-id='hl_789']");
    expect(highlights.length).toBe(2);
  });

  test("multiple non-overlapping highlights on same page", () => {
    // "Hello World Goodbye" - highlight "Hello" and "Goodbye"
    const layer = createTextLayer([
      { text: "Hello ", charOffset: 0 },
      { text: "World ", charOffset: 6 },
      { text: "Goodbye", charOffset: 12 },
    ]);

    const anchors: PdfHighlightAnchor[] = [
      {
        highlightId: "hl_aaa",
        charStart: 0,
        charEnd: 5,
        color: "yellow",
        isActive: false,
      },
      {
        highlightId: "hl_bbb",
        charStart: 12,
        charEnd: 19,
        color: "pink",
        isActive: false,
      },
    ];

    const result = applyPdfHighlightsToPage(layer, anchors);

    expect(result.anchored).toBe(2);
    expect(result.anchoredIds).toContain("hl_aaa");
    expect(result.anchoredIds).toContain("hl_bbb");

    // Verify both highlights are present
    const highlight1 = layer.querySelector("[data-highlight-id='hl_aaa']");
    const highlight2 = layer.querySelector("[data-highlight-id='hl_bbb']");

    expect(highlight1).not.toBeNull();
    expect(highlight2).not.toBeNull();
    expect(highlight1?.classList.contains("pdf-highlight-yellow")).toBe(true);
    expect(highlight2?.classList.contains("pdf-highlight-pink")).toBe(true);
  });

  test("active highlight gets active class", () => {
    const layer = createTextLayer([{ text: "Hello World", charOffset: 0 }]);

    const anchors: PdfHighlightAnchor[] = [
      {
        highlightId: "hl_active",
        charStart: 0,
        charEnd: 5,
        color: "yellow",
        isActive: true, // This is the active highlight
      },
    ];

    applyPdfHighlightsToPage(layer, anchors);

    const highlight = layer.querySelector("[data-highlight-id='hl_active']");
    expect(highlight?.classList.contains("pdf-highlight-active")).toBe(true);
  });

  test("non-active highlight does not get active class", () => {
    const layer = createTextLayer([{ text: "Hello World", charOffset: 0 }]);

    const anchors: PdfHighlightAnchor[] = [
      {
        highlightId: "hl_inactive",
        charStart: 0,
        charEnd: 5,
        color: "yellow",
        isActive: false,
      },
    ];

    applyPdfHighlightsToPage(layer, anchors);

    const highlight = layer.querySelector("[data-highlight-id='hl_inactive']");
    expect(highlight?.classList.contains("pdf-highlight-active")).toBe(false);
  });

  test("highlight with no intersecting spans returns failed", () => {
    // Text layer spans 0-11, but highlight is at 100-110
    const layer = createTextLayer([{ text: "Hello World", charOffset: 0 }]);

    const anchors: PdfHighlightAnchor[] = [
      {
        highlightId: "hl_miss",
        charStart: 100,
        charEnd: 110,
        color: "yellow",
        isActive: false,
      },
    ];

    const result = applyPdfHighlightsToPage(layer, anchors);

    expect(result.anchored).toBe(0);
    expect(result.failed).toBe(1);
    expect(result.anchoredIds).not.toContain("hl_miss");
  });

  test("empty anchors array returns zero counts", () => {
    const layer = createTextLayer([{ text: "Hello World", charOffset: 0 }]);

    const result = applyPdfHighlightsToPage(layer, []);

    expect(result.anchored).toBe(0);
    expect(result.failed).toBe(0);
  });

  test("empty text layer fails all anchors", () => {
    const layer = document.createElement("div");
    layer.className = "pdf-text-layer";
    // No spans

    const anchors: PdfHighlightAnchor[] = [
      {
        highlightId: "hl_orphan",
        charStart: 0,
        charEnd: 10,
        color: "yellow",
        isActive: false,
      },
    ];

    const result = applyPdfHighlightsToPage(layer, anchors);

    expect(result.anchored).toBe(0);
    expect(result.failed).toBe(1);
  });

  test("different colors are applied correctly", () => {
    const layer = createTextLayer([
      { text: "One ", charOffset: 0 },
      { text: "Two ", charOffset: 4 },
      { text: "Three", charOffset: 8 },
    ]);

    const anchors: PdfHighlightAnchor[] = [
      { highlightId: "h1", charStart: 0, charEnd: 3, color: "yellow", isActive: false },
      { highlightId: "h2", charStart: 4, charEnd: 7, color: "blue", isActive: false },
      { highlightId: "h3", charStart: 8, charEnd: 13, color: "purple", isActive: false },
    ];

    applyPdfHighlightsToPage(layer, anchors);

    expect(layer.querySelector("[data-highlight-id='h1']")?.classList.contains("pdf-highlight-yellow")).toBe(true);
    expect(layer.querySelector("[data-highlight-id='h2']")?.classList.contains("pdf-highlight-blue")).toBe(true);
    expect(layer.querySelector("[data-highlight-id='h3']")?.classList.contains("pdf-highlight-purple")).toBe(true);
  });
});

// =============================================================================
// clearPdfHighlightsFromPage Tests
// =============================================================================

describe("clearPdfHighlightsFromPage", () => {
  test("removes highlight classes from full-span highlights", () => {
    const layer = createTextLayer([{ text: "Hello World", charOffset: 0 }]);

    // Apply highlight first
    applyPdfHighlightsToPage(layer, [
      {
        highlightId: "hl_clear",
        charStart: 0,
        charEnd: 11,
        color: "yellow",
        isActive: true,
      },
    ]);

    // Verify it's there
    const span = layer.querySelector("span[data-char-offset]");
    expect(span?.classList.contains("pdf-highlight")).toBe(true);

    // Clear highlights
    clearPdfHighlightsFromPage(layer);

    // Verify classes are removed
    expect(span?.classList.contains("pdf-highlight")).toBe(false);
    expect(span?.classList.contains("pdf-highlight-yellow")).toBe(false);
    expect(span?.classList.contains("pdf-highlight-active")).toBe(false);
    expect(span?.hasAttribute("data-highlight-id")).toBe(false);
  });

  test("removes nested highlight spans for partial highlights", () => {
    const layer = createTextLayer([{ text: "Hello World", charOffset: 0 }]);

    // Apply partial highlight
    applyPdfHighlightsToPage(layer, [
      {
        highlightId: "hl_partial",
        charStart: 6,
        charEnd: 11,
        color: "yellow",
        isActive: false,
      },
    ]);

    // There should be a nested span
    const nestedSpan = layer.querySelector("[data-highlight-id='hl_partial']");
    expect(nestedSpan).not.toBeNull();

    // Clear highlights
    clearPdfHighlightsFromPage(layer);

    // Nested span should be gone
    const removedSpan = layer.querySelector("[data-highlight-id='hl_partial']");
    expect(removedSpan).toBeNull();
  });
});

// =============================================================================
// updateActiveHighlight Tests
// =============================================================================

describe("updateActiveHighlight", () => {
  test("adds active class to the specified highlight", () => {
    const layer = createTextLayer([
      { text: "Hello ", charOffset: 0 },
      { text: "World", charOffset: 6 },
    ]);

    // Apply two highlights
    applyPdfHighlightsToPage(layer, [
      { highlightId: "h1", charStart: 0, charEnd: 5, color: "yellow", isActive: false },
      { highlightId: "h2", charStart: 6, charEnd: 11, color: "blue", isActive: false },
    ]);

    // Neither should be active
    expect(layer.querySelector("[data-highlight-id='h1']")?.classList.contains("pdf-highlight-active")).toBe(false);
    expect(layer.querySelector("[data-highlight-id='h2']")?.classList.contains("pdf-highlight-active")).toBe(false);

    // Set h1 as active
    updateActiveHighlight(layer, "h1");

    // Only h1 should be active
    expect(layer.querySelector("[data-highlight-id='h1']")?.classList.contains("pdf-highlight-active")).toBe(true);
    expect(layer.querySelector("[data-highlight-id='h2']")?.classList.contains("pdf-highlight-active")).toBe(false);
  });

  test("removes active class when null is passed", () => {
    const layer = createTextLayer([{ text: "Hello", charOffset: 0 }]);

    applyPdfHighlightsToPage(layer, [
      { highlightId: "h1", charStart: 0, charEnd: 5, color: "yellow", isActive: true },
    ]);

    expect(layer.querySelector("[data-highlight-id='h1']")?.classList.contains("pdf-highlight-active")).toBe(true);

    updateActiveHighlight(layer, null);

    expect(layer.querySelector("[data-highlight-id='h1']")?.classList.contains("pdf-highlight-active")).toBe(false);
  });

  test("switches active from one highlight to another", () => {
    const layer = createTextLayer([
      { text: "One ", charOffset: 0 },
      { text: "Two", charOffset: 4 },
    ]);

    applyPdfHighlightsToPage(layer, [
      { highlightId: "h1", charStart: 0, charEnd: 3, color: "yellow", isActive: true },
      { highlightId: "h2", charStart: 4, charEnd: 7, color: "blue", isActive: false },
    ]);

    // h1 is active
    expect(layer.querySelector("[data-highlight-id='h1']")?.classList.contains("pdf-highlight-active")).toBe(true);
    expect(layer.querySelector("[data-highlight-id='h2']")?.classList.contains("pdf-highlight-active")).toBe(false);

    // Switch to h2
    updateActiveHighlight(layer, "h2");

    // Now h2 is active, h1 is not
    expect(layer.querySelector("[data-highlight-id='h1']")?.classList.contains("pdf-highlight-active")).toBe(false);
    expect(layer.querySelector("[data-highlight-id='h2']")?.classList.contains("pdf-highlight-active")).toBe(true);
  });
});

// =============================================================================
// findHighlightElement Tests
// =============================================================================

describe("findHighlightElement", () => {
  test("finds highlight element by ID", () => {
    const layer = createTextLayer([{ text: "Hello", charOffset: 0 }]);

    applyPdfHighlightsToPage(layer, [
      { highlightId: "hl_findme", charStart: 0, charEnd: 5, color: "yellow", isActive: false },
    ]);

    const element = findHighlightElement(layer, "hl_findme");

    expect(element).not.toBeNull();
    expect(element?.getAttribute("data-highlight-id")).toBe("hl_findme");
  });

  test("returns null for non-existent highlight", () => {
    const layer = createTextLayer([{ text: "Hello", charOffset: 0 }]);

    const element = findHighlightElement(layer, "hl_nonexistent");

    expect(element).toBeNull();
  });
});

// =============================================================================
// highlightIntersectsPage Tests
// =============================================================================

describe("highlightIntersectsPage", () => {
  test("highlight fully within page returns true", () => {
    // Page range: 0-100, highlight: 20-50
    expect(highlightIntersectsPage(0, 100, 20, 50)).toBe(true);
  });

  test("highlight starting before page but ending within returns true", () => {
    // Page range: 50-100, highlight: 30-70
    expect(highlightIntersectsPage(50, 100, 30, 70)).toBe(true);
  });

  test("highlight starting within page but ending after returns true", () => {
    // Page range: 0-50, highlight: 30-70
    expect(highlightIntersectsPage(0, 50, 30, 70)).toBe(true);
  });

  test("highlight spanning entire page returns true", () => {
    // Page range: 50-100, highlight: 0-200
    expect(highlightIntersectsPage(50, 100, 0, 200)).toBe(true);
  });

  test("highlight completely before page returns false", () => {
    // Page range: 100-200, highlight: 0-50
    expect(highlightIntersectsPage(100, 200, 0, 50)).toBe(false);
  });

  test("highlight completely after page returns false", () => {
    // Page range: 0-100, highlight: 150-200
    expect(highlightIntersectsPage(0, 100, 150, 200)).toBe(false);
  });

  test("highlight ending exactly at page start returns false", () => {
    // Page range: 100-200, highlight: 50-100 (ends at page start, no overlap)
    expect(highlightIntersectsPage(100, 200, 50, 100)).toBe(false);
  });

  test("highlight starting exactly at page end returns false", () => {
    // Page range: 0-100, highlight: 100-150 (starts at page end, no overlap)
    expect(highlightIntersectsPage(0, 100, 100, 150)).toBe(false);
  });
});

