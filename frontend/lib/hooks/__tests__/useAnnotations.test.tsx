import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, beforeEach, describe, test, expect } from "vitest";
import type { ReactNode } from "react";

import {
  useAnnotations,
  useCreateAnnotation,
  useUpdateAnnotation,
  useDeleteAnnotation,
  highlightAnnotationsKey,
} from "../useAnnotations";
import type { AnnotationsListResult, AnnotationItem } from "@/lib/api/annotations";
import type { ClientError } from "@/lib/api/http";

// Mock the API wrapper layer
vi.mock("@/lib/api/annotations", () => ({
  listAnnotationsForHighlight: vi.fn(),
  createAnnotation: vi.fn(),
  updateAnnotation: vi.fn(),
  deleteAnnotation: vi.fn(),
}));

// Import mocked functions for type-safe access
import {
  listAnnotationsForHighlight,
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
} from "@/lib/api/annotations";

const mockListAnnotationsForHighlight = vi.mocked(listAnnotationsForHighlight);
const mockCreateAnnotation = vi.mocked(createAnnotation);
const mockUpdateAnnotation = vi.mocked(updateAnnotation);
const mockDeleteAnnotation = vi.mocked(deleteAnnotation);

// Test fixtures
const mockAnnotation1: AnnotationItem = {
  id: "ann_11111111-2222-3333-4444-555555555555",
  user_id: "usr_test",
  document_id: "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  highlight_id: "hl_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  content: "First annotation",
  created_at: "2025-01-01T12:00:00Z",
  updated_at: "2025-01-01T12:00:00Z",
};

const mockAnnotation2: AnnotationItem = {
  id: "ann_22222222-3333-4444-5555-666666666666",
  user_id: "usr_test",
  document_id: "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  highlight_id: "hl_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  content: "Second annotation",
  created_at: "2025-01-02T10:30:00Z",
  updated_at: "2025-01-02T10:32:00Z",
};

const mockAnnotationsResult: AnnotationsListResult = {
  items: [mockAnnotation1, mockAnnotation2],
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

describe("useAnnotations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("fetches annotations successfully", async () => {
    mockListAnnotationsForHighlight.mockResolvedValue(mockAnnotationsResult);

    const { result } = renderHook(
      () => useAnnotations("hl_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
      { wrapper: createWrapper() }
    );

    // Initially loading
    expect(result.current.isLoading).toBe(true);

    // Wait for success
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    // Check flattened annotations array
    expect(result.current.annotations).toHaveLength(2);
    expect(result.current.annotations[0].id).toBe(mockAnnotation1.id);
    expect(result.current.annotations[1].content).toBe("Second annotation");
  });

  test("exposes error on fetch failure", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Database connection failed",
      details: null,
      traceId: "req_abc123",
    };

    mockListAnnotationsForHighlight.mockRejectedValue(clientError);

    const { result } = renderHook(
      () => useAnnotations("hl_test"),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(clientError);
    expect(result.current.annotations).toHaveLength(0);
  });

  test("does not fetch when enabled is false", async () => {
    const { result } = renderHook(
      () =>
        useAnnotations("hl_test", {
          enabled: false,
        }),
      { wrapper: createWrapper() }
    );

    // Should not be loading (query is disabled)
    expect(result.current.isLoading).toBe(false);

    // API should not have been called
    expect(mockListAnnotationsForHighlight).not.toHaveBeenCalled();
  });

  test("does not fetch when highlightId is empty", async () => {
    const { result } = renderHook(
      () => useAnnotations(""),
      { wrapper: createWrapper() }
    );

    // Should not be loading (query is disabled due to empty highlightId)
    expect(result.current.isLoading).toBe(false);

    // API should not have been called
    expect(mockListAnnotationsForHighlight).not.toHaveBeenCalled();
  });

  test("uses custom page size", async () => {
    mockListAnnotationsForHighlight.mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    renderHook(
      () => useAnnotations("hl_test", { pageSize: 50 }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(mockListAnnotationsForHighlight).toHaveBeenCalledWith(
        "hl_test",
        undefined,
        50
      );
    });
  });

  test("supports pagination via fetchNextPage", async () => {
    const firstPage: AnnotationsListResult = {
      items: [mockAnnotation1],
      next_cursor: "cursor_2",
      has_more: true,
    };

    const secondPage: AnnotationsListResult = {
      items: [mockAnnotation2],
      next_cursor: null,
      has_more: false,
    };

    mockListAnnotationsForHighlight
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);

    const { result } = renderHook(
      () => useAnnotations("hl_test"),
      { wrapper: createWrapper() }
    );

    // Wait for first page
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.annotations).toHaveLength(1);
    expect(result.current.hasNextPage).toBe(true);

    // Fetch next page
    act(() => {
      result.current.fetchNextPage();
    });

    await waitFor(() => {
      expect(result.current.annotations).toHaveLength(2);
    });

    // Verify second page was fetched with cursor
    expect(mockListAnnotationsForHighlight).toHaveBeenLastCalledWith(
      "hl_test",
      "cursor_2",
      100
    );

    // Verify no more pages
    expect(result.current.hasNextPage).toBe(false);
  });
});

