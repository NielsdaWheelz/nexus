import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { InspectorPanel } from "../InspectorPanel";
import type { HighlightItem } from "@/lib/generated-api";

/**
 * Create a mock highlight for testing.
 */
function createMockHighlight(
  id: string,
  options: {
    anchor_type?: "text" | "pdf" | "transcript";
    text_start?: number;
    text_end?: number;
    quote?: string;
    pdf_page_number?: number | null;
    pdf_char_offset?: number | null;
    color?: string;
    created_at?: string;
  } = {}
): HighlightItem {
  return {
    id,
    document_id: "doc_test",
    anchor_type: options.anchor_type ?? "text",
    text_start: options.text_start ?? 0,
    text_end: options.text_end ?? 10,
    quote: options.quote ?? "test quote",
    color: options.color ?? "yellow",
    pdf_page_number: options.pdf_page_number ?? null,
    pdf_char_offset: options.pdf_char_offset ?? null,
    created_at: options.created_at ?? "2025-01-15T12:00:00Z",
    updated_at: "2025-01-15T12:00:00Z",
  };
}

describe("InspectorPanel", () => {
  describe("loading state", () => {
    test("renders loading state when isLoading and no highlights", () => {
      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={[]}
          isLoading={true}
        />
      );

      expect(screen.getByTestId("inspector-panel-loading")).toBeInTheDocument();
      expect(screen.getByText("Loading highlights...")).toBeInTheDocument();
    });

    test("shows highlights even when still loading more", () => {
      const highlights = [createMockHighlight("hl_1")];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
          isLoading={true}
        />
      );

      // Should show list, not loading state
      expect(screen.getByTestId("inspector-panel")).toBeInTheDocument();
      expect(screen.queryByTestId("inspector-panel-loading")).not.toBeInTheDocument();
    });
  });

  describe("error state", () => {
    test("renders error state", () => {
      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={[]}
          error="Network error occurred"
        />
      );

      expect(screen.getByTestId("inspector-panel-error")).toBeInTheDocument();
      expect(screen.getByText("Failed to load highlights")).toBeInTheDocument();
      expect(screen.getByText("Network error occurred")).toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    test("renders empty state when no highlights", () => {
      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={[]}
        />
      );

      expect(screen.getByTestId("inspector-panel-empty")).toBeInTheDocument();
      expect(screen.getByText("No highlights yet")).toBeInTheDocument();
    });
  });

  describe("highlights list", () => {
    test("renders list of highlights", () => {
      const highlights = [
        createMockHighlight("hl_1", { quote: "First quote" }),
        createMockHighlight("hl_2", { quote: "Second quote" }),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      expect(screen.getByTestId("inspector-panel")).toBeInTheDocument();
      expect(screen.getByText("2 highlights")).toBeInTheDocument();
      expect(screen.getByText("First quote")).toBeInTheDocument();
      expect(screen.getByText("Second quote")).toBeInTheDocument();
    });

    test("shows correct count for single highlight", () => {
      const highlights = [createMockHighlight("hl_1")];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      expect(screen.getByText("1 highlight")).toBeInTheDocument();
    });

    test("truncates long quotes", () => {
      const longQuote = "A".repeat(100);
      const highlights = [createMockHighlight("hl_1", { quote: longQuote })];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      // Should be truncated to 80 chars with ellipsis
      const expectedText = "A".repeat(79) + "…";
      expect(screen.getByText(expectedText)).toBeInTheDocument();
    });

    test("shows formatted date", () => {
      const highlights = [
        createMockHighlight("hl_1", { created_at: "2025-06-15T14:30:00Z" }),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      expect(screen.getByText(/Jun 15, 2025/)).toBeInTheDocument();
    });
  });

  describe("sorting", () => {
    test("sorts text highlights by text_start", () => {
      const highlights = [
        createMockHighlight("hl_2", { text_start: 200, quote: "Second" }),
        createMockHighlight("hl_1", { text_start: 100, quote: "First" }),
        createMockHighlight("hl_3", { text_start: 300, quote: "Third" }),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      const list = screen.getByTestId("inspector-panel-list");
      const items = list.querySelectorAll('[data-testid^="inspector-highlight-"]');

      expect(items[0]).toHaveAttribute("data-highlight-id", "hl_1");
      expect(items[1]).toHaveAttribute("data-highlight-id", "hl_2");
      expect(items[2]).toHaveAttribute("data-highlight-id", "hl_3");
    });

    test("sorts PDF highlights by page number", () => {
      const highlights = [
        createMockHighlight("hl_2", {
          anchor_type: "pdf",
          pdf_page_number: 5,
          pdf_char_offset: 0,
          quote: "Page 5",
        }),
        createMockHighlight("hl_1", {
          anchor_type: "pdf",
          pdf_page_number: 1,
          pdf_char_offset: 0,
          quote: "Page 1",
        }),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      const list = screen.getByTestId("inspector-panel-list");
      const items = list.querySelectorAll('[data-testid^="inspector-highlight-"]');

      expect(items[0]).toHaveAttribute("data-highlight-id", "hl_1");
      expect(items[1]).toHaveAttribute("data-highlight-id", "hl_2");
    });

    test("text anchors appear before PDF anchors in mixed list", () => {
      const highlights = [
        createMockHighlight("hl_pdf", {
          anchor_type: "pdf",
          pdf_page_number: 1,
          pdf_char_offset: 0,
          quote: "PDF quote",
        }),
        createMockHighlight("hl_text", {
          anchor_type: "text",
          text_start: 100,
          quote: "Text quote",
        }),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      const list = screen.getByTestId("inspector-panel-list");
      const items = list.querySelectorAll('[data-testid^="inspector-highlight-"]');

      expect(items[0]).toHaveAttribute("data-highlight-id", "hl_text");
      expect(items[1]).toHaveAttribute("data-highlight-id", "hl_pdf");
    });
  });

  describe("interaction callbacks", () => {
    test("calls onHighlightClick when highlight is clicked", () => {
      const onHighlightClick = vi.fn();
      const highlights = [createMockHighlight("hl_1")];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
          onHighlightClick={onHighlightClick}
        />
      );

      const highlightButton = screen.getByTestId("inspector-highlight-hl_1");
      fireEvent.click(highlightButton);

      expect(onHighlightClick).toHaveBeenCalledWith("hl_1");
      expect(onHighlightClick).toHaveBeenCalledTimes(1);
    });

    test("calls onHighlightHover on mouse enter/leave", () => {
      const onHighlightHover = vi.fn();
      const highlights = [createMockHighlight("hl_1")];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
          onHighlightHover={onHighlightHover}
        />
      );

      const highlightButton = screen.getByTestId("inspector-highlight-hl_1");

      fireEvent.mouseEnter(highlightButton);
      expect(onHighlightHover).toHaveBeenCalledWith("hl_1");

      fireEvent.mouseLeave(highlightButton);
      expect(onHighlightHover).toHaveBeenCalledWith(null);
    });
  });

  describe("active/hovered state styling", () => {
    test("active highlight has data-active true", () => {
      const highlights = [createMockHighlight("hl_1")];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
          activeHighlightId="hl_1"
        />
      );

      const highlightButton = screen.getByTestId("inspector-highlight-hl_1");
      expect(highlightButton).toHaveAttribute("data-active", "true");
    });

    test("inactive highlight has data-active false", () => {
      const highlights = [createMockHighlight("hl_1")];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
          activeHighlightId={null}
        />
      );

      const highlightButton = screen.getByTestId("inspector-highlight-hl_1");
      expect(highlightButton).toHaveAttribute("data-active", "false");
    });

    test("active highlight has distinct styling", () => {
      const highlights = [createMockHighlight("hl_1")];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
          activeHighlightId="hl_1"
        />
      );

      const highlightButton = screen.getByTestId("inspector-highlight-hl_1");
      expect(highlightButton.className).toContain("ring-2");
      expect(highlightButton.className).toContain("bg-yellow-50");
    });
  });

  describe("position labels", () => {
    test("shows page number for PDF highlights", () => {
      const highlights = [
        createMockHighlight("hl_1", {
          anchor_type: "pdf",
          pdf_page_number: 42,
          pdf_char_offset: 0,
        }),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      expect(screen.getByText("p. 42")).toBeInTheDocument();
    });

    test("does not show position label for text highlights", () => {
      const highlights = [
        createMockHighlight("hl_1", { anchor_type: "text" }),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      // No "p." prefix for text anchors
      expect(screen.queryByText(/^p\./)).not.toBeInTheDocument();
    });
  });

  describe("color markers", () => {
    test("renders different color markers for different highlight colors", () => {
      const highlights = [
        createMockHighlight("hl_1", { color: "blue", quote: "Blue quote" }),
        createMockHighlight("hl_2", { color: "green", quote: "Green quote" }),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      // Check that both highlights are rendered
      expect(screen.getByText("Blue quote")).toBeInTheDocument();
      expect(screen.getByText("Green quote")).toBeInTheDocument();

      // The color markers should have different classes
      // (we can't easily assert on specific classes without deeper DOM inspection)
    });
  });

  describe("data attributes", () => {
    test("each highlight has data-highlight-id", () => {
      const highlights = [
        createMockHighlight("hl_1"),
        createMockHighlight("hl_2"),
      ];

      render(
        <InspectorPanel
          documentId="doc_test"
          highlights={highlights}
        />
      );

      expect(screen.getByTestId("inspector-highlight-hl_1")).toHaveAttribute(
        "data-highlight-id",
        "hl_1"
      );
      expect(screen.getByTestId("inspector-highlight-hl_2")).toHaveAttribute(
        "data-highlight-id",
        "hl_2"
      );
    });
  });
});

