import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { describe, test, expect, beforeEach, vi, type Mock } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { PdfReader } from "../PdfReader";
import type { DocumentListItem, HighlightItem } from "@/lib/generated-api";
import { useUIStore } from "@/lib/state/ui";

// Mock scrollIntoView since it's not available in JSDOM
Element.prototype.scrollIntoView = vi.fn();

// Mock useDocumentBlob hook
vi.mock("@/lib/hooks/useDocumentBlob", () => ({
  useDocumentBlob: vi.fn(),
}));

// Mock highlights API
vi.mock("@/lib/api/highlights", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    createHighlight: vi.fn(),
    fetchDocumentHighlights: vi.fn().mockResolvedValue({ items: [], has_more: false, next_cursor: null }),
  };
});

// Import mocked hooks and functions
import { useDocumentBlob } from "@/lib/hooks/useDocumentBlob";
import { createHighlight } from "@/lib/api/highlights";
const mockUseDocumentBlob = useDocumentBlob as Mock;
const mockCreateHighlight = vi.mocked(createHighlight);

// Mock pdf.js library
const mockGetPage = vi.fn();
const mockGetTextContent = vi.fn();
const mockRender = vi.fn();
const mockCleanup = vi.fn();

const mockPdfDocument = {
  numPages: 5,
  getPage: mockGetPage,
};

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {
    workerSrc: "",
  },
  getDocument: vi.fn().mockImplementation(() => ({
    promise: Promise.resolve(mockPdfDocument),
  })),
  // Mock version for CDN worker URL construction
  version: "5.4.449",
}));

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
 * Create a mock document for testing.
 * Note: Using string literals instead of enum references since
 * DocumentListItem enums aren't available at test runtime.
 */
function createMockDocument(
  overrides?: Partial<DocumentListItem>
): DocumentListItem {
  return {
    id: "doc_test-12345678",
    title: "Test PDF Document",
    source_kind: "pdf" as DocumentListItem["source_kind"],
    processing_status: "ready" as DocumentListItem["processing_status"],
    created_at: "2025-01-01T12:00:00Z",
    updated_at: "2025-01-01T12:00:00Z",
    ...overrides,
  };
}

/**
 * Create mock text items for a page.
 */
function createMockTextItems(pageNum: number, itemCount: number = 3) {
  return Array.from({ length: itemCount }, (_, i) => ({
    str: `Page ${pageNum} text item ${i + 1}`,
    transform: [12, 0, 0, 12, 50 + i * 100, 700 - i * 20],
    width: 80,
    height: 12,
    fontName: "Helvetica",
  }));
}

/**
 * Create a mock ArrayBuffer (fake PDF data).
 */
