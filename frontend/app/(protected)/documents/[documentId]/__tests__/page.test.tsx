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

import { useDocumentDetail } from "@/lib/hooks/useDocuments";
const mockUseDocumentDetail = vi.mocked(useDocumentDetail);

// Mock next/link since we're testing outside Next.js context
vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

// Test fixtures
const mockDocument: DocumentListItem = {
  id: "doc_test-123",
  title: "Test Document",
  source_kind: DocumentListItem.source_kind.PDF,
  processing_status: DocumentListItem.processing_status.READY,
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
    // Status
    expect(screen.getByText("Ready")).toBeInTheDocument();
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

