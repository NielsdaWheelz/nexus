import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DocumentsPage from "../page";
import type { DocumentsListResult } from "@/lib/api/documents";
import type { ClientError } from "@/lib/api/http";
import { DocumentListItem } from "@/lib/generated-api";

// Mock the API wrapper layer (not the generated service)
vi.mock("@/lib/api/documents", () => ({
  fetchDocumentsList: vi.fn(),
  isClientError: (error: unknown): error is ClientError =>
    typeof error === "object" &&
    error !== null &&
    "httpStatus" in error &&
    "code" in error &&
    "message" in error,
  isNotFoundError: (error: ClientError) => error.code === "NOT_FOUND",
}));

// Mock next/link
vi.mock("next/link", () => {
  return {
    default: ({ children }: { children: React.ReactNode }) => children,
  };
});

// Mock the window.location.href
beforeEach(() => {
  Object.defineProperty(window, "location", {
    value: { href: "" },
    writable: true,
  });
});

// Import the mocked function for type-safe access
import { fetchDocumentsList } from "@/lib/api/documents";
const mockFetchDocumentsList = vi.mocked(fetchDocumentsList);

const mockDocumentsResult: DocumentsListResult = {
  items: [
    {
      id: "doc_11111111-2222-3333-4444-555555555555",
      title: "The Myth of Sisyphus",
      source_kind: DocumentListItem.source_kind.PDF,
      processing_status: DocumentListItem.processing_status.READY,
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    },
    {
      id: "doc_22222222-3333-4444-5555-666666666666",
      title: "Crime and Punishment",
      source_kind: DocumentListItem.source_kind.EPUB,
      processing_status: DocumentListItem.processing_status.READY,
      created_at: "2025-01-02T10:30:00Z",
      updated_at: "2025-01-02T10:32:00Z",
    },
  ],
  next_cursor: null,
  has_more: false,
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

describe("DocumentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders loading state initially", async () => {
    mockFetchDocumentsList.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockDocumentsResult), 100))
    );

    renderWithQueryClient(<DocumentsPage />);

    expect(screen.getByText("Loading documents...")).toBeInTheDocument();
  });

  test("renders documents list on successful fetch", async () => {
    mockFetchDocumentsList.mockResolvedValue(mockDocumentsResult);

    renderWithQueryClient(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Documents")).toBeInTheDocument();
      expect(screen.getByText("The Myth of Sisyphus")).toBeInTheDocument();
      expect(screen.getByText("Crime and Punishment")).toBeInTheDocument();
    });
  });

  test("displays document metadata correctly", async () => {
    mockFetchDocumentsList.mockResolvedValue(mockDocumentsResult);

    renderWithQueryClient(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("PDF")).toBeInTheDocument();
      expect(screen.getByText("EPUB")).toBeInTheDocument();
      expect(screen.getAllByText("Ready")).toHaveLength(2);
    });
  });

  test("renders empty state when no documents", async () => {
    mockFetchDocumentsList.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    renderWithQueryClient(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("No documents yet")).toBeInTheDocument();
    });
  });

  test("renders error state with ClientError on API failure", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Database connection failed",
      details: null,
      traceId: "req_abc123",
    };

    mockFetchDocumentsList.mockRejectedValue(clientError);

    renderWithQueryClient(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load documents")).toBeInTheDocument();
      expect(screen.getByText("Database connection failed")).toBeInTheDocument();
      expect(screen.getByText("Retry")).toBeInTheDocument();
    });
  });

  test("displays error code in error state", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Something went wrong",
      details: null,
      traceId: null,
    };

    mockFetchDocumentsList.mockRejectedValue(clientError);

    renderWithQueryClient(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Error code: INTERNAL_ERROR")).toBeInTheDocument();
    });
  });

  test("retry button refetches documents", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "API error",
      details: null,
      traceId: null,
    };

    mockFetchDocumentsList
      .mockRejectedValueOnce(clientError)
      .mockResolvedValueOnce(mockDocumentsResult);

    renderWithQueryClient(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load documents")).toBeInTheDocument();
    });

    const retryButton = screen.getByText("Retry");
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText("The Myth of Sisyphus")).toBeInTheDocument();
    });
  });

  test("renders pagination button when has_more is true", async () => {
    mockFetchDocumentsList.mockResolvedValue({
      items: mockDocumentsResult.items,
      next_cursor: "next_page_cursor",
      has_more: true,
    });

    renderWithQueryClient(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Load More")).toBeInTheDocument();
    });
  });

  test("loads more documents when Load More is clicked", async () => {
    const firstPage: DocumentsListResult = {
      items: [mockDocumentsResult.items[0]],
      next_cursor: "cursor_2",
      has_more: true,
    };

    const secondPage: DocumentsListResult = {
      items: [mockDocumentsResult.items[1]],
      next_cursor: null,
      has_more: false,
    };

    mockFetchDocumentsList
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);

    renderWithQueryClient(<DocumentsPage />);

    // Wait for first page
    await waitFor(() => {
      expect(screen.getByText("The Myth of Sisyphus")).toBeInTheDocument();
    });

    // Click load more
    const loadMoreButton = screen.getByText("Load More");
    fireEvent.click(loadMoreButton);

    // Wait for second page
    await waitFor(() => {
      expect(screen.getByText("Crime and Punishment")).toBeInTheDocument();
    });
  });
});
