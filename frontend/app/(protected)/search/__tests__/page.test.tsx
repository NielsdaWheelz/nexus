import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import type { SearchResult } from "@/lib/search";

// Hoist mocks to avoid initialization order issues
const { mockPush, mockGet, mockSetActiveHighlightId, mockUseSearch } = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockGet: vi.fn(),
  mockSetActiveHighlightId: vi.fn(),
  mockUseSearch: vi.fn(),
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    back: vi.fn(),
  }),
  useSearchParams: () => ({
    get: mockGet,
  }),
}));

// Mock the UI store
vi.mock("@/lib/state/ui", () => ({
  useUIStore: (selector: (state: { setActiveHighlightId: () => void }) => unknown) =>
    selector({ setActiveHighlightId: mockSetActiveHighlightId }),
}));

// Mock the useSearch hook
vi.mock("@/lib/search", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/search")>();
  return {
    ...actual,
    useSearch: mockUseSearch,
  };
});

// Import after mocks are set up
import SearchPage from "../page";

// Test fixtures
const mockResults: SearchResult[] = [
  {
    id: "chunk_11111111-2222-3333-4444-555555555555",
    kind: "chunk",
    documentId: "doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    score: 0.89,
    text: "The absurd is the essential concept and the only truth. One must imagine Sisyphus happy.",
    textStart: 10240,
    textEnd: 10450,
  },
  {
    id: "chunk_22222222-3333-4444-5555-666666666666",
    kind: "chunk",
    documentId: "doc_bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
    score: 0.75,
    text: "Revolt is the refusal to accept the limits of the human condition.",
    textStart: 8900,
    textEnd: 9120,
  },
];

