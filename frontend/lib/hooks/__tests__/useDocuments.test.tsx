import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, beforeEach, describe, test, expect } from "vitest";
import type { ReactNode } from "react";

import { useDocumentsList, useDocumentDetail } from "../useDocuments";
import type { DocumentsListResult } from "@/lib/api/documents";
import type { ClientError } from "@/lib/api/http";
import { DocumentListItem } from "@/lib/generated-api";

// Mock the API wrapper layer
vi.mock("@/lib/api/documents", () => ({
  fetchDocumentsList: vi.fn(),
  fetchDocument: vi.fn(),
}));

// Import mocked functions for type-safe access
import { fetchDocumentsList, fetchDocument } from "@/lib/api/documents";
const mockFetchDocumentsList = vi.mocked(fetchDocumentsList);
const mockFetchDocument = vi.mocked(fetchDocument);

// Test fixtures
const mockDocument: DocumentListItem = {
  id: "doc_11111111-2222-3333-4444-555555555555",
  title: "The Myth of Sisyphus",
  source_kind: DocumentListItem.source_kind.PDF,
  processing_status: DocumentListItem.processing_status.READY,
  created_at: "2025-01-01T12:00:00Z",
  updated_at: "2025-01-01T13:00:00Z",
};

const mockDocumentsResult: DocumentsListResult = {
  items: [
    mockDocument,
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
 * Create a wrapper component with a fresh QueryClient for each test.
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

describe("useDocumentsList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("fetches documents successfully", async () => {
    mockFetchDocumentsList.mockResolvedValue(mockDocumentsResult);

    const { result } = renderHook(() => useDocumentsList(), {
      wrapper: createWrapper(),
    });

    // Initially loading
    expect(result.current.isLoading).toBe(true);

    // Wait for success
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Check data
    expect(result.current.data?.pages).toHaveLength(1);
    expect(result.current.data?.pages[0].items).toHaveLength(2);
    expect(result.current.data?.pages[0].items[0].title).toBe("The Myth of Sisyphus");
  });

  test("exposes error on fetch failure", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Database connection failed",
      details: null,
      traceId: "req_abc123",
    };

    mockFetchDocumentsList.mockRejectedValue(clientError);

    const { result } = renderHook(() => useDocumentsList(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(clientError);
  });

  test("passes status filter to API", async () => {
    mockFetchDocumentsList.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    renderHook(() => useDocumentsList({ status: "ready" }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(mockFetchDocumentsList).toHaveBeenCalledWith({
        cursor: undefined,
        limit: 20,
        status: "ready",
      });
    });
  });

  test("uses custom page size", async () => {
    mockFetchDocumentsList.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    renderHook(() => useDocumentsList({ pageSize: 50 }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(mockFetchDocumentsList).toHaveBeenCalledWith({
        cursor: undefined,
        limit: 50,
        status: undefined,
      });
    });
  });

  test("supports pagination via fetchNextPage", async () => {
    const firstPage: DocumentsListResult = {
      items: [mockDocument],
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

    const { result } = renderHook(() => useDocumentsList(), {
      wrapper: createWrapper(),
    });

    // Wait for first page
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.hasNextPage).toBe(true);

    // Fetch next page
    result.current.fetchNextPage();

    await waitFor(() => {
      expect(result.current.data?.pages).toHaveLength(2);
    });

    // Verify second page was fetched with cursor
    expect(mockFetchDocumentsList).toHaveBeenLastCalledWith({
      cursor: "cursor_2",
      limit: 20,
      status: undefined,
    });

    // Verify no more pages
    expect(result.current.hasNextPage).toBe(false);
  });
});

describe("useDocumentDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("fetches document successfully", async () => {
    mockFetchDocument.mockResolvedValue(mockDocument);

    const { result } = renderHook(
      () => useDocumentDetail("doc_11111111-2222-3333-4444-555555555555"),
      { wrapper: createWrapper() }
    );

    // Initially loading
    expect(result.current.isLoading).toBe(true);

    // Wait for success
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Check data
    expect(result.current.data?.title).toBe("The Myth of Sisyphus");
    expect(result.current.data?.id).toBe("doc_11111111-2222-3333-4444-555555555555");
  });

  test("exposes error on fetch failure", async () => {
    const clientError: ClientError = {
      httpStatus: 404,
      code: "NOT_FOUND",
      message: "Document not found",
      details: null,
      traceId: "req_xyz",
    };

    mockFetchDocument.mockRejectedValue(clientError);

    const { result } = renderHook(
      () => useDocumentDetail("doc_nonexistent"),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(clientError);
  });

  test("does not fetch when documentId is null", async () => {
    const { result } = renderHook(() => useDocumentDetail(null), {
      wrapper: createWrapper(),
    });

    // Should not be loading (query is disabled)
    expect(result.current.isLoading).toBe(false);
    expect(result.current.fetchStatus).toBe("idle");

    // API should not have been called
    expect(mockFetchDocument).not.toHaveBeenCalled();
  });

  test("does not fetch when documentId is undefined", async () => {
    const { result } = renderHook(() => useDocumentDetail(undefined), {
      wrapper: createWrapper(),
    });

    // Should not be loading (query is disabled)
    expect(result.current.isLoading).toBe(false);
    expect(result.current.fetchStatus).toBe("idle");

    // API should not have been called
    expect(mockFetchDocument).not.toHaveBeenCalled();
  });

  test("calls fetchDocument with correct documentId", async () => {
    mockFetchDocument.mockResolvedValue(mockDocument);

    renderHook(
      () => useDocumentDetail("doc_11111111-2222-3333-4444-555555555555"),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(mockFetchDocument).toHaveBeenCalledWith(
        "doc_11111111-2222-3333-4444-555555555555"
      );
    });
  });
});

