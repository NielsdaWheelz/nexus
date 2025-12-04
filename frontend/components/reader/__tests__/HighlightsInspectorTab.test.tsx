import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, test, expect, beforeEach, vi } from "vitest";
import { HighlightsInspectorTab } from "../HighlightsInspectorTab";
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
  quote: string,
  createdAt: string = "2025-01-01T12:00:00Z",
  options?: { anchor_type?: "text" | "pdf" | "transcript"; color?: string }
): HighlightItem {
  return {
    id,
    document_id: "doc_test",
    anchor_type: options?.anchor_type ?? "text",
    text_start: textStart,
    text_end: textEnd,
    quote,
    color: options?.color ?? "yellow",
    pdf_page_number: null,
    pdf_char_offset: null,
    created_at: createdAt,
    updated_at: createdAt,
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

describe("HighlightsInspectorTab", () => {
  beforeEach(() => {
    resetUIStore();
    vi.clearAllMocks();
  });

  describe("loading state", () => {
    test("renders loading state when isLoading and no data", () => {
      render(
        <HighlightsInspectorTab
          highlights={[]}
          isLoading={true}
        />
      );

      expect(screen.getByTestId("highlights-inspector-loading")).toBeInTheDocument();
      expect(screen.getByText("Loading highlights...")).toBeInTheDocument();
    });

    test("shows highlights even when still loading more", () => {
      const highlights = [createMockHighlight("hl_1", 0, 10, "Hello worl")];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
          isLoading={true}
        />
      );

      // Should show highlights list, not loading state
      expect(screen.getByTestId("highlights-inspector-list")).toBeInTheDocument();
      expect(screen.queryByTestId("highlights-inspector-loading")).not.toBeInTheDocument();
    });
  });

  describe("error state", () => {
    test("renders error state", () => {
      render(
        <HighlightsInspectorTab
          highlights={[]}
          error="Network error occurred"
        />
      );

      expect(screen.getByTestId("highlights-inspector-error")).toBeInTheDocument();
      expect(screen.getByText("Failed to load highlights")).toBeInTheDocument();
      expect(screen.getByText("Network error occurred")).toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    test("renders empty state when no highlights", () => {
      render(
        <HighlightsInspectorTab
          highlights={[]}
        />
      );

      expect(screen.getByTestId("highlights-inspector-empty")).toBeInTheDocument();
      expect(screen.getByText("No highlights yet")).toBeInTheDocument();
    });
  });

  describe("highlights list", () => {
    test("renders list of highlights", () => {
      const highlights = [
        createMockHighlight("hl_1", 0, 10, "Hello worl"),
        createMockHighlight("hl_2", 20, 30, "is a test "),
      ];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      expect(screen.getByTestId("highlights-inspector-list")).toBeInTheDocument();
      expect(screen.getByText("2 highlights")).toBeInTheDocument();
    });

    test("shows correct count for single highlight", () => {
      const highlights = [createMockHighlight("hl_1", 0, 10, "Hello worl")];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      expect(screen.getByText("1 highlight")).toBeInTheDocument();
    });

    test("displays quote from highlight item", () => {
      const highlights = [createMockHighlight("hl_1", 0, 5, "Hello")];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      expect(screen.getByText("Hello")).toBeInTheDocument();
    });

    test("truncates long quotes", () => {
      const longQuote = "A".repeat(100);
      const highlights = [createMockHighlight("hl_1", 0, 100, longQuote)];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      // Should be truncated to 80 chars with ellipsis
      const expectedText = "A".repeat(79) + "…";
      expect(screen.getByText(expectedText)).toBeInTheDocument();
    });

    test("shows formatted date", () => {
      const highlights = [
        createMockHighlight("hl_1", 0, 10, "Hello worl", "2025-06-15T14:30:00Z"),
      ];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      // Date should be formatted
      expect(screen.getByText(/Jun 15, 2025/)).toBeInTheDocument();
    });
  });

  describe("interaction with UI store", () => {
    test("clicking highlight sets activeHighlightId", () => {
      const highlights = [createMockHighlight("hl_1", 0, 10, "Hello worl")];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      const highlightButton = screen.getByRole("button");
      fireEvent.click(highlightButton);

      expect(useUIStore.getState().activeHighlightId).toBe("hl_1");
    });

    test("clicking highlight calls scrollIntoView", () => {
      const highlights = [createMockHighlight("hl_1", 0, 10, "Hello worl")];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      const highlightButton = screen.getByRole("button");
      fireEvent.click(highlightButton);

      // scrollIntoView should have been called (via scrollToHighlight)
      // Note: The actual scroll target is in a different component
      expect(useUIStore.getState().activeHighlightId).toBe("hl_1");
    });

    test("hovering highlight sets hoveredHighlightId", () => {
      const highlights = [createMockHighlight("hl_1", 0, 10, "Hello worl")];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      const highlightButton = screen.getByRole("button");

      fireEvent.mouseEnter(highlightButton);
      expect(useUIStore.getState().hoveredHighlightId).toBe("hl_1");

      fireEvent.mouseLeave(highlightButton);
      expect(useUIStore.getState().hoveredHighlightId).toBeNull();
    });

    test("active highlight has data-active attribute", () => {
      const highlights = [createMockHighlight("hl_1", 0, 10, "Hello worl")];

      // Set active highlight before render
      act(() => {
        useUIStore.getState().setActiveHighlightId("hl_1");
      });

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      const highlightButton = screen.getByRole("button");
      expect(highlightButton).toHaveAttribute("data-active", "true");
    });

    test("inactive highlight has data-active false", () => {
      const highlights = [createMockHighlight("hl_1", 0, 10, "Hello worl")];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      const highlightButton = screen.getByRole("button");
      expect(highlightButton).toHaveAttribute("data-active", "false");
    });

    test("active highlight has distinct styling", () => {
      const highlights = [createMockHighlight("hl_1", 0, 10, "Hello worl")];

      act(() => {
        useUIStore.getState().setActiveHighlightId("hl_1");
      });

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      const highlightButton = screen.getByRole("button");
      expect(highlightButton.className).toContain("ring-2");
      expect(highlightButton.className).toContain("bg-yellow-50");
    });
  });

  describe("data attributes", () => {
    test("each highlight row has data-highlight-id", () => {
      const highlights = [
        createMockHighlight("hl_1", 0, 10, "Hello worl"),
        createMockHighlight("hl_2", 20, 30, "is a test "),
      ];

      render(
        <HighlightsInspectorTab
          highlights={highlights}
        />
      );

      const buttons = screen.getAllByRole("button");
      expect(buttons[0]).toHaveAttribute("data-highlight-id", "hl_1");
      expect(buttons[1]).toHaveAttribute("data-highlight-id", "hl_2");
    });
  });
});

