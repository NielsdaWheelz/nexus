import { render, screen, waitFor } from "@testing-library/react";
import { describe, test, expect, beforeEach, vi, type Mock } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { PdfReader } from "../PdfReader";
import type { DocumentListItem } from "@/lib/generated-api";

// Mock scrollIntoView since it's not available in JSDOM
Element.prototype.scrollIntoView = vi.fn();

// Mock useDocumentBlob hook
vi.mock("@/lib/hooks/useDocumentBlob", () => ({
  useDocumentBlob: vi.fn(),
}));

// Import mocked hook
import { useDocumentBlob } from "@/lib/hooks/useDocumentBlob";
const mockUseDocumentBlob = useDocumentBlob as Mock;

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

describe("PdfReader", () => {
  beforeEach(() => {
    vi.clearAllMocks();

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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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
          document={createMockDocument()}
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

