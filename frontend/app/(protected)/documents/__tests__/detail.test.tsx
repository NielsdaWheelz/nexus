import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { DocumentsService } from "@/lib/generated-api";
import type { DocumentListItem } from "@/lib/generated-api";
import DocumentDetailPage from "../[documentId]/page";

// Mock the generated API
vi.mock("@/lib/generated-api", () => ({
  DocumentsService: {
    getDocumentDocumentsDocumentIdGet: vi.fn(),
  },
}));

// Mock next/link
vi.mock("next/link", () => {
  return {
    default: ({ children }: any) => children,
  };
});

const mockDocument: DocumentListItem = {
  id: "doc_11111111-2222-3333-4444-555555555555",
  title: "The Myth of Sisyphus",
  source_kind: "pdf",
  processing_status: "ready",
  created_at: "2025-01-01T12:00:00Z",
  updated_at: "2025-01-01T13:00:00Z",
};

describe("DocumentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders loading state initially", () => {
    (DocumentsService.getDocumentDocumentsDocumentIdGet as any).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockDocument), 100))
    );

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    expect(screen.getByText("Loading document...")).toBeInTheDocument();
  });

  test("renders document details on successful fetch", async () => {
    (DocumentsService.getDocumentDocumentsDocumentIdGet as any).mockResolvedValue(mockDocument);

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("The Myth of Sisyphus")).toBeInTheDocument();
      expect(screen.getByText("PDF")).toBeInTheDocument();
      expect(screen.getByText("Ready")).toBeInTheDocument();
    });
  });

  test("renders back to documents link", async () => {
    (DocumentsService.getDocumentDocumentsDocumentIdGet as any).mockResolvedValue(mockDocument);

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("← Back to documents")).toBeInTheDocument();
    });
  });

  test("renders error state on not found", async () => {
    (DocumentsService.getDocumentDocumentsDocumentIdGet as any).mockRejectedValue(
      new Error("API error: 404 not found")
    );

    render(<DocumentDetailPage params={{ documentId: "doc_nonexistent" }} />);

    await waitFor(() => {
      expect(screen.getAllByText("Document not found")).toHaveLength(2);
    });
  });

  test("renders error state on API failure", async () => {
    (DocumentsService.getDocumentDocumentsDocumentIdGet as any).mockRejectedValue(
      new Error("Network error")
    );

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("Failed to load document")).toBeInTheDocument();
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  test("displays processing state message", async () => {
    const processingDoc: DocumentListItem = {
      ...mockDocument,
      processing_status: "processing",
    };

    (DocumentsService.getDocumentDocumentsDocumentIdGet as any).mockResolvedValue(processingDoc);

    render(
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
      processing_status: "failed",
    };

    (DocumentsService.getDocumentDocumentsDocumentIdGet as any).mockResolvedValue(failedDoc);

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(
        screen.getByText("This document failed to process. Please try uploading it again.")
      ).toBeInTheDocument();
    });
  });

  test("displays document ID in monospace", async () => {
    (DocumentsService.getDocumentDocumentsDocumentIdGet as any).mockResolvedValue(mockDocument);

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("doc_11111111-2222-3333-4444-555555555555")).toBeInTheDocument();
    });
  });
});
