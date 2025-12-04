import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, describe, test, expect, beforeEach } from "vitest";
import type { ReactNode } from "react";

import DocumentDetailPage from "../page";
import { useUIStore } from "@/lib/state/ui";
import { DocumentListItem } from "@/lib/generated-api";

// Mock the useDocumentDetail hook
vi.mock("@/lib/hooks/useDocuments", () => ({
  useDocumentDetail: vi.fn(),
}));

// Mock the useDocumentBlob hook (for PdfReader)
vi.mock("@/lib/hooks/useDocumentBlob", () => ({
  useDocumentBlob: vi.fn(),
}));

// Mock the useDocumentContent hook (for HtmlHighlightReader)
vi.mock("@/lib/hooks/useDocumentContent", () => ({
  useDocumentContent: vi.fn(),
}));

// Mock the useDocumentHighlights hook
vi.mock("@/lib/hooks/useHighlights", () => ({
  useDocumentHighlights: vi.fn(),
  useCreateHighlight: vi.fn(() => ({ createHighlight: vi.fn(), isPending: false })),
}));

import { useDocumentDetail } from "@/lib/hooks/useDocuments";
import { useDocumentBlob } from "@/lib/hooks/useDocumentBlob";
import { useDocumentContent } from "@/lib/hooks/useDocumentContent";
import { useDocumentHighlights } from "@/lib/hooks/useHighlights";

const mockUseDocumentDetail = vi.mocked(useDocumentDetail);
const mockUseDocumentBlob = vi.mocked(useDocumentBlob);
const mockUseDocumentContent = vi.mocked(useDocumentContent);
const mockUseDocumentHighlights = vi.mocked(useDocumentHighlights);

// Mock next/link since we're testing outside Next.js context
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

// Test fixtures
// Note: Using PENDING status for tests that verify DocumentContent rendering,
// since "ready" PDF documents now render PdfReader instead of DocumentContent.
const mockDocument: DocumentListItem = {
  id: "doc_test-123",
  title: "Test Document",
  source_kind: DocumentListItem.source_kind.PDF,
  processing_status: DocumentListItem.processing_status.PENDING,
  created_at: "2025-01-15T10:00:00Z",
  updated_at: "2025-01-15T12:00:00Z",
};

/**
 * Create wrapper with QueryClientProvider.
 */
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

/**
 * Reset zustand store state between tests.
 */
function resetUIStore() {
  useUIStore.setState({
    isInspectorOpen: true,
    activeInspectorTab: "highlights",
  });
}