describe("useCreateAnnotation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("creates annotation and invalidates query", async () => {
    const newAnnotation: AnnotationItem = {
      ...mockAnnotation1,
      id: "ann_new",
      content: "New annotation content",
    };
    mockCreateAnnotation.mockResolvedValue(newAnnotation);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
    });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () => useCreateAnnotation("hl_test"),
      { wrapper }
    );

    expect(result.current.isPending).toBe(false);

    // Create annotation
    let createdAnnotation: AnnotationItem | undefined;
    await act(async () => {
      createdAnnotation = await result.current.createAnnotation("New annotation content");
    });

    expect(mockCreateAnnotation).toHaveBeenCalledWith({
      highlightId: "hl_test",
      content: "New annotation content",
    });

    expect(createdAnnotation).toEqual(newAnnotation);

    // Check that query was invalidated
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: highlightAnnotationsKey("hl_test"),
    });
  });

  test("exposes error on creation failure", async () => {
    const clientError: ClientError = {
      httpStatus: 400,
      code: "VALIDATION_ERROR",
      message: "Content cannot be empty",
      details: null,
      traceId: null,
    };

    mockCreateAnnotation.mockRejectedValue(clientError);

    const { result } = renderHook(
      () => useCreateAnnotation("hl_test"),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      try {
        await result.current.createAnnotation("test");
      } catch {
        // Expected to throw
      }
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toEqual(clientError);
  });
});

describe("useUpdateAnnotation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("updates annotation and invalidates query", async () => {
    const updatedAnnotation: AnnotationItem = {
      ...mockAnnotation1,
      content: "Updated content",
      updated_at: "2025-01-03T10:00:00Z",
    };
    mockUpdateAnnotation.mockResolvedValue(updatedAnnotation);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
    });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () => useUpdateAnnotation("hl_test"),
      { wrapper }
    );

    // Update annotation
    let updated: AnnotationItem | undefined;
    await act(async () => {
      updated = await result.current.updateAnnotation({
        annotationId: mockAnnotation1.id,
        content: "Updated content",
      });
    });

    expect(mockUpdateAnnotation).toHaveBeenCalledWith({
      annotationId: mockAnnotation1.id,
      content: "Updated content",
    });

    expect(updated).toEqual(updatedAnnotation);

    // Check that query was invalidated
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: highlightAnnotationsKey("hl_test"),
    });
  });

  test("exposes error on update failure", async () => {
    const clientError: ClientError = {
      httpStatus: 404,
      code: "NOT_FOUND",
      message: "Annotation not found",
      details: null,
      traceId: null,
    };

    mockUpdateAnnotation.mockRejectedValue(clientError);

    const { result } = renderHook(
      () => useUpdateAnnotation("hl_test"),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      try {
        await result.current.updateAnnotation({
          annotationId: "ann_notfound",
          content: "test",
        });
      } catch {
        // Expected to throw
      }
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toEqual(clientError);
  });
});

describe("useDeleteAnnotation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("deletes annotation and invalidates query", async () => {
    mockDeleteAnnotation.mockResolvedValue(undefined);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
    });

    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () => useDeleteAnnotation("hl_test"),
      { wrapper }
    );

    // Delete annotation
    await act(async () => {
      await result.current.deleteAnnotation(mockAnnotation1.id);
    });

    expect(mockDeleteAnnotation).toHaveBeenCalledWith(mockAnnotation1.id);

    // Check that query was invalidated
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: highlightAnnotationsKey("hl_test"),
    });
  });

  test("exposes error on deletion failure", async () => {
    const clientError: ClientError = {
      httpStatus: 403,
      code: "PERMISSION_DENIED",
      message: "Cannot delete this annotation",
      details: null,
      traceId: null,
    };

    mockDeleteAnnotation.mockRejectedValue(clientError);

    const { result } = renderHook(
      () => useDeleteAnnotation("hl_test"),
      { wrapper: createWrapper() }
    );

    await act(async () => {
      try {
        await result.current.deleteAnnotation("ann_test");
      } catch {
        // Expected to throw
      }
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toEqual(clientError);
  });
});

describe("highlightAnnotationsKey", () => {
  test("generates correct query key", () => {
    const key = highlightAnnotationsKey("hl_test123");
    expect(key).toEqual(["annotations", { highlightId: "hl_test123" }]);
  });
});