/**
 * Create a wrapper component with QueryClient.
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

function renderSearchPage() {
  return render(<SearchPage />, { wrapper: createWrapper() });
}

describe("SearchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockReturnValue(null); // No initial query param
    mockUseSearch.mockReturnValue({
      results: [],
      isLoading: false,
      isError: false,
      error: null,
      isSuccess: false,
      hasMore: false,
      nextCursor: null,
      refetch: vi.fn(),
    });
  });

  describe("initial render", () => {
    test("renders search input and title", () => {
      renderSearchPage();

      expect(screen.getByRole("heading", { name: /search/i })).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/search your documents/i)).toBeInTheDocument();
    });

    test("shows initial state message when no search has been performed", () => {
      renderSearchPage();

      expect(screen.getByText(/search your documents/i)).toBeInTheDocument();
      expect(screen.getByText(/enter a query to find relevant content/i)).toBeInTheDocument();
    });

    test("initializes input from URL query param", () => {
      mockGet.mockReturnValue("existentialism");

      renderSearchPage();

      const input = screen.getByPlaceholderText(/search your documents/i) as HTMLInputElement;
      expect(input.value).toBe("existentialism");
    });
  });

  describe("search interaction", () => {
    test("typing triggers search after debounce", async () => {
      renderSearchPage();

      const input = screen.getByPlaceholderText(/search your documents/i);
      fireEvent.change(input, { target: { value: "camus" } });

      // useSearch should be called with the query after debounce
      await waitFor(() => {
        expect(mockUseSearch).toHaveBeenCalledWith(
          expect.objectContaining({ query: "camus" })
        );
      });
    });

    test("shows clear button when input has value", async () => {
      renderSearchPage();

      const input = screen.getByPlaceholderText(/search your documents/i);
      fireEvent.change(input, { target: { value: "test" } });

      // Clear button should be visible (X icon)
      const clearButton = screen.getByRole("button");
      expect(clearButton).toBeInTheDocument();
    });

    test("clears input when clear button is clicked", async () => {
      renderSearchPage();

      const input = screen.getByPlaceholderText(/search your documents/i) as HTMLInputElement;
      fireEvent.change(input, { target: { value: "test" } });

      expect(input.value).toBe("test");

      // Click clear button
      const clearButton = screen.getByRole("button");
      fireEvent.click(clearButton);

      expect(input.value).toBe("");
    });
  });

  describe("loading state", () => {
    test("shows loading spinner while searching", () => {
      mockUseSearch.mockReturnValue({
        results: [],
        isLoading: true,
        isError: false,
        error: null,
        isSuccess: false,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      // Simulate having searched
      mockGet.mockReturnValue("test");
      renderSearchPage();

      expect(screen.getByText(/searching/i)).toBeInTheDocument();
    });
  });

  describe("error state", () => {
    test("shows error message on search failure", () => {
      mockUseSearch.mockReturnValue({
        results: [],
        isLoading: false,
        isError: true,
        error: {
          httpStatus: 500,
          code: "ERR_RETRIEVAL_FAILED",
          message: "Vector search failed",
          details: null,
          traceId: "req_123",
        },
        isSuccess: false,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("test");
      renderSearchPage();

      // Check for the error title (h3 element)
      expect(screen.getByRole("heading", { level: 3, name: /search failed/i })).toBeInTheDocument();
      expect(screen.getByText(/vector search failed/i)).toBeInTheDocument();
    });
  });

  describe("results display", () => {
    test("shows results when search returns data", async () => {
      mockUseSearch.mockReturnValue({
        results: mockResults,
        isLoading: false,
        isError: false,
        error: null,
        isSuccess: true,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("test");
      renderSearchPage();

      // Should show result count
      expect(screen.getByText(/2 results found/i)).toBeInTheDocument();

      // Should show result snippets
      expect(screen.getByText(/the absurd is the essential concept/i)).toBeInTheDocument();
      expect(screen.getByText(/revolt is the refusal/i)).toBeInTheDocument();
    });

    test("shows empty state when search returns no results", () => {
      mockUseSearch.mockReturnValue({
        results: [],
        isLoading: false,
        isError: false,
        error: null,
        isSuccess: true,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("nonexistent");
      renderSearchPage();

      expect(screen.getByText(/no results found/i)).toBeInTheDocument();
    });
  });

  describe("result navigation", () => {
    test("navigates to document when result is clicked", async () => {
      mockUseSearch.mockReturnValue({
        results: mockResults,
        isLoading: false,
        isError: false,
        error: null,
        isSuccess: true,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("test");
      renderSearchPage();

      // Find and click the first result
      const firstResult = screen.getByText(/the absurd is the essential concept/i).closest('[role="button"]');
      expect(firstResult).toBeInTheDocument();

      fireEvent.click(firstResult!);

      // Should clear active highlight and navigate
      expect(mockSetActiveHighlightId).toHaveBeenCalledWith(null);
      expect(mockPush).toHaveBeenCalledWith("/app/documents/doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    });

    test("navigates to correct document for second result", async () => {
      mockUseSearch.mockReturnValue({
        results: mockResults,
        isLoading: false,
        isError: false,
        error: null,
        isSuccess: true,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("test");
      renderSearchPage();

      // Find and click the second result
      const secondResult = screen.getByText(/revolt is the refusal/i).closest('[role="button"]');
      fireEvent.click(secondResult!);

      expect(mockPush).toHaveBeenCalledWith("/app/documents/doc_bbbbbbbb-cccc-dddd-eeee-ffffffffffff");
    });

    test("supports keyboard navigation (Enter key)", async () => {
      mockUseSearch.mockReturnValue({
        results: mockResults,
        isLoading: false,
        isError: false,
        error: null,
        isSuccess: true,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("test");
      renderSearchPage();

      // Find the first result and press Enter
      const firstResult = screen.getByText(/the absurd is the essential concept/i).closest('[role="button"]');
      fireEvent.keyDown(firstResult!, { key: "Enter" });

      expect(mockPush).toHaveBeenCalledWith("/app/documents/doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");
    });
  });

  describe("result metadata display", () => {
    test("shows similarity score on results", () => {
      mockUseSearch.mockReturnValue({
        results: mockResults,
        isLoading: false,
        isError: false,
        error: null,
        isSuccess: true,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("test");
      renderSearchPage();

      // Should show percentage scores
      expect(screen.getByText(/89% match/i)).toBeInTheDocument();
      expect(screen.getByText(/75% match/i)).toBeInTheDocument();
    });

    test("shows result kind badge", () => {
      mockUseSearch.mockReturnValue({
        results: mockResults,
        isLoading: false,
        isError: false,
        error: null,
        isSuccess: true,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("test");
      renderSearchPage();

      // Should show "Chunk" badges
      const badges = screen.getAllByText(/chunk/i);
      expect(badges.length).toBeGreaterThanOrEqual(2);
    });

    test("shows text position information", () => {
      mockUseSearch.mockReturnValue({
        results: mockResults,
        isLoading: false,
        isError: false,
        error: null,
        isSuccess: true,
        hasMore: false,
        nextCursor: null,
        refetch: vi.fn(),
      });

      mockGet.mockReturnValue("test");
      renderSearchPage();

      // Should show position info for first result
      expect(screen.getByText(/10,240/)).toBeInTheDocument();
    });
  });
});

