import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { useApiRequest } from "@/lib/api-client";
import { DocumentListResponse } from "@/lib/api/documents";
import DocumentsPage from "../page";

// Mock the useApiRequest hook
jest.mock("@/lib/api-client", () => ({
  useApiRequest: jest.fn(),
}));

// Mock next/link
jest.mock("next/link", () => {
  return ({ children, href }: any) => children;
});

// Mock the window.location.href
delete (window as any).location;
window.location = { ...window.location, href: "" };

const mockDocuments: DocumentListResponse = {
  items: [
    {
      id: "doc_11111111-2222-3333-4444-555555555555",
      title: "The Myth of Sisyphus",
      source_kind: "pdf",
      processing_status: "ready",
      created_at: "2025-01-01T12:00:00Z",
      updated_at: "2025-01-01T12:00:00Z",
    },
    {
      id: "doc_22222222-3333-4444-5555-666666666666",
      title: "Crime and Punishment",
      source_kind: "epub",
      processing_status: "ready",
      created_at: "2025-01-02T10:30:00Z",
      updated_at: "2025-01-02T10:32:00Z",
    },
  ],
  next_cursor: null,
  has_more: false,
};

describe("DocumentsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("renders loading state initially", async () => {
    const mockApiGet = jest.fn(
      () => new Promise((resolve) => setTimeout(() => resolve(mockDocuments), 100))
    );

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(<DocumentsPage />);

    expect(screen.getByText("Loading documents...")).toBeInTheDocument();
  });

  test("renders documents list on successful fetch", async () => {
    const mockApiGet = jest.fn().mockResolvedValue(mockDocuments);

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Documents")).toBeInTheDocument();
      expect(screen.getByText("The Myth of Sisyphus")).toBeInTheDocument();
      expect(screen.getByText("Crime and Punishment")).toBeInTheDocument();
    });
  });

  test("displays document metadata correctly", async () => {
    const mockApiGet = jest.fn().mockResolvedValue(mockDocuments);

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("PDF")).toBeInTheDocument();
      expect(screen.getByText("EPUB")).toBeInTheDocument();
      expect(screen.getAllByText("Ready")).toHaveLength(2);
    });
  });

  test("renders empty state when no documents", async () => {
    const mockApiGet = jest.fn().mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("No documents yet")).toBeInTheDocument();
    });
  });

  test("renders error state on API failure", async () => {
    const mockApiGet = jest.fn().mockRejectedValue(new Error("API error: 500"));

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load documents")).toBeInTheDocument();
      expect(screen.getByText("API error: 500")).toBeInTheDocument();
      expect(screen.getByText("Retry")).toBeInTheDocument();
    });
  });

  test("retry button refetches documents", async () => {
    const mockApiGet = jest
      .fn()
      .mockRejectedValueOnce(new Error("API error"))
      .mockResolvedValueOnce(mockDocuments);

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(<DocumentsPage />);

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
    const mockApiGet = jest.fn().mockResolvedValue({
      items: mockDocuments.items,
      next_cursor: "next_page_cursor",
      has_more: true,
    });

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Load More")).toBeInTheDocument();
    });
  });
});
