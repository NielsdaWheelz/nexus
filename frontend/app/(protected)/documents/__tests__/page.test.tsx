import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi } from "vitest";
import { DocumentsService } from "@/lib/generated-api";
import type { DocumentListResponse } from "@/lib/generated-api";
import DocumentsPage from "../page";

// Mock the generated API
vi.mock("@/lib/generated-api", () => ({
  DocumentsService: {
    listDocumentsDocumentsGet: vi.fn(),
  },
}));

// Mock next/link
vi.mock("next/link", () => {
  return {
    default: ({ children, href }: any) => children,
  };
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
    vi.clearAllMocks();
  });

  test("renders loading state initially", async () => {
    (DocumentsService.listDocumentsDocumentsGet as any).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockDocuments), 100))
    );

    render(<DocumentsPage />);

    expect(screen.getByText("Loading documents...")).toBeInTheDocument();
  });

  test("renders documents list on successful fetch", async () => {
    (DocumentsService.listDocumentsDocumentsGet as any).mockResolvedValue(mockDocuments);

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Documents")).toBeInTheDocument();
      expect(screen.getByText("The Myth of Sisyphus")).toBeInTheDocument();
      expect(screen.getByText("Crime and Punishment")).toBeInTheDocument();
    });
  });

  test("displays document metadata correctly", async () => {
    (DocumentsService.listDocumentsDocumentsGet as any).mockResolvedValue(mockDocuments);

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("PDF")).toBeInTheDocument();
      expect(screen.getByText("EPUB")).toBeInTheDocument();
      expect(screen.getAllByText("Ready")).toHaveLength(2);
    });
  });

  test("renders empty state when no documents", async () => {
    (DocumentsService.listDocumentsDocumentsGet as any).mockResolvedValue({
      items: [],
      next_cursor: null,
      has_more: false,
    });

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("No documents yet")).toBeInTheDocument();
    });
  });

  test("renders error state on API failure", async () => {
    (DocumentsService.listDocumentsDocumentsGet as any).mockRejectedValue(
      new Error("API error: 500")
    );

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load documents")).toBeInTheDocument();
      expect(screen.getByText("API error: 500")).toBeInTheDocument();
      expect(screen.getByText("Retry")).toBeInTheDocument();
    });
  });

  test("retry button refetches documents", async () => {
    (DocumentsService.listDocumentsDocumentsGet as any)
      .mockRejectedValueOnce(new Error("API error"))
      .mockResolvedValueOnce(mockDocuments);

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
    (DocumentsService.listDocumentsDocumentsGet as any).mockResolvedValue({
      items: mockDocuments.items,
      next_cursor: "next_page_cursor",
      has_more: true,
    });

    render(<DocumentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Load More")).toBeInTheDocument();
    });
  });
});