describe("DocumentDetailPage integration with ReaderLayout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetUIStore();

    // Default mock for useDocumentBlob (loading state)
    mockUseDocumentBlob.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentBlob>);

    // Default mock for useDocumentContent (loading state)
    mockUseDocumentContent.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentContent>);

    // Default mock for useDocumentHighlights
    mockUseDocumentHighlights.mockReturnValue({
      highlights: [],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useDocumentHighlights>);
  });

  test("shows loading state before ReaderLayout", () => {
    mockUseDocumentDetail.mockReturnValue({
      data: undefined,
      error: null,
      isLoading: true,
      isError: false,
      isSuccess: false,
    } as ReturnType<typeof useDocumentDetail>);

    render(<DocumentDetailPage params={{ documentId: "doc_test-123" }} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText("Loading document...")).toBeInTheDocument();
    // ReaderLayout should not be rendered
    expect(screen.queryByText("Library")).not.toBeInTheDocument();
  });

  test("shows error state before ReaderLayout", () => {
    mockUseDocumentDetail.mockReturnValue({
      data: undefined,
      error: { code: "NOT_FOUND", message: "Not found", httpStatus: 404, details: null, traceId: null },
      isLoading: false,
      isError: true,
      isSuccess: false,
    } as unknown as ReturnType<typeof useDocumentDetail>);

    render(<DocumentDetailPage params={{ documentId: "doc_test-123" }} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText("Document not found")).toBeInTheDocument();
    // ReaderLayout should not be rendered
    expect(screen.queryByText("Library")).not.toBeInTheDocument();
  });

  test("renders ReaderLayout on success", () => {
    mockUseDocumentDetail.mockReturnValue({
      data: mockDocument,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    render(<DocumentDetailPage params={{ documentId: "doc_test-123" }} />, {
      wrapper: createWrapper(),
    });

    // ReaderLayout is rendered
    expect(screen.getByText("Library")).toBeInTheDocument();
    // Inspector is visible
    expect(screen.getByTestId("inspector-content-highlights")).toBeInTheDocument();
  });

  test("renders document metadata in center pane", () => {
    mockUseDocumentDetail.mockReturnValue({
      data: mockDocument,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    render(<DocumentDetailPage params={{ documentId: "doc_test-123" }} />, {
      wrapper: createWrapper(),
    });

    // Document title
    expect(screen.getByText("Test Document")).toBeInTheDocument();
    // Source kind
    expect(screen.getByText("PDF")).toBeInTheDocument();
    // Status (mockDocument uses PENDING status)
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  test("inspector is visible by default on success", () => {
    mockUseDocumentDetail.mockReturnValue({
      data: mockDocument,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    render(<DocumentDetailPage params={{ documentId: "doc_test-123" }} />, {
      wrapper: createWrapper(),
    });

    // All 4 tabs visible
    expect(screen.getByTestId("tab-highlights")).toBeInTheDocument();
    expect(screen.getByTestId("tab-annotations")).toBeInTheDocument();
    expect(screen.getByTestId("tab-chat")).toBeInTheDocument();
    expect(screen.getByTestId("tab-info")).toBeInTheDocument();

    // Highlights tab active by default
    expect(screen.getByTestId("tab-highlights")).toHaveAttribute("aria-selected", "true");
  });

  test("shows processing status message", () => {
    const processingDoc: DocumentListItem = {
      ...mockDocument,
      processing_status: DocumentListItem.processing_status.PROCESSING,
    };

    mockUseDocumentDetail.mockReturnValue({
      data: processingDoc,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    render(<DocumentDetailPage params={{ documentId: "doc_test-123" }} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText(/currently being processed/)).toBeInTheDocument();
  });

  test("shows failed status message", () => {
    const failedDoc: DocumentListItem = {
      ...mockDocument,
      processing_status: DocumentListItem.processing_status.FAILED,
    };

    mockUseDocumentDetail.mockReturnValue({
      data: failedDoc,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    render(<DocumentDetailPage params={{ documentId: "doc_test-123" }} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText(/failed to process/)).toBeInTheDocument();
  });
});

// =============================================================================
// PDF vs HTML Reader Selection Tests
// =============================================================================

describe("DocumentDetailPage reader selection by source_kind", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetUIStore();

    // Default mock for useDocumentHighlights
    mockUseDocumentHighlights.mockReturnValue({
      highlights: [],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useDocumentHighlights>);
  });

  test("renders PdfReader for ready PDF documents", () => {
    // Ready PDF document
    const pdfDoc: DocumentListItem = {
      id: "doc_pdf-123",
      title: "Test PDF",
      source_kind: DocumentListItem.source_kind.PDF,
      processing_status: DocumentListItem.processing_status.READY,
      created_at: "2025-01-15T10:00:00Z",
      updated_at: "2025-01-15T12:00:00Z",
    };

    mockUseDocumentDetail.mockReturnValue({
      data: pdfDoc,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    // PdfReader will be loading blob
    mockUseDocumentBlob.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentBlob>);

    // Content hook should not be used for PDF
    mockUseDocumentContent.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentContent>);

    render(<DocumentDetailPage params={{ documentId: "doc_pdf-123" }} />, {
      wrapper: createWrapper(),
    });

    // PdfReader shows loading state
    expect(screen.getByTestId("pdf-reader-loading")).toBeInTheDocument();
    expect(screen.getByText("Loading PDF...")).toBeInTheDocument();

    // Should NOT show HTML reader or DocumentContent
    expect(screen.queryByTestId("html-reader")).not.toBeInTheDocument();
  });

  test("renders HtmlHighlightReader for ready HTML documents with content", () => {
    // Ready HTML document
    const htmlDoc: DocumentListItem = {
      id: "doc_html-123",
      title: "Test HTML",
      source_kind: DocumentListItem.source_kind.HTML,
      processing_status: DocumentListItem.processing_status.READY,
      created_at: "2025-01-15T10:00:00Z",
      updated_at: "2025-01-15T12:00:00Z",
    };

    mockUseDocumentDetail.mockReturnValue({
      data: htmlDoc,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    // Blob hook not used for HTML
    mockUseDocumentBlob.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentBlob>);

    // Content is loaded for HTML
    mockUseDocumentContent.mockReturnValue({
      data: {
        canonical_text: "Hello, world! This is test content.",
        canonical_hash: "abc123",
        anchored_content_hash: null,
        source_kind: "html",
        text_length: 35,
      },
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentContent>);

    render(<DocumentDetailPage params={{ documentId: "doc_html-123" }} />, {
      wrapper: createWrapper(),
    });

    // HtmlHighlightReader renders
    expect(screen.getByTestId("html-reader")).toBeInTheDocument();
    expect(screen.getByText("Hello, world! This is test content.")).toBeInTheDocument();

    // Should NOT show PDF reader
    expect(screen.queryByTestId("pdf-reader-loading")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pdf-reader")).not.toBeInTheDocument();
  });

  test("renders HtmlHighlightReader for ready EPUB documents with content", () => {
    // Ready EPUB document (should behave same as HTML)
    const epubDoc: DocumentListItem = {
      id: "doc_epub-123",
      title: "Test EPUB",
      source_kind: DocumentListItem.source_kind.EPUB,
      processing_status: DocumentListItem.processing_status.READY,
      created_at: "2025-01-15T10:00:00Z",
      updated_at: "2025-01-15T12:00:00Z",
    };

    mockUseDocumentDetail.mockReturnValue({
      data: epubDoc,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    mockUseDocumentBlob.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentBlob>);

    mockUseDocumentContent.mockReturnValue({
      data: {
        canonical_text: "EPUB document content here.",
        canonical_hash: "def456",
        anchored_content_hash: null,
        source_kind: "epub",
        text_length: 27,
      },
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentContent>);

    render(<DocumentDetailPage params={{ documentId: "doc_epub-123" }} />, {
      wrapper: createWrapper(),
    });

    // HtmlHighlightReader renders for EPUB
    expect(screen.getByTestId("html-reader")).toBeInTheDocument();
    expect(screen.getByText("EPUB document content here.")).toBeInTheDocument();

    // Should NOT show PDF reader
    expect(screen.queryByTestId("pdf-reader-loading")).not.toBeInTheDocument();
  });

  test("renders DocumentContent for not-ready documents regardless of source_kind", () => {
    // Pending PDF document should show DocumentContent, not PdfReader
    const pendingPdf: DocumentListItem = {
      id: "doc_pending-pdf",
      title: "Pending PDF",
      source_kind: DocumentListItem.source_kind.PDF,
      processing_status: DocumentListItem.processing_status.PENDING,
      created_at: "2025-01-15T10:00:00Z",
      updated_at: "2025-01-15T12:00:00Z",
    };

    mockUseDocumentDetail.mockReturnValue({
      data: pendingPdf,
      error: null,
      isLoading: false,
      isError: false,
      isSuccess: true,
    } as ReturnType<typeof useDocumentDetail>);

    mockUseDocumentBlob.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentBlob>);

    mockUseDocumentContent.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDocumentContent>);

    render(<DocumentDetailPage params={{ documentId: "doc_pending-pdf" }} />, {
      wrapper: createWrapper(),
    });

    // Should show document title (from DocumentContent)
    expect(screen.getByText("Pending PDF")).toBeInTheDocument();
    // Should show pending status badge
    expect(screen.getByText("Pending")).toBeInTheDocument();

    // Should NOT show PdfReader
    expect(screen.queryByTestId("pdf-reader-loading")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pdf-reader")).not.toBeInTheDocument();
  });
});