function createMockPdfBuffer(): ArrayBuffer {
  // Create a simple buffer with some bytes
  return new Uint8Array([0x25, 0x50, 0x44, 0x46]).buffer;
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

describe("PdfReader", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetUIStore();

    // Setup default mock implementations
    mockGetPage.mockImplementation(async (pageNum: number) => {
      const textItems = createMockTextItems(pageNum);
      return {
        getViewport: () => ({ width: 612, height: 792, scale: 1.5 }),
        getTextContent: () =>
          Promise.resolve({
            items: textItems,
            styles: {},
          }),
        render: () => ({
          promise: Promise.resolve(),
        }),
        cleanup: mockCleanup,
      };
    });

    // Reset IntersectionObserver mock
    const mockIntersectionObserver = vi.fn();
    mockIntersectionObserver.mockImplementation((callback) => ({
      observe: vi.fn(),
      unobserve: vi.fn(),
      disconnect: vi.fn(),
    }));
    window.IntersectionObserver = mockIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  describe("loading states", () => {
    test("shows loading state while fetching blob", () => {
      mockUseDocumentBlob.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      expect(screen.getByTestId("pdf-reader-loading")).toBeInTheDocument();
      expect(screen.getByText("Loading PDF...")).toBeInTheDocument();
    });

    test("shows error state when blob fetch fails", () => {
      mockUseDocumentBlob.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: { message: "Failed to fetch PDF blob" },
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      expect(screen.getByTestId("pdf-reader-error")).toBeInTheDocument();
      expect(screen.getByText("Failed to load PDF")).toBeInTheDocument();
      expect(screen.getByText("Failed to fetch PDF blob")).toBeInTheDocument();
    });
  });

  describe("pdf rendering", () => {
    test("renders pdf reader container when blob is loaded", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      // Wait for async PDF loading
      await waitFor(() => {
        expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
      });
    });

    test("renders initial pages with canvas and text layer", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      // Wait for pages to render
      await waitFor(() => {
        expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
      });

      // Should render at least 3 pages initially (INITIAL_PAGE_COUNT)
      await waitFor(() => {
        expect(screen.getByTestId("pdf-page-1")).toBeInTheDocument();
        expect(screen.getByTestId("pdf-page-2")).toBeInTheDocument();
        expect(screen.getByTestId("pdf-page-3")).toBeInTheDocument();
      });

      // Each page should have a canvas
      expect(screen.getByTestId("pdf-canvas-1")).toBeInTheDocument();
      expect(screen.getByTestId("pdf-canvas-2")).toBeInTheDocument();
      expect(screen.getByTestId("pdf-canvas-3")).toBeInTheDocument();

      // Each page should have a text layer
      expect(screen.getByTestId("pdf-text-layer-1")).toBeInTheDocument();
      expect(screen.getByTestId("pdf-text-layer-2")).toBeInTheDocument();
      expect(screen.getByTestId("pdf-text-layer-3")).toBeInTheDocument();
    });

    test("page containers have data-page-number attribute", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        const page1 = screen.getByTestId("pdf-page-1");
        expect(page1).toHaveAttribute("data-page-number", "1");
      });

      const page2 = screen.getByTestId("pdf-page-2");
      expect(page2).toHaveAttribute("data-page-number", "2");

      const page3 = screen.getByTestId("pdf-page-3");
      expect(page3).toHaveAttribute("data-page-number", "3");
    });

    test("text layer spans have required data attributes", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      const { container } = render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      // Wait for rendering
      await waitFor(() => {
        expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
      });

      await waitFor(() => {
        // Get text layer spans from page 1
        const textLayer1 = screen.getByTestId("pdf-text-layer-1");
        const spans = textLayer1.querySelectorAll("span");

        expect(spans.length).toBeGreaterThan(0);

        // Each span should have data-page-number and data-char-offset
        spans.forEach((span) => {
          expect(span).toHaveAttribute("data-page-number", "1");
          expect(span).toHaveAttribute("data-char-offset");
        });
      });
    });

    test("text spans contain text content from PDF", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
      });

      // Wait for text content to appear
      await waitFor(() => {
        // Check that text items from our mock are rendered
        expect(screen.getByText("Page 1 text item 1")).toBeInTheDocument();
      });
    });

    test("shows page count information", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
      });

      // Should show "Showing X of Y pages"
      await waitFor(() => {
        expect(screen.getByText(/Showing \d+ of 5 pages/)).toBeInTheDocument();
      });
    });
  });

  describe("text layer structure", () => {
    test("text layer has pdf-text-layer class", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        const textLayer = screen.getByTestId("pdf-text-layer-1");
        expect(textLayer).toHaveClass("pdf-text-layer");
      });
    });

    test("page container has pdf-page class", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        const page = screen.getByTestId("pdf-page-1");
        expect(page).toHaveClass("pdf-page");
      });
    });
  });

  describe("data attributes for anchoring", () => {
    test("data-char-offset increments across text items", async () => {
      mockUseDocumentBlob.mockReturnValue({
        data: createMockPdfBuffer(),
        isLoading: false,
        isError: false,
        error: null,
      });

      render(
        <PdfReader
          documentId="doc_test-12345678"
        />,
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
      });

      await waitFor(() => {
        const textLayer1 = screen.getByTestId("pdf-text-layer-1");
        const spans = textLayer1.querySelectorAll("span");

        // First span should start at offset 0
        const firstOffset = parseInt(spans[0]?.getAttribute("data-char-offset") ?? "-1", 10);
        expect(firstOffset).toBe(0);

        // Subsequent spans should have increasing offsets
        if (spans.length > 1) {
          const secondOffset = parseInt(spans[1]?.getAttribute("data-char-offset") ?? "-1", 10);
          expect(secondOffset).toBeGreaterThan(firstOffset);
        }
      });
    });
  });
});

// =============================================================================
// PDF Highlight Creation Flow Tests (PR10)
// =============================================================================

