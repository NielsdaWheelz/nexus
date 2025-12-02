import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, beforeEach, describe, test, expect } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import UploadPage from "../page";
import type { ClientError } from "@/lib/api/http";
import type { DocumentUploadResponse } from "@/lib/generated-api";

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
  }),
}));

// Mock the API wrapper layer
vi.mock("@/lib/api/documents", () => ({
  uploadDocument: vi.fn(),
  isClientError: (error: unknown): error is ClientError =>
    typeof error === "object" &&
    error !== null &&
    "httpStatus" in error &&
    "code" in error &&
    "message" in error,
}));

// Import the mocked function for type-safe access
import { uploadDocument } from "@/lib/api/documents";
const mockUploadDocument = vi.mocked(uploadDocument);

const mockUploadResponse: DocumentUploadResponse = {
  id: "doc_11111111-2222-3333-4444-555555555555",
  title: "test-document.pdf",
  source_kind: "pdf" as DocumentUploadResponse.source_kind,
  created_at: "2025-01-01T12:00:00Z",
  updated_at: "2025-01-01T12:00:00Z",
};

/**
 * Helper to render component with QueryClientProvider.
 */
function renderWithQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

/**
 * Helper to create a mock File object.
 */
function createMockFile(name: string, type: string): File {
  return new File(["test content"], name, { type });
}

describe("UploadPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders upload form with all required elements", () => {
    renderWithQueryClient(<UploadPage />);

    // Page heading
    expect(screen.getByText("Upload Document")).toBeInTheDocument();

    // File input
    expect(screen.getByLabelText("File")).toBeInTheDocument();

    // Source kind selector
    expect(screen.getByLabelText("Document Type")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "PDF" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "EPUB" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "HTML" })).toBeInTheDocument();

    // Optional title field
    expect(screen.getByLabelText(/Title/)).toBeInTheDocument();

    // Submit button
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
  });

  test("submit button is disabled when file is not selected", () => {
    renderWithQueryClient(<UploadPage />);

    const submitButton = screen.getByRole("button", { name: "Upload" });
    expect(submitButton).toBeDisabled();
  });

  test("submit button is disabled when source kind is not selected", () => {
    renderWithQueryClient(<UploadPage />);

    // Select a file but no source kind
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    const submitButton = screen.getByRole("button", { name: "Upload" });
    expect(submitButton).toBeDisabled();
  });

  test("submit button is enabled when file and source kind are selected", () => {
    renderWithQueryClient(<UploadPage />);

    // Select a file
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    // Select source kind
    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    const submitButton = screen.getByRole("button", { name: "Upload" });
    expect(submitButton).not.toBeDisabled();
  });

  test("shows selected filename after file selection", () => {
    renderWithQueryClient(<UploadPage />);

    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("my-document.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    expect(screen.getByText("Selected: my-document.pdf")).toBeInTheDocument();
  });

  test("successful upload redirects to document detail page", async () => {
    mockUploadDocument.mockResolvedValue(mockUploadResponse);

    renderWithQueryClient(<UploadPage />);

    // Select file
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    // Select source kind
    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    // Submit form
    const submitButton = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(
        `/app/documents/${mockUploadResponse.id}`
      );
    });
  });

  test("shows uploading state and disables button during upload", async () => {
    // Make upload take some time
    mockUploadDocument.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(mockUploadResponse), 100))
    );

    renderWithQueryClient(<UploadPage />);

    // Select file and source kind
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    // Submit
    const submitButton = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(submitButton);

    // Should show uploading state
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Uploading…" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
    });
  });

  test("calls uploadDocument with correct parameters", async () => {
    mockUploadDocument.mockResolvedValue(mockUploadResponse);

    renderWithQueryClient(<UploadPage />);

    // Select file
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    // Select source kind
    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    // Enter title
    const titleInput = screen.getByLabelText(/Title/);
    fireEvent.change(titleInput, { target: { value: "My Custom Title" } });

    // Submit
    const submitButton = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockUploadDocument).toHaveBeenCalledWith({
        file: mockFile,
        sourceKind: "pdf",
        title: "My Custom Title",
      });
    });
  });

  test("title is undefined when empty", async () => {
    mockUploadDocument.mockResolvedValue(mockUploadResponse);

    renderWithQueryClient(<UploadPage />);

    // Select file
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    // Select source kind
    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    // Don't enter a title

    // Submit
    const submitButton = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockUploadDocument).toHaveBeenCalledWith({
        file: mockFile,
        sourceKind: "pdf",
        title: undefined,
      });
    });
  });

  test("displays error message on upload failure", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Upload failed: storage unavailable",
      details: null,
      traceId: "req_xyz",
    };

    mockUploadDocument.mockRejectedValue(clientError);

    renderWithQueryClient(<UploadPage />);

    // Select file and source kind
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    // Submit
    const submitButton = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(submitButton);

    // Should show error message
    await waitFor(() => {
      expect(screen.getByText("Upload failed: storage unavailable")).toBeInTheDocument();
    });
  });

  test("submit button is re-enabled after error", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Upload failed",
      details: null,
      traceId: null,
    };

    mockUploadDocument.mockRejectedValue(clientError);

    renderWithQueryClient(<UploadPage />);

    // Select file and source kind
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    // Submit
    const submitButton = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(submitButton);

    // Wait for error and check button is re-enabled
    await waitFor(() => {
      expect(screen.getByText("Upload failed")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "Upload" })).not.toBeDisabled();
  });

  test("handles non-ClientError exceptions", async () => {
    mockUploadDocument.mockRejectedValue(new Error("Network error"));

    renderWithQueryClient(<UploadPage />);

    // Select file and source kind
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    // Submit
    const submitButton = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(submitButton);

    // Should show generic error message
    await waitFor(() => {
      expect(screen.getByText("An unexpected error occurred")).toBeInTheDocument();
    });
  });

  test("clears error when selecting a new file", async () => {
    const clientError: ClientError = {
      httpStatus: 500,
      code: "INTERNAL_ERROR",
      message: "Upload failed",
      details: null,
      traceId: null,
    };

    mockUploadDocument.mockRejectedValue(clientError);

    renderWithQueryClient(<UploadPage />);

    // Initial file selection and source kind
    const fileInput = screen.getByLabelText("File");
    const mockFile = createMockFile("test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [mockFile] } });

    const sourceKindSelect = screen.getByLabelText("Document Type");
    fireEvent.change(sourceKindSelect, { target: { value: "pdf" } });

    // Submit and get error
    const submitButton = screen.getByRole("button", { name: "Upload" });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText("Upload failed")).toBeInTheDocument();
    });

    // Select a new file
    const newFile = createMockFile("new-test.pdf", "application/pdf");
    fireEvent.change(fileInput, { target: { files: [newFile] } });

    // Error should be cleared
    expect(screen.queryByText("Upload failed")).not.toBeInTheDocument();
  });
});

