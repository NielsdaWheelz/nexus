import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, test, expect, beforeEach, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { AnnotationsInspectorTab } from "../AnnotationsInspectorTab";
import type { AnnotationItem } from "@/lib/api/annotations";

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
function createMockAnnotation(
  id: string,
  content: string,
  highlightId: string = "hl_test123",
  createdAt: string = "2025-01-01T12:00:00Z"
): AnnotationItem {
  return {
    id,
    user_id: "usr_test",
    document_id: "doc_test",
    highlight_id: highlightId,
    content,
    created_at: createdAt,
    updated_at: createdAt,
  };
}

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

describe("AnnotationsInspectorTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock window.confirm
    vi.spyOn(window, "confirm").mockImplementation(() => true);
  });

  describe("when no highlight is selected", () => {
    test("renders empty state prompting to select a highlight", () => {
      render(<AnnotationsInspectorTab highlightId={null} />, {
        wrapper: createWrapper(),
      });

      expect(
        screen.getByTestId("annotations-inspector-no-highlight")
      ).toBeInTheDocument();
      expect(screen.getByText("No highlight selected")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Select a highlight in the document to view its annotations."
        )
      ).toBeInTheDocument();
    });

    test("does not call useAnnotations when highlightId is null", () => {
      render(<AnnotationsInspectorTab highlightId={null} />, {
        wrapper: createWrapper(),
      });

      // API should not have been called
      expect(mockListAnnotationsForHighlight).not.toHaveBeenCalled();
    });
  });

  describe("when highlight is selected", () => {
    test("renders loading state initially", async () => {
      // Never resolve to keep loading state
      mockListAnnotationsForHighlight.mockImplementation(
        () => new Promise(() => {})
      );

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      expect(
        screen.getByTestId("annotations-inspector-loading")
      ).toBeInTheDocument();
      expect(screen.getByText("Loading annotations...")).toBeInTheDocument();
    });

    test("renders empty state when no annotations exist", async () => {
      mockListAnnotationsForHighlight.mockResolvedValue({
        items: [],
        next_cursor: null,
        has_more: false,
      });

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(
          screen.getByTestId("annotations-inspector-empty")
        ).toBeInTheDocument();
      });

      expect(screen.getByText("No annotations yet.")).toBeInTheDocument();
    });

    test("renders error state on fetch failure", async () => {
      mockListAnnotationsForHighlight.mockRejectedValue(
        new Error("Network error")
      );

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(
          screen.getByTestId("annotations-inspector-error")
        ).toBeInTheDocument();
      });

      expect(screen.getByText("Failed to load annotations")).toBeInTheDocument();
      expect(screen.getByText("Network error")).toBeInTheDocument();
    });

    test("renders list of annotations", async () => {
      const annotations = [
        createMockAnnotation("ann_1", "First note"),
        createMockAnnotation("ann_2", "Second note"),
      ];

      mockListAnnotationsForHighlight.mockResolvedValue({
        items: annotations,
        next_cursor: null,
        has_more: false,
      });

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(
          screen.getByTestId("annotations-inspector-list")
        ).toBeInTheDocument();
      });

      expect(screen.getByText("2 annotations")).toBeInTheDocument();
      expect(screen.getByText("First note")).toBeInTheDocument();
      expect(screen.getByText("Second note")).toBeInTheDocument();
    });

    test("shows correct count for single annotation", async () => {
      const annotations = [createMockAnnotation("ann_1", "Only note")];

      mockListAnnotationsForHighlight.mockResolvedValue({
        items: annotations,
        next_cursor: null,
        has_more: false,
      });

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("1 annotation")).toBeInTheDocument();
      });
    });
  });

  describe("create annotation", () => {
    beforeEach(() => {
      mockListAnnotationsForHighlight.mockResolvedValue({
        items: [],
        next_cursor: null,
        has_more: false,
      });
    });

    test("creates annotation on submit", async () => {
      const newAnnotation = createMockAnnotation("ann_new", "New annotation");
      mockCreateAnnotation.mockResolvedValue(newAnnotation);

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByTestId("annotation-create-input")).toBeInTheDocument();
      });

      const input = screen.getByTestId("annotation-create-input");
      const submitBtn = screen.getByTestId("annotation-create-btn");

      // Button should be disabled when input is empty
      expect(submitBtn).toBeDisabled();

      // Type content
      fireEvent.change(input, { target: { value: "New annotation" } });
      expect(submitBtn).not.toBeDisabled();

      // Submit
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(mockCreateAnnotation).toHaveBeenCalledWith({
          highlightId: "hl_test123",
          content: "New annotation",
        });
      });

      // Input should be cleared after success
      await waitFor(() => {
        expect(input).toHaveValue("");
      });
    });

    test("shows error when create fails", async () => {
      mockCreateAnnotation.mockRejectedValue(new Error("Server error"));

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByTestId("annotation-create-input")).toBeInTheDocument();
      });

      const input = screen.getByTestId("annotation-create-input");
      const submitBtn = screen.getByTestId("annotation-create-btn");

      fireEvent.change(input, { target: { value: "Will fail" } });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(
          screen.getByTestId("annotation-create-error")
        ).toBeInTheDocument();
      });

      expect(screen.getByText("Server error")).toBeInTheDocument();
    });

    test("trims whitespace from content", async () => {
      const newAnnotation = createMockAnnotation("ann_new", "Trimmed");
      mockCreateAnnotation.mockResolvedValue(newAnnotation);

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByTestId("annotation-create-input")).toBeInTheDocument();
      });

      const input = screen.getByTestId("annotation-create-input");
      fireEvent.change(input, { target: { value: "  Trimmed  " } });
      fireEvent.click(screen.getByTestId("annotation-create-btn"));

      await waitFor(() => {
        expect(mockCreateAnnotation).toHaveBeenCalledWith({
          highlightId: "hl_test123",
          content: "Trimmed",
        });
      });
    });

    test("disables submit for whitespace-only content", async () => {
      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByTestId("annotation-create-input")).toBeInTheDocument();
      });

      const input = screen.getByTestId("annotation-create-input");
      const submitBtn = screen.getByTestId("annotation-create-btn");

      fireEvent.change(input, { target: { value: "   " } });
      expect(submitBtn).toBeDisabled();
    });
  });

  describe("edit annotation", () => {
    const existingAnnotation = createMockAnnotation("ann_1", "Original content");

    beforeEach(() => {
      mockListAnnotationsForHighlight.mockResolvedValue({
        items: [existingAnnotation],
        next_cursor: null,
        has_more: false,
      });
    });

    test("enters edit mode when clicking edit", async () => {
      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("Original content")).toBeInTheDocument();
      });

      // Click edit
      fireEvent.click(screen.getByTestId("annotation-edit-btn"));

      // Should show edit input with existing content
      const editInput = screen.getByTestId("annotation-edit-input");
      expect(editInput).toBeInTheDocument();
      expect(editInput).toHaveValue("Original content");

      // Card should have editing attribute
      expect(screen.getByTestId("annotation-card-ann_1")).toHaveAttribute(
        "data-editing",
        "true"
      );
    });

    test("cancels edit without saving", async () => {
      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("Original content")).toBeInTheDocument();
      });

      // Enter edit mode
      fireEvent.click(screen.getByTestId("annotation-edit-btn"));

      // Change content
      const editInput = screen.getByTestId("annotation-edit-input");
      fireEvent.change(editInput, { target: { value: "Changed content" } });

      // Cancel
      fireEvent.click(screen.getByTestId("annotation-cancel-btn"));

      // Should show original content, not changed
      await waitFor(() => {
        expect(screen.getByText("Original content")).toBeInTheDocument();
      });

      // Update API should not have been called
      expect(mockUpdateAnnotation).not.toHaveBeenCalled();
    });

    test("saves edited content", async () => {
      const updatedAnnotation = createMockAnnotation("ann_1", "Updated content");
      mockUpdateAnnotation.mockResolvedValue(updatedAnnotation);

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("Original content")).toBeInTheDocument();
      });

      // Enter edit mode
      fireEvent.click(screen.getByTestId("annotation-edit-btn"));

      // Change content
      const editInput = screen.getByTestId("annotation-edit-input");
      fireEvent.change(editInput, { target: { value: "Updated content" } });

      // Save
      fireEvent.click(screen.getByTestId("annotation-save-btn"));

      await waitFor(() => {
        expect(mockUpdateAnnotation).toHaveBeenCalledWith({
          annotationId: "ann_1",
          content: "Updated content",
        });
      });
    });

    test("shows error when update fails", async () => {
      mockUpdateAnnotation.mockRejectedValue(new Error("Update failed"));

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("Original content")).toBeInTheDocument();
      });

      // Enter edit mode and save
      fireEvent.click(screen.getByTestId("annotation-edit-btn"));
      fireEvent.click(screen.getByTestId("annotation-save-btn"));

      await waitFor(() => {
        expect(screen.getByTestId("annotation-edit-error")).toBeInTheDocument();
      });

      expect(screen.getByText("Update failed")).toBeInTheDocument();
    });
  });

  describe("delete annotation", () => {
    const existingAnnotation = createMockAnnotation("ann_1", "To be deleted");

    beforeEach(() => {
      mockListAnnotationsForHighlight.mockResolvedValue({
        items: [existingAnnotation],
        next_cursor: null,
        has_more: false,
      });
    });

    test("deletes annotation on confirm", async () => {
      mockDeleteAnnotation.mockResolvedValue(undefined);

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("To be deleted")).toBeInTheDocument();
      });

      // Click delete
      fireEvent.click(screen.getByTestId("annotation-delete-btn"));

      // Confirm should have been called
      expect(window.confirm).toHaveBeenCalledWith("Delete this annotation?");

      // Delete API should have been called
      await waitFor(() => {
        expect(mockDeleteAnnotation).toHaveBeenCalledWith("ann_1");
      });
    });

    test("does not delete when user cancels confirm", async () => {
      vi.spyOn(window, "confirm").mockReturnValue(false);

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByText("To be deleted")).toBeInTheDocument();
      });

      // Click delete
      fireEvent.click(screen.getByTestId("annotation-delete-btn"));

      // Delete API should not have been called
      expect(mockDeleteAnnotation).not.toHaveBeenCalled();
    });
  });

  describe("data attributes", () => {
    test("each annotation card has correct data-testid", async () => {
      const annotations = [
        createMockAnnotation("ann_1", "First"),
        createMockAnnotation("ann_2", "Second"),
      ];

      mockListAnnotationsForHighlight.mockResolvedValue({
        items: annotations,
        next_cursor: null,
        has_more: false,
      });

      render(<AnnotationsInspectorTab highlightId="hl_test123" />, {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(screen.getByTestId("annotation-card-ann_1")).toBeInTheDocument();
        expect(screen.getByTestId("annotation-card-ann_2")).toBeInTheDocument();
      });
    });
  });

  describe("highlight change", () => {
    test("resets edit state when highlightId changes", async () => {
      const annotationA = createMockAnnotation("ann_a", "Annotation for A", "hl_A");
      const annotationB = createMockAnnotation("ann_b", "Annotation for B", "hl_B");

      // First call returns annotation for highlight A
      mockListAnnotationsForHighlight.mockResolvedValueOnce({
        items: [annotationA],
        next_cursor: null,
        has_more: false,
      });

      const Wrapper = createWrapper();
      const { rerender } = render(
        <AnnotationsInspectorTab highlightId="hl_A" />,
        { wrapper: Wrapper }
      );

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText("Annotation for A")).toBeInTheDocument();
      });

      // Enter edit mode
      fireEvent.click(screen.getByTestId("annotation-edit-btn"));
      expect(screen.getByTestId("annotation-edit-input")).toBeInTheDocument();
      expect(screen.getByTestId("annotation-card-ann_a")).toHaveAttribute(
        "data-editing",
        "true"
      );

      // Mock second call for highlight B
      mockListAnnotationsForHighlight.mockResolvedValueOnce({
        items: [annotationB],
        next_cursor: null,
        has_more: false,
      });

      // Change highlight
      rerender(
        <Wrapper>
          <AnnotationsInspectorTab highlightId="hl_B" />
        </Wrapper>
      );

      // Wait for new annotations to load
      await waitFor(() => {
        expect(screen.getByText("Annotation for B")).toBeInTheDocument();
      });

      // Edit mode should be reset - annotation B's card should NOT be in edit mode
      expect(screen.getByTestId("annotation-card-ann_b")).toHaveAttribute(
        "data-editing",
        "false"
      );
    });

    test("clears create form when highlightId changes", async () => {
      mockListAnnotationsForHighlight.mockResolvedValue({
        items: [],
        next_cursor: null,
        has_more: false,
      });

      const Wrapper = createWrapper();
      const { rerender } = render(
        <AnnotationsInspectorTab highlightId="hl_A" />,
        { wrapper: Wrapper }
      );

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByTestId("annotation-create-input")).toBeInTheDocument();
      });

      // Type something in create form
      const input = screen.getByTestId("annotation-create-input");
      fireEvent.change(input, { target: { value: "Draft content" } });
      expect(input).toHaveValue("Draft content");

      // Change highlight
      rerender(
        <Wrapper>
          <AnnotationsInspectorTab highlightId="hl_B" />
        </Wrapper>
      );

      // Wait for re-render
      await waitFor(() => {
        expect(screen.getByTestId("annotation-create-input")).toBeInTheDocument();
      });

      // Create form should be cleared
      expect(screen.getByTestId("annotation-create-input")).toHaveValue("");
    });

    test("fetches annotations for new highlight", async () => {
      mockListAnnotationsForHighlight.mockResolvedValue({
        items: [],
        next_cursor: null,
        has_more: false,
      });

      const Wrapper = createWrapper();
      const { rerender } = render(
        <AnnotationsInspectorTab highlightId="hl_A" />,
        { wrapper: Wrapper }
      );

      await waitFor(() => {
        expect(mockListAnnotationsForHighlight).toHaveBeenCalledWith(
          "hl_A",
          undefined,
          100
        );
      });

      // Change highlight
      rerender(
        <Wrapper>
          <AnnotationsInspectorTab highlightId="hl_B" />
        </Wrapper>
      );

      await waitFor(() => {
        expect(mockListAnnotationsForHighlight).toHaveBeenCalledWith(
          "hl_B",
          undefined,
          100
        );
      });
    });
  });
});

