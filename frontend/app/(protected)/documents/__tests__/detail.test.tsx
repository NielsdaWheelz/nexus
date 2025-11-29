import { render, screen, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DocumentDetailPage from "../[documentId]/page";
import { DocumentListItem } from "@/lib/generated-api";
import type { ClientError } from "@/lib/api/http";

// Mock the API wrapper layer (not the generated service)
vi.mock("@/lib/api/documents", () => ({
  fetchDocument: vi.fn(),
  isClientError: (error: unknown): error is ClientError =>
    typeof error === "object" &&
    error !== null &&
    "httpStatus" in error &&
    "code" in error &&
    "message" in error,
  isNotFoundError: (error: ClientError) =>
    error.code === "NOT_FOUND" || error.httpStatus === 404,
}));

// Mock next/link
vi.mock("next/link", () => {
  return {
    default: ({ children }: { children: React.ReactNode }) => children,
  };
});

// Import the mocked function for type-safe access
import { fetchDocument } from "@/lib/api/documents";
const mockFetchDocument = vi.mocked(fetchDocument);

const mockDocument: DocumentListItem = {
  id: "doc_11111111-2222-3333-4444-555555555555",
  title: "The Myth of Sisyphus",
  source_kind: DocumentListItem.source_kind.PDF,
  processing_status: DocumentListItem.processing_status.READY,
  created_at: "2025-01-01T12:00:00Z",
  updated_at: "2025-01-01T13:00:00Z",
};

/**
 * Helper to render component with QueryClientProvider.
 * Creates a fresh QueryClient for each test to avoid cache interference.
 */
function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // Don't retry in tests
        gcTime: 0, // Disable garbage collection caching
      },
    },
  });

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("DocumentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders loading state initially", () => {
    mockFetchDocument.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockDocument), 100))
    );

    renderWithQueryClient(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    expect(screen.getByText("Loading document...")).toBeInTheDocument();
  });

  test("renders document details on successful fetch", async () => {
    mockFetchDocument.mockResolvedValue(mockDocument);

    renderWithQueryClient(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("The Myth of Sisyphus")).toBeInTheDocument();
      expect(screen.getByText("PDF")).toBeInTheDocument();
      expect(screen.getByText("Ready")).toBeInTheDocument();
    });
  });

  test("renders back to documents link", async () => {
    mockFetchDocument.mockResolvedValue(mockDocument);

    renderWithQueryClient(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("← Back to documents")).toBeInTheDocument();
    });
  });

  test("renders not found error state with correct message", async () => {
    const notFoundError: ClientError = {
      httpStatus: 404,
      code: "NOT_FOUND",
      message: "Document not found",
      details: null,
      traceId: "req_xyz",
    };

    mockFetchDocument.mockRejectedValue(notFoundError);

    renderWithQueryClient(<DocumentDetailPage params={{ documentId: "doc_nonexistent" }} />);

    await waitFor(() => {
      // Should show the not found heading
      expect(screen.getByText("Document not found")).toBeInTheDocument();
      // Should show the explanatory message
      expect(
        screen.getByText("The document you're looking for doesn't exist or you don't have access to it.")
      ).toBeInTheDocument();
    });
  });

  test("renders generic error state on API failure", async () => {
    const serverError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Database connection failed",
      details: null,
      traceId: "req_abc",
    };

    mockFetchDocument.mockRejectedValue(serverError);

    renderWithQueryClient(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("Failed to load document")).toBeInTheDocument();
      expect(screen.getByText("Database connection failed")).toBeInTheDocument();
      expect(screen.getByText("Error code: INTERNAL_ERROR")).toBeInTheDocument();
    });
  });

  test("displays processing state message", async () => {
    const processingDoc: DocumentListItem = {
      ...mockDocument,
      processing_status: DocumentListItem.processing_status.PROCESSING,
    };

    mockFetchDocument.mockResolvedValue(processingDoc);

    renderWithQueryClient(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "This document is currently being processed. Please check back in a moment."
        )
      ).toBeInTheDocument();
    });
  });

  test("displays failed state message", async () => {
    const failedDoc: DocumentListItem = {
      ...mockDocument,
      processing_status: DocumentListItem.processing_status.FAILED,
    };

    mockFetchDocument.mockResolvedValue(failedDoc);

    renderWithQueryClient(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(
        screen.getByText("This document failed to process. Please try uploading it again.")
      ).toBeInTheDocument();
    });
  });

  test("displays document ID in monospace", async () => {
    mockFetchDocument.mockResolvedValue(mockDocument);

    renderWithQueryClient(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("doc_11111111-2222-3333-4444-555555555555")).toBeInTheDocument();
    });
  });

  test("calls fetchDocument with correct documentId", async () => {
    mockFetchDocument.mockResolvedValue(mockDocument);

    renderWithQueryClient(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(mockFetchDocument).toHaveBeenCalledWith("doc_11111111-2222-3333-4444-555555555555");
    });
  });
});
