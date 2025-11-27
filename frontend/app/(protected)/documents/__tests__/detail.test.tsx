import { render, screen, waitFor } from "@testing-library/react";
import { useApiRequest } from "@/lib/api-client";
import { DocumentListItem } from "@/lib/api/documents";
import DocumentDetailPage from "../[documentId]/page";

// Mock the useApiRequest hook
jest.mock("@/lib/api-client", () => ({
  useApiRequest: jest.fn(),
}));

// Mock next/link
jest.mock("next/link", () => {
  return ({ children }: any) => children;
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
    jest.clearAllMocks();
  });

  test("renders loading state initially", () => {
    const mockApiGet = jest.fn(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(mockDocument), 100)
        )
    );

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    expect(screen.getByText("Loading document...")).toBeInTheDocument();
  });

  test("renders document details on successful fetch", async () => {
    const mockApiGet = jest.fn().mockResolvedValue(mockDocument);

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

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
    const mockApiGet = jest.fn().mockResolvedValue(mockDocument);

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("← Back to documents")).toBeInTheDocument();
    });
  });

  test("renders error state on not found", async () => {
    const mockApiGet = jest
      .fn()
      .mockRejectedValue(new Error("API error: 404 not found"));

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(
      <DocumentDetailPage params={{ documentId: "doc_nonexistent" }} />
    );

    await waitFor(() => {
      expect(screen.getByText("Document not found")).toBeInTheDocument();
    });
  });

  test("renders error state on API failure", async () => {
    const mockApiGet = jest
      .fn()
      .mockRejectedValue(new Error("Network error"));

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load document")
      ).toBeInTheDocument();
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });
  });

  test("displays processing state message", async () => {
    const processingDoc: DocumentListItem = {
      ...mockDocument,
      processing_status: "processing",
    };

    const mockApiGet = jest.fn().mockResolvedValue(processingDoc);

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

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

    const mockApiGet = jest.fn().mockResolvedValue(failedDoc);

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "This document failed to process. Please try uploading it again."
        )
      ).toBeInTheDocument();
    });
  });

  test("displays document ID in monospace", async () => {
    const mockApiGet = jest.fn().mockResolvedValue(mockDocument);

    (useApiRequest as jest.Mock).mockReturnValue({
      apiGet: mockApiGet,
    });

    render(
      <DocumentDetailPage params={{ documentId: "doc_11111111-2222-3333-4444-555555555555" }} />
    );

    await waitFor(() => {
      expect(
        screen.getByText("doc_11111111-2222-3333-4444-555555555555")
      ).toBeInTheDocument();
    });
  });
});