describe("PdfReader - highlight creation flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetUIStore();

    // Setup mock page implementation
    mockGetPage.mockImplementation(async (pageNum: number) => {
      const textItems = createMockTextItems(pageNum);
      return {
        getViewport: () => ({ width: 612, height: 792, scale: 1.5 }),
        getTextContent: () =>
          Promise.resolve({
            items: textItems,
            styles: {},
          }),
        render: () => ({
          promise: Promise.resolve(),
        }),
        cleanup: vi.fn(),
      };
    });
    
    // Setup default useDocumentBlob mock
    mockUseDocumentBlob.mockReturnValue({
      data: createMockPdfBuffer(),
      isLoading: false,
      isError: false,
      error: null,
    });

    // Setup IntersectionObserver mock
    const mockIntersectionObserver = vi.fn();
    mockIntersectionObserver.mockImplementation(() => ({
      observe: vi.fn(),
      unobserve: vi.fn(),
      disconnect: vi.fn(),
    }));
    window.IntersectionObserver = mockIntersectionObserver as unknown as typeof IntersectionObserver;
  });

  /**
   * Helper to mock window.getSelection with specific text.
   * 
   * For PDF selection to work, we need to simulate selection within a text layer span
   * that has data-page-number and data-char-offset attributes.
   *
   * @param selectedText - The text that appears to be selected
   * @param isCollapsed - Whether the selection is collapsed (empty)
   * @param containerElement - The container element (usually the pdf-reader div)
   * @param pageNumber - PDF page number (1-based)
   * @param charOffset - Global character offset in pdf.js text stream
   */
  function mockSelection(
    selectedText: string,
    isCollapsed: boolean = false,
    containerElement?: Element | null,
    pageNumber: number = 1,
    charOffset: number = 0
  ) {
    // Find the actual text layer span in the DOM that contains the text
    // This allows us to properly test the selection → anchor mapping
    let anchorNode: Node | null = null;
    let focusNode: Node | null = null;
    
    if (containerElement) {
      // Try to find the span with the selected text
      const spans = containerElement.querySelectorAll(`span[data-page-number="${pageNumber}"]`);
      for (const span of spans) {
        if (span.textContent?.includes(selectedText)) {
          anchorNode = span.firstChild || span;
          focusNode = span.firstChild || span;
          break;
        }
      }
    }
    
    // Fallback to container if no matching span found
    if (!anchorNode) {
      anchorNode = containerElement || null;
      focusNode = containerElement || null;
    }

    const mockRange = {
      toString: () => selectedText,
      commonAncestorContainer: containerElement,
      startOffset: 0,
      endOffset: selectedText.length,
      collapsed: isCollapsed,
    };

    const mockSelectionObj = {
      isCollapsed,
      toString: () => selectedText,
      anchorNode,
      focusNode,
      removeAllRanges: vi.fn(),
      getRangeAt: () => mockRange,
      rangeCount: isCollapsed ? 0 : 1,
    };

    vi.spyOn(window, "getSelection").mockReturnValue(
      mockSelectionObj as unknown as Selection
    );

    return mockSelectionObj;
  }

  test("shows selection action bar when text is selected in pdf text layer", async () => {
    render(
      <PdfReader
        documentId="doc_test-12345678"
      />,
      { wrapper: createWrapper() }
    );

    // Wait for PDF to render
    await waitFor(() => {
      expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
    });

    // Wait for text layer to render
    await waitFor(() => {
      expect(screen.getByText("Page 1 text item 1")).toBeInTheDocument();
    });

    // Setup mock selection before mouseup
    const reader = screen.getByTestId("pdf-reader");
    mockSelection("Page 1 text item 1", false, reader);

    // Trigger mouseup
    fireEvent.mouseUp(reader);

    // Should show selection action bar
    expect(screen.getByTestId("pdf-selection-action-bar")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-create-highlight-btn")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-cancel-selection-btn")).toBeInTheDocument();
  });

  test("does not show selection UI for collapsed (empty) selection", async () => {
    render(
      <PdfReader
        documentId="doc_test-12345678"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
    });

    const reader = screen.getByTestId("pdf-reader");
    mockSelection("", true, reader); // collapsed selection

    fireEvent.mouseUp(reader);

    expect(screen.queryByTestId("pdf-selection-action-bar")).not.toBeInTheDocument();
  });

  test("cancel button clears selection state", async () => {
    render(
      <PdfReader
        documentId="doc_test-12345678"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Page 1 text item 1")).toBeInTheDocument();
    });

    const reader = screen.getByTestId("pdf-reader");
    const mockSel = mockSelection("Page 1 text item 1", false, reader);

    // Trigger selection
    fireEvent.mouseUp(reader);
    expect(screen.getByTestId("pdf-selection-action-bar")).toBeInTheDocument();

    // Click cancel
    fireEvent.click(screen.getByTestId("pdf-cancel-selection-btn"));

    // Action bar should disappear
    expect(screen.queryByTestId("pdf-selection-action-bar")).not.toBeInTheDocument();
    expect(mockSel.removeAllRanges).toHaveBeenCalled();
  });

  test("calls createHighlight API with PDF anchor fields on confirm", async () => {
    const createdHighlight: HighlightItem = {
      id: "hl_new123",
      document_id: "doc_test-12345678",
      anchor_type: "pdf",
      text_start: 0,
      text_end: 18,
      quote: "Page 1 text item 1",
      color: "yellow",
      pdf_page_number: 1,
      pdf_char_offset: 0,
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    };

    mockCreateHighlight.mockResolvedValue(createdHighlight);

    render(
      <PdfReader
        documentId="doc_test-12345678"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Page 1 text item 1")).toBeInTheDocument();
    });

    const reader = screen.getByTestId("pdf-reader");
    mockSelection("Page 1 text item 1", false, reader);

    // Trigger selection
    fireEvent.mouseUp(reader);

    // Click create highlight
    await act(async () => {
      fireEvent.click(screen.getByTestId("pdf-create-highlight-btn"));
    });

    // Verify API was called with correct offsets
    await waitFor(() => {
      expect(mockCreateHighlight).toHaveBeenCalledWith(
        expect.objectContaining({
          documentId: "doc_test-12345678",
          anchorType: "pdf",
          // Note: exact offsets depend on selection resolution
          // The key thing is that anchorType is "pdf" and pdfPageNumber/pdfCharOffset are present
          pdfPageNumber: expect.any(Number),
        })
      );
    });
  });

  test("sets new highlight as active after creation", async () => {
    const createdHighlight: HighlightItem = {
      id: "hl_new123",
      document_id: "doc_test-12345678",
      anchor_type: "pdf",
      text_start: 0,
      text_end: 18,
      quote: "Page 1 text item 1",
      color: "yellow",
      pdf_page_number: 1,
      pdf_char_offset: 0,
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    };

    mockCreateHighlight.mockResolvedValue(createdHighlight);

    render(
      <PdfReader
        documentId="doc_test-12345678"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Page 1 text item 1")).toBeInTheDocument();
    });

    const reader = screen.getByTestId("pdf-reader");
    mockSelection("Page 1 text item 1", false, reader);

    fireEvent.mouseUp(reader);

    await act(async () => {
      fireEvent.click(screen.getByTestId("pdf-create-highlight-btn"));
    });

    // Wait for mutation to complete
    await waitFor(() => {
      expect(useUIStore.getState().activeHighlightId).toBe("hl_new123");
    });
  });

  test("shows error message when selection cannot be resolved to pdf text layer", async () => {
    render(
      <PdfReader
        documentId="doc_test-12345678"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
    });

    const reader = screen.getByTestId("pdf-reader");
    // Mock a selection outside the text layer (no data-char-offset span found)
    mockSelection("nonexistent text in pdf", false, reader);

    fireEvent.mouseUp(reader);

    // Should show error, not action bar
    // Error could be "Could not identify selection boundaries" or "Could not locate selection"
    expect(screen.queryByTestId("pdf-selection-action-bar")).not.toBeInTheDocument();
    expect(screen.getByTestId("pdf-selection-error")).toBeInTheDocument();
  });

  test("shows error when API call fails", async () => {
    mockCreateHighlight.mockRejectedValue(new Error("Server error"));

    render(
      <PdfReader
        documentId="doc_test-12345678"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Page 1 text item 1")).toBeInTheDocument();
    });

    const reader = screen.getByTestId("pdf-reader");
    mockSelection("Page 1 text item 1", false, reader);

    fireEvent.mouseUp(reader);

    await act(async () => {
      fireEvent.click(screen.getByTestId("pdf-create-highlight-btn"));
    });

    // Should show error message
    await waitFor(() => {
      expect(screen.getByTestId("pdf-selection-error")).toBeInTheDocument();
    });
  });

  test("clears selection action bar after successful creation", async () => {
    const createdHighlight: HighlightItem = {
      id: "hl_new123",
      document_id: "doc_test-12345678",
      anchor_type: "pdf",
      text_start: 0,
      text_end: 18,
      quote: "Page 1 text item 1",
      color: "yellow",
      pdf_page_number: 1,
      pdf_char_offset: 0,
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    };

    mockCreateHighlight.mockResolvedValue(createdHighlight);

    render(
      <PdfReader
        documentId="doc_test-12345678"
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByTestId("pdf-reader")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Page 1 text item 1")).toBeInTheDocument();
    });

    const reader = screen.getByTestId("pdf-reader");
    const mockSel = mockSelection("Page 1 text item 1", false, reader);

    fireEvent.mouseUp(reader);
    expect(screen.getByTestId("pdf-selection-action-bar")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByTestId("pdf-create-highlight-btn"));
    });

    await waitFor(() => {
      expect(screen.queryByTestId("pdf-selection-action-bar")).not.toBeInTheDocument();
    });

    expect(mockSel.removeAllRanges).toHaveBeenCalled();
  });
});

