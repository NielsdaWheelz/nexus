import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, beforeEach, describe, test, expect } from "vitest";
import type { ReactNode } from "react";

import { useDocumentHighlights } from "../useHighlights";
import type { HighlightsListResult } from "@/lib/api/highlights";
import type { ClientError } from "@/lib/api/http";
import type { HighlightItem } from "@/lib/generated-api";

// Mock the API wrapper layer
vi.mock("@/lib/api/highlights", () => ({
  fetchDocumentHighlights: vi.fn(),
}));

// Import mocked functions for type-safe access
import { fetchDocumentHighlights } from "@/lib/api/highlights";
const mockFetchDocumentHighlights = vi.mocked(fetchDocumentHighlights);

// Test fixtures
const mockHighlight1: HighlightItem = {
  id: "hl_11111111-2222-3333-4444-555555555555",
  document_id: "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  anchor_type: "text",
  text_start: 100,
  text_end: 150,
  quote: "test quote 1",
  color: "yellow",
  pdf_page_number: null,
  pdf_char_offset: null,
  created_at: "2025-01-01T12:00:00Z",
  updated_at: "2025-01-01T12:00:00Z",
};

const mockHighlight2: HighlightItem = {
  id: "hl_22222222-3333-4444-5555-666666666666",
  document_id: "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  anchor_type: "text",
  text_start: 200,
  text_end: 250,
  quote: "test quote 2",
  color: "blue",
  pdf_page_number: null,
  pdf_char_offset: null,
  created_at: "2025-01-02T10:30:00Z",
  updated_at: "2025-01-02T10:32:00Z",
};

const mockHighlightsResult: HighlightsListResult = {
  items: [mockHighlight1, mockHighlight2],
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

describe("useDocumentHighlights", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("fetches highlights successfully", async () => {
    mockFetchDocumentHighlights.mockResolvedValue(mockHighlightsResult);

    const { result } = renderHook(
      () => useDocumentHighlights("doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
      { wrapper: createWrapper() }
    );

    // Initially loading
    expect(result.current.isLoading).toBe(true);

    // Wait for success
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Check flattened highlights array
    expect(result.current.highlights).toHaveLength(2);
    expect(result.current.highlights[0].id).toBe(
      "hl_11111111-2222-3333-4444-555555555555"
    );
    expect(result.current.highlights[1].text_start).toBe(200);
  });

  test("exposes error on fetch failure", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Database connection failed",
      details: null,
      traceId: "req_abc123",
    };

    mockFetchDocumentHighlights.mockRejectedValue(clientError);

    const { result } = renderHook(
      () => useDocumentHighlights("doc_test"),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(clientError);
    expect(result.current.highlights).toHaveLength(0);
  });

  test("does not fetch when enabled is false", async () => {
    const { result } = renderHook(
      () =>
        useDocumentHighlights("doc_test", {
          enabled: false,
        }),
      { wrapper: createWrapper() }
    );

    // Should not be loading (query is disabled)
    expect(result.current.isLoading).toBe(false);

    // API should not have been called
    expect(mockFetchDocumentHighlights).not.toHaveBeenCalled();
  });

  test("does not fetch when documentId is empty", async () => {
    const { result } = renderHook(
      () => useDocumentHighlights(""),
      { wrapper: createWrapper() }
    );

    // Should not be loading (query is disabled due to empty docId)
    expect(result.current.isLoading).toBe(false);

    // API should not have been called
    expect(mockFetchDocumentHighlights).not.toHaveBeenCalled();
  });

  test("uses custom page size", async () => {
    mockFetchDocumentHighlights.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    renderHook(
      () => useDocumentHighlights("doc_test", { pageSize: 50 }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(mockFetchDocumentHighlights).toHaveBeenCalledWith({
        documentId: "doc_test",
        cursor: undefined,
        limit: 50,
      });
    });
  });

  test("supports pagination via fetchNextPage", async () => {
    const firstPage: HighlightsListResult = {
      items: [mockHighlight1],
      next_cursor: "cursor_2",
      has_more: true,
    };

    const secondPage: HighlightsListResult = {
      items: [mockHighlight2],
      next_cursor: null,
      has_more: false,
    };

    mockFetchDocumentHighlights
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);

    const { result } = renderHook(
      () => useDocumentHighlights("doc_test"),
      { wrapper: createWrapper() }
    );

    // Wait for first page
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.highlights).toHaveLength(1);
    expect(result.current.hasNextPage).toBe(true);

    // Fetch next page
    result.current.fetchNextPage();

    await waitFor(() => {
      expect(result.current.highlights).toHaveLength(2);
    });

    // Verify second page was fetched with cursor
    expect(mockFetchDocumentHighlights).toHaveBeenLastCalledWith({
      documentId: "doc_test",
      cursor: "cursor_2",
      limit: 100,
    });

    // Verify no more pages
    expect(result.current.hasNextPage).toBe(false);
  });

  test("flattens multiple pages into single array", async () => {
    const firstPage: HighlightsListResult = {
      items: [mockHighlight1],
      next_cursor: "cursor_2",
      has_more: true,
    };

    const secondPage: HighlightsListResult = {
      items: [mockHighlight2],
      next_cursor: null,
      has_more: false,
    };

    mockFetchDocumentHighlights
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);

    const { result } = renderHook(
      () => useDocumentHighlights("doc_test"),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Fetch next page
    result.current.fetchNextPage();

    await waitFor(() => {
      expect(result.current.highlights).toHaveLength(2);
    });

    // Verify both highlights are in the flattened array
    expect(result.current.highlights[0].id).toBe(mockHighlight1.id);
    expect(result.current.highlights[1].id).toBe(mockHighlight2.id);
  });
});

