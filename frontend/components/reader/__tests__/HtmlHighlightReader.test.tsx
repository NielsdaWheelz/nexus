import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, test, expect, beforeEach, vi } from "vitest";
import { HtmlHighlightReader } from "../HtmlHighlightReader";
import { useUIStore } from "@/lib/state/ui";
import type { HighlightItem } from "@/lib/generated-api";

// Mock scrollIntoView since it's not available in JSDOM
Element.prototype.scrollIntoView = vi.fn();

/**
 * Create a mock highlight for testing.
 */
function createMockHighlight(
  id: string,
  textStart: number,
  textEnd: number,
  quote: string = ""
): HighlightItem {
  return {
    id,
    document_id: "doc_test",
    text_start: textStart,
    text_end: textEnd,
    quote: quote || `[${textStart}-${textEnd}]`,
    created_at: "2025-01-01T12:00:00Z",
    updated_at: "2025-01-01T12:00:00Z",
  };
}

/**
 * Reset zustand store state between tests.
 */
function resetUIStore() {
  useUIStore.setState({
    isInspectorOpen: true,
    activeInspectorTab: "highlights",
    activeHighlightId: null,
    hoveredHighlightId: null,
  });
}

describe("HtmlHighlightReader", () => {
  beforeEach(() => {
    resetUIStore();
  });

  describe("basic rendering", () => {
    test("renders plain text when no highlights", () => {
      render(
        <HtmlHighlightReader
          canonicalText="Hello, world!"
          highlights={[]}
        />
      );

      expect(screen.getByTestId("html-reader")).toBeInTheDocument();
      expect(screen.getByText("Hello, world!")).toBeInTheDocument();
      // Should not have any highlight spans
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    test("renders empty state when no canonical text", () => {
      render(
        <HtmlHighlightReader
          canonicalText=""
          highlights={[]}
        />
      );

      expect(screen.getByText("No content available")).toBeInTheDocument();
    });

    test("renders single highlight correctly", () => {
      const text = "Hello, world!";
      const highlight = createMockHighlight("hl_1", 7, 12); // "world"

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      // Check that "world" is in a highlight span
      const highlightSpan = screen.getByText("world");
      expect(highlightSpan).toHaveAttribute("data-highlight-id", "hl_1");
    });

    test("renders multiple non-overlapping highlights", () => {
      const text = "Hello, beautiful world!";
      const highlights = [
        createMockHighlight("hl_1", 0, 5), // "Hello"
        createMockHighlight("hl_2", 7, 16), // "beautiful"
        createMockHighlight("hl_3", 17, 22), // "world"
      ];

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={highlights}
        />
      );

      // All three highlights should be rendered
      expect(screen.getByText("Hello")).toHaveAttribute(
        "data-highlight-id",
        "hl_1"
      );
      expect(screen.getByText("beautiful")).toHaveAttribute(
        "data-highlight-id",
        "hl_2"
      );
      expect(screen.getByText("world")).toHaveAttribute(
        "data-highlight-id",
        "hl_3"
      );
    });

    test("handles highlight at start of text", () => {
      const text = "Hello, world!";
      const highlight = createMockHighlight("hl_1", 0, 5); // "Hello"

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      expect(screen.getByText("Hello")).toHaveAttribute(
        "data-highlight-id",
        "hl_1"
      );
    });

    test("handles highlight at end of text", () => {
      const text = "Hello, world!";
      const highlight = createMockHighlight("hl_1", 7, 13); // "world!"

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      expect(screen.getByText("world!")).toHaveAttribute(
        "data-highlight-id",
        "hl_1"
      );
    });
  });

  describe("overlapping highlights (first wins policy)", () => {
    test("first highlight wins when two overlap", () => {
      const text = "Hello, world!";
      // hl_1 covers "Hello, " (0-7)
      // hl_2 covers ", wor" (5-10) - overlaps with hl_1
      const highlights = [
        createMockHighlight("hl_1", 0, 7),
        createMockHighlight("hl_2", 5, 10),
      ];

      const { container } = render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={highlights}
        />
      );

      // hl_1 should be rendered (check by data-highlight-id)
      const hl1Span = container.querySelector('[data-highlight-id="hl_1"]');
      expect(hl1Span).toBeInTheDocument();
      expect(hl1Span?.textContent).toBe("Hello, ");

      // hl_2 should be skipped (overlaps) - no span with this id
      const hl2Span = container.querySelector('[data-highlight-id="hl_2"]');
      expect(hl2Span).not.toBeInTheDocument();
    });

    test("later highlight is rendered if it starts after first ends", () => {
      const text = "Hello, world!";
      const highlights = [
        createMockHighlight("hl_1", 0, 5), // "Hello"
        createMockHighlight("hl_2", 7, 12), // "world"
      ];

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={highlights}
        />
      );

      // Both should be rendered (no overlap)
      expect(screen.getByText("Hello")).toHaveAttribute(
        "data-highlight-id",
        "hl_1"
      );
      expect(screen.getByText("world")).toHaveAttribute(
        "data-highlight-id",
        "hl_2"
      );
    });
  });

  describe("edge cases and validation", () => {
    test("clamps out-of-bounds highlight start", () => {
      const text = "Hello";
      const highlight = createMockHighlight("hl_1", -5, 3); // Invalid start

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      // Should clamp to 0-3 ("Hel")
      expect(screen.getByText("Hel")).toHaveAttribute(
        "data-highlight-id",
        "hl_1"
      );
    });

    test("clamps out-of-bounds highlight end", () => {
      const text = "Hello";
      const highlight = createMockHighlight("hl_1", 3, 100); // End beyond text

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      // Should clamp to 3-5 ("lo")
      expect(screen.getByText("lo")).toHaveAttribute(
        "data-highlight-id",
        "hl_1"
      );
    });

    test("filters out invalid ranges where start >= end", () => {
      const text = "Hello";
      const highlights = [
        createMockHighlight("hl_1", 5, 5), // Empty range
        createMockHighlight("hl_2", 4, 2), // Inverted range
      ];

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={highlights}
        />
      );

      // Neither should produce highlight spans
      const reader = screen.getByTestId("html-reader");
      expect(reader.querySelectorAll("[data-highlight-id]")).toHaveLength(0);
    });

    test("handles unicode characters", () => {
      // text_start and text_end are character (codepoint) indices
      // which align with JavaScript string indices
      const text = "Héllo wörld café";
      const highlight = createMockHighlight("hl_1", 0, 5, "Héllo");

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      // Should render without crashing
      expect(screen.getByTestId("html-reader")).toBeInTheDocument();
    });

    test("handles whitespace and newlines", () => {
      const text = "Hello\nworld\n\ntest";
      const highlight = createMockHighlight("hl_1", 6, 11); // "world"

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      expect(screen.getByText("world")).toHaveAttribute(
        "data-highlight-id",
        "hl_1"
      );
    });
  });

  describe("interaction with UI store", () => {
    test("clicking highlight sets activeHighlightId", () => {
      const text = "Hello, world!";
      const highlight = createMockHighlight("hl_1", 7, 12);

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      const highlightSpan = screen.getByText("world");
      fireEvent.click(highlightSpan);

      expect(useUIStore.getState().activeHighlightId).toBe("hl_1");
    });

    test("hovering highlight sets hoveredHighlightId", () => {
      const text = "Hello, world!";
      const highlight = createMockHighlight("hl_1", 7, 12);

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      const highlightSpan = screen.getByText("world");

      fireEvent.mouseEnter(highlightSpan);
      expect(useUIStore.getState().hoveredHighlightId).toBe("hl_1");

      fireEvent.mouseLeave(highlightSpan);
      expect(useUIStore.getState().hoveredHighlightId).toBeNull();
    });

    test("active highlight has distinct styling", () => {
      const text = "Hello, world!";
      const highlight = createMockHighlight("hl_1", 7, 12);

      // Set active highlight before render
      act(() => {
        useUIStore.getState().setActiveHighlightId("hl_1");
      });

      render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={[highlight]}
        />
      );

      const highlightSpan = screen.getByText("world");
      expect(highlightSpan.className).toContain("ring-2");
    });
  });

  describe("performance smoke test", () => {
    test("renders large text with many highlights without error", () => {
      // Generate 10k character text
      const text = "A".repeat(10000);

      // Generate 300 non-overlapping highlights (every 30 chars, 10 chars each)
      const highlights: HighlightItem[] = [];
      for (let i = 0; i < 300; i++) {
        highlights.push(
          createMockHighlight(`hl_${i}`, i * 30, i * 30 + 10)
        );
      }

      // Should render without throwing
      const { container } = render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={highlights}
        />
      );

      // Verify correct number of highlight spans
      const highlightSpans = container.querySelectorAll("[data-highlight-id]");
      expect(highlightSpans.length).toBe(300);
    });

    test("renders large text with 500 highlights", () => {
      const text = "X".repeat(20000);

      const highlights: HighlightItem[] = [];
      for (let i = 0; i < 500; i++) {
        highlights.push(
          createMockHighlight(`hl_${i}`, i * 35, i * 35 + 15)
        );
      }

      const { container } = render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={highlights}
        />
      );

      const highlightSpans = container.querySelectorAll("[data-highlight-id]");
      expect(highlightSpans.length).toBe(500);
    });
  });

  describe("sorting and determinism", () => {
    test("highlights are sorted by text_start for deterministic rendering", () => {
      const text = "ABCDEFGHIJ";
      // Add highlights out of order
      const highlights = [
        createMockHighlight("hl_3", 6, 8), // "GH"
        createMockHighlight("hl_1", 0, 2), // "AB"
        createMockHighlight("hl_2", 3, 5), // "DE"
      ];

      const { container } = render(
        <HtmlHighlightReader
          canonicalText={text}
          highlights={highlights}
        />
      );

      // Get all highlight spans in DOM order
      const spans = container.querySelectorAll("[data-highlight-id]");

      // Should be in sorted order by position
      expect(spans[0]).toHaveAttribute("data-highlight-id", "hl_1");
      expect(spans[1]).toHaveAttribute("data-highlight-id", "hl_2");
      expect(spans[2]).toHaveAttribute("data-highlight-id", "hl_3");
    });
  });
});

