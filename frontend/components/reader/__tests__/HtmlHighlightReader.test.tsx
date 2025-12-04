import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { describe, test, expect, beforeEach, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { HtmlHighlightReader } from "../HtmlHighlightReader";
import { useUIStore } from "@/lib/state/ui";
import type { HighlightItem } from "@/lib/generated-api";

// Mock scrollIntoView since it's not available in JSDOM
Element.prototype.scrollIntoView = vi.fn();

// Mock the highlights API
vi.mock("@/lib/api/highlights", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    createHighlight: vi.fn(),
    fetchDocumentHighlights: vi.fn(),
  };
});

// Import mocked functions
import { createHighlight } from "@/lib/api/highlights";
const mockCreateHighlight = vi.mocked(createHighlight);

/**
 * Create a wrapper with QueryClient for hooks that need it.
 */
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

/**
 * Create a mock highlight for testing.
 * Defaults to anchor_type="text" for HTML/EPUB testing.
 */
function createMockHighlight(
  id: string,
  textStart: number,
  textEnd: number,
  quote: string = "",
  options?: { anchor_type?: "text" | "pdf" | "transcript"; color?: string }
): HighlightItem {
  return {
    id,
    document_id: "doc_test",
    anchor_type: options?.anchor_type ?? "text",
    text_start: textStart,
    text_end: textEnd,
    quote: quote || `[${textStart}-${textEnd}]`,
    color: options?.color ?? "yellow",
    pdf_page_number: null,
    pdf_char_offset: null,
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
    vi.clearAllMocks();
  });

  describe("basic rendering", () => {
    test("renders plain text when no highlights", () => {
      render(
        <HtmlHighlightReader
          canonicalText="Hello, world!"
          highlights={[]}
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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
        />,
        { wrapper: createWrapper() }
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

// =============================================================================
// Highlight Creation Flow Tests (PR6)
// =============================================================================

describe("HtmlHighlightReader - highlight creation flow", () => {
  beforeEach(() => {
    resetUIStore();
    vi.clearAllMocks();
    // Reset window.getSelection mock
    vi.spyOn(window, "getSelection").mockRestore();
  });

  /**
   * Helper to mock window.getSelection with specific text.
   * This simulates the browser selection API.
   */
  function mockSelection(
    selectedText: string,
    isCollapsed: boolean = false,
    containerElement?: Element | null
  ) {
    const mockRange = {
      toString: () => selectedText,
      commonAncestorContainer: containerElement,
    };

    const mockSelectionObj = {
      isCollapsed,
      toString: () => selectedText,
      anchorNode: containerElement,
      focusNode: containerElement,
      removeAllRanges: vi.fn(),
      getRangeAt: () => mockRange,
      rangeCount: isCollapsed ? 0 : 1,
    };

    vi.spyOn(window, "getSelection").mockReturnValue(
      mockSelectionObj as unknown as Selection
    );

    return mockSelectionObj;
  }

  test("does not show selection UI when documentId is not provided", () => {
    const text = "Hello, world!";

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        // No documentId - selection disabled
      />,
      { wrapper: createWrapper() }
    );

    // Trigger mouseup
    const reader = screen.getByTestId("html-reader");
    mockSelection("world", false, reader);
    fireEvent.mouseUp(reader);

    // Should not show selection action bar
    expect(screen.queryByTestId("selection-action-bar")).not.toBeInTheDocument();
  });

  test("shows selection action bar when text is selected", async () => {
    const text = "Hello, world!";

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId="doc_test123"
      />,
      { wrapper: createWrapper() }
    );

    // Setup mock selection before mouseup
    const reader = screen.getByTestId("html-reader");
    mockSelection("world", false, reader);

    // Trigger mouseup
    fireEvent.mouseUp(reader);

    // Should show selection action bar
    expect(screen.getByTestId("selection-action-bar")).toBeInTheDocument();
    expect(screen.getByTestId("create-highlight-btn")).toBeInTheDocument();
    expect(screen.getByTestId("cancel-selection-btn")).toBeInTheDocument();
  });

  test("does not show selection UI for collapsed (empty) selection", () => {
    const text = "Hello, world!";

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId="doc_test123"
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    mockSelection("", true, reader); // collapsed selection

    fireEvent.mouseUp(reader);

    expect(screen.queryByTestId("selection-action-bar")).not.toBeInTheDocument();
  });

  test("cancel button clears selection state", async () => {
    const text = "Hello, world!";

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId="doc_test123"
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    const mockSel = mockSelection("world", false, reader);

    // Trigger selection
    fireEvent.mouseUp(reader);
    expect(screen.getByTestId("selection-action-bar")).toBeInTheDocument();

    // Click cancel
    fireEvent.click(screen.getByTestId("cancel-selection-btn"));

    // Action bar should disappear
    expect(screen.queryByTestId("selection-action-bar")).not.toBeInTheDocument();
    expect(mockSel.removeAllRanges).toHaveBeenCalled();
  });

  test("escape key cancels selection", async () => {
    const text = "Hello, world!";

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId="doc_test123"
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    const mockSel = mockSelection("world", false, reader);

    // Trigger selection
    fireEvent.mouseUp(reader);
    expect(screen.getByTestId("selection-action-bar")).toBeInTheDocument();

    // Press escape
    fireEvent.keyDown(document, { key: "Escape" });

    // Action bar should disappear
    expect(screen.queryByTestId("selection-action-bar")).not.toBeInTheDocument();
    expect(mockSel.removeAllRanges).toHaveBeenCalled();
  });

  test("clicking outside action bar cancels selection", async () => {
    const text = "Hello, world!";

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId="doc_test123"
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    const mockSel = mockSelection("world", false, reader);

    // Trigger selection
    fireEvent.mouseUp(reader);
    expect(screen.getByTestId("selection-action-bar")).toBeInTheDocument();

    // Click outside (on document body)
    fireEvent.mouseDown(document.body);

    // Action bar should disappear
    expect(screen.queryByTestId("selection-action-bar")).not.toBeInTheDocument();
    expect(mockSel.removeAllRanges).toHaveBeenCalled();
  });

  test("calls createHighlight API with correct offsets on confirm", async () => {
    const text = "Hello, world!";
    const documentId = "doc_test123";

    const createdHighlight: HighlightItem = {
      id: "hl_new123",
      document_id: documentId,
      text_start: 7,
      text_end: 12,
      quote: "world",
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    };

    mockCreateHighlight.mockResolvedValue(createdHighlight);

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId={documentId}
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    mockSelection("world", false, reader);

    // Trigger selection
    fireEvent.mouseUp(reader);

    // Click create highlight
    await act(async () => {
      fireEvent.click(screen.getByTestId("create-highlight-btn"));
    });

    // Verify API was called with correct offsets
    await waitFor(() => {
      expect(mockCreateHighlight).toHaveBeenCalledWith({
        documentId,
        textStart: 7, // "world" starts at index 7
        textEnd: 12, // "world" ends at index 12
      });
    });
  });

  test("sets new highlight as active after creation", async () => {
    const text = "Hello, world!";
    const documentId = "doc_test123";

    const createdHighlight: HighlightItem = {
      id: "hl_new123",
      document_id: documentId,
      text_start: 7,
      text_end: 12,
      quote: "world",
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    };

    mockCreateHighlight.mockResolvedValue(createdHighlight);

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId={documentId}
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    mockSelection("world", false, reader);

    fireEvent.mouseUp(reader);

    await act(async () => {
      fireEvent.click(screen.getByTestId("create-highlight-btn"));
    });

    // Wait for mutation to complete
    await waitFor(() => {
      expect(useUIStore.getState().activeHighlightId).toBe("hl_new123");
    });
  });

  test("calls onHighlightCreated callback after successful creation", async () => {
    const text = "Hello, world!";
    const documentId = "doc_test123";
    const onHighlightCreated = vi.fn();

    const createdHighlight: HighlightItem = {
      id: "hl_new123",
      document_id: documentId,
      text_start: 7,
      text_end: 12,
      quote: "world",
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    };

    mockCreateHighlight.mockResolvedValue(createdHighlight);

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId={documentId}
        onHighlightCreated={onHighlightCreated}
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    mockSelection("world", false, reader);

    fireEvent.mouseUp(reader);

    await act(async () => {
      fireEvent.click(screen.getByTestId("create-highlight-btn"));
    });

    await waitFor(() => {
      expect(onHighlightCreated).toHaveBeenCalledWith(createdHighlight);
    });
  });

  test("shows error message when selection cannot be resolved", () => {
    const text = "Hello, world!";

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId="doc_test123"
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    // Mock a selection that doesn't exist in the canonical text
    mockSelection("nonexistent text", false, reader);

    fireEvent.mouseUp(reader);

    // Should show error, not action bar
    expect(screen.queryByTestId("selection-action-bar")).not.toBeInTheDocument();
    expect(screen.getByTestId("selection-error")).toBeInTheDocument();
    expect(screen.getByText(/Could not map selection/)).toBeInTheDocument();
  });

  test("shows error when API call fails", async () => {
    const text = "Hello, world!";
    const documentId = "doc_test123";
    const onHighlightError = vi.fn();

    mockCreateHighlight.mockRejectedValue(new Error("Server error"));

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId={documentId}
        onHighlightError={onHighlightError}
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    mockSelection("world", false, reader);

    fireEvent.mouseUp(reader);

    await act(async () => {
      fireEvent.click(screen.getByTestId("create-highlight-btn"));
    });

    // Should show error message
    await waitFor(() => {
      expect(screen.getByTestId("selection-error")).toBeInTheDocument();
    });

    expect(onHighlightError).toHaveBeenCalled();
  });

  test("clears selection action bar after successful creation", async () => {
    const text = "Hello, world!";
    const documentId = "doc_test123";

    const createdHighlight: HighlightItem = {
      id: "hl_new123",
      document_id: documentId,
      text_start: 7,
      text_end: 12,
      quote: "world",
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    };

    mockCreateHighlight.mockResolvedValue(createdHighlight);

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId={documentId}
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    const mockSel = mockSelection("world", false, reader);

    fireEvent.mouseUp(reader);
    expect(screen.getByTestId("selection-action-bar")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId("create-highlight-btn"));
    });

    await waitFor(() => {
      expect(screen.queryByTestId("selection-action-bar")).not.toBeInTheDocument();
    });

    expect(mockSel.removeAllRanges).toHaveBeenCalled();
  });

  test("disables create button while creation is pending", async () => {
    const text = "Hello, world!";
    const documentId = "doc_test123";

    // Make the API call hang
    let resolvePromise: (value: HighlightItem) => void;
    mockCreateHighlight.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePromise = resolve;
        })
    );

    render(
      <HtmlHighlightReader
        canonicalText={text}
        highlights={[]}
        documentId={documentId}
      />,
      { wrapper: createWrapper() }
    );

    const reader = screen.getByTestId("html-reader");
    mockSelection("world", false, reader);

    fireEvent.mouseUp(reader);

    const createBtn = screen.getByTestId("create-highlight-btn");
    expect(createBtn).not.toBeDisabled();

    // Click to start creation
    fireEvent.click(createBtn);

    // Button should be disabled while pending
    await waitFor(() => {
      expect(createBtn).toBeDisabled();
      expect(createBtn).toHaveTextContent("Creating...");
    });

    // Resolve the promise
    await act(async () => {
      resolvePromise!({
        id: "hl_new123",
        document_id: documentId,
        text_start: 7,
        text_end: 12,
        quote: "world",
        created_at: "2025-01-01T12:00:00Z",
        updated_at: "2025-01-01T12:00:00Z",
      });
    });
  });
});

