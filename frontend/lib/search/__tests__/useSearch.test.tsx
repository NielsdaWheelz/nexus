import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, beforeEach, describe, test, expect } from "vitest";
import type { ReactNode } from "react";

import { useSearch, type UseSearchOptions } from "../useSearch";
import type { SearchChunksResult } from "@/lib/api/search";
import type { ClientError } from "@/lib/api/http";

// Mock the API wrapper layer
vi.mock("@/lib/api/search", () => ({
  searchChunks: vi.fn(),
}));

// Import mocked function for type-safe access
import { searchChunks } from "@/lib/api/search";
const mockSearchChunks = vi.mocked(searchChunks);

// Test fixtures
const mockChunkHit = {
  chunk_id: "chunk_11111111-2222-3333-4444-555555555555",
  document_id: "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  score: 0.89,
  text: "The absurd is the essential concept and the only truth. One must imagine Sisyphus happy.",
  text_start: 10240,
  text_end: 10450,
};

const mockSearchResult: SearchChunksResult = {
  items: [
    mockChunkHit,
    {
      chunk_id: "chunk_22222222-3333-4444-5555-666666666666",
      document_id: "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      score: 0.75,
      text: "Revolt is the refusal to accept the limits of the human condition.",
      text_start: 8900,
      text_end: 9120,
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

describe("useSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("does not fetch when query is empty", async () => {
    const { result } = renderHook(() => useSearch({ query: "" }), {
      wrapper: createWrapper(),
    });

    // Should not be loading (query is disabled)
    expect(result.current.isLoading).toBe(false);
    expect(result.current.results).toEqual([]);

    // API should not have been called
    expect(mockSearchChunks).not.toHaveBeenCalled();
  });

  test("does not fetch when query is whitespace only", async () => {
    const { result } = renderHook(() => useSearch({ query: "   " }), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(false);
    expect(mockSearchChunks).not.toHaveBeenCalled();
  });

  test("fetches when query is non-empty", async () => {
    mockSearchChunks.mockResolvedValue(mockSearchResult);

    const { result } = renderHook(() => useSearch({ query: "existentialism" }), {
      wrapper: createWrapper(),
    });

    // Initially loading
    expect(result.current.isLoading).toBe(true);

    // Wait for success
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Check API was called with correct params
    expect(mockSearchChunks).toHaveBeenCalledWith({
      query: "existentialism",
      limit: 20,
      documentIds: undefined,
    });

    // Check results are transformed correctly
    expect(result.current.results).toHaveLength(2);
    expect(result.current.results[0]).toEqual({
      id: "chunk_11111111-2222-3333-4444-555555555555",
      kind: "chunk",
      documentId: "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      score: 0.89,
      text: "The absurd is the essential concept and the only truth. One must imagine Sisyphus happy.",
      textStart: 10240,
      textEnd: 10450,
    });
  });

  test("trims query before searching", async () => {
    mockSearchChunks.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    renderHook(() => useSearch({ query: "  revolt  " }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(mockSearchChunks).toHaveBeenCalledWith({
        query: "revolt",
        limit: 20,
        documentIds: undefined,
      });
    });
  });

  test("passes custom limit to API", async () => {
    mockSearchChunks.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    renderHook(() => useSearch({ query: "camus", limit: 10 }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(mockSearchChunks).toHaveBeenCalledWith({
        query: "camus",
        limit: 10,
        documentIds: undefined,
      });
    });
  });

  test("passes documentIds filter to API", async () => {
    mockSearchChunks.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    const documentIds = ["doc_123", "doc_456"];

    renderHook(() => useSearch({ query: "absurd", documentIds }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(mockSearchChunks).toHaveBeenCalledWith({
        query: "absurd",
        limit: 20,
        documentIds,
      });
    });
  });

  test("exposes error on fetch failure", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "ERR_RETRIEVAL_FAILED",
      message: "Vector search failed",
      details: { reason: "connection timeout" },
      traceId: "req_abc123",
    };

    mockSearchChunks.mockRejectedValue(clientError);

    const { result } = renderHook(() => useSearch({ query: "test" }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(clientError);
    expect(result.current.results).toEqual([]);
  });

  test("respects enabled option", async () => {
    mockSearchChunks.mockResolvedValue(mockSearchResult);

    const { result, rerender } = renderHook(
      (props: UseSearchOptions) => useSearch(props),
      {
        wrapper: createWrapper(),
        initialProps: { query: "test", enabled: false },
      }
    );

    // Should not fetch when disabled
    expect(result.current.isLoading).toBe(false);
    expect(mockSearchChunks).not.toHaveBeenCalled();

    // Enable and verify it fetches
    rerender({ query: "test", enabled: true });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(mockSearchChunks).toHaveBeenCalled();
  });

  test("returns pagination metadata", async () => {
    const resultWithPagination: SearchChunksResult = {
      items: [mockChunkHit],
      next_cursor: "cursor_xyz",
      has_more: true,
    };

    mockSearchChunks.mockResolvedValue(resultWithPagination);

    const { result } = renderHook(() => useSearch({ query: "test" }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.hasMore).toBe(true);
    expect(result.current.nextCursor).toBe("cursor_xyz");
  });

  test("returns empty results and no pagination when search returns nothing", async () => {
    mockSearchChunks.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    const { result } = renderHook(() => useSearch({ query: "nonexistent" }), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.results).toEqual([]);
    expect(result.current.hasMore).toBe(false);
    expect(result.current.nextCursor).toBe(null);
  });
});

