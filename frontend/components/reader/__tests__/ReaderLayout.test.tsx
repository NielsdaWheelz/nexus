import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, test, expect, beforeEach } from "vitest";
import { ReaderLayout } from "../ReaderLayout";
import { useUIStore } from "@/lib/state/ui";

/**
 * Reset zustand store state between tests.
 */
function resetUIStore() {
  useUIStore.setState({
    isInspectorOpen: true,
    activeInspectorTab: "highlights",
    activeHighlightId: null,
    hoveredHighlightId: null,
  });
}

describe("ReaderLayout", () => {
  beforeEach(() => {
    resetUIStore();
  });

  describe("three-pane layout", () => {
    test("renders left navigation pane", () => {
      render(<ReaderLayout documentId="doc_123" />);

      expect(screen.getByText("Library")).toBeInTheDocument();
      expect(screen.getByText("Document navigation")).toBeInTheDocument();
    });

    test("renders center pane with children", () => {
      render(
        <ReaderLayout documentId="doc_123">
          <div data-testid="test-content">Test Content</div>
        </ReaderLayout>
      );

      expect(screen.getByTestId("test-content")).toBeInTheDocument();
      expect(screen.getByText("Test Content")).toBeInTheDocument();
    });

    test("renders center pane placeholder when no children", () => {
      render(<ReaderLayout documentId="doc_123" />);

      expect(screen.getByText("Reader content will appear here")).toBeInTheDocument();
    });

    test("renders right inspector pane with tabs", () => {
      render(<ReaderLayout documentId="doc_123" />);

      expect(screen.getByTestId("tab-highlights")).toBeInTheDocument();
      expect(screen.getByTestId("tab-annotations")).toBeInTheDocument();
      expect(screen.getByTestId("tab-chat")).toBeInTheDocument();
      expect(screen.getByTestId("tab-info")).toBeInTheDocument();
    });

    test("renders all three panes when inspector is open", () => {
      render(
        <ReaderLayout documentId="doc_123">
          <div>Center Content</div>
        </ReaderLayout>
      );

      // Left pane
      expect(screen.getByText("Library")).toBeInTheDocument();
      // Center pane
      expect(screen.getByText("Center Content")).toBeInTheDocument();
      // Right pane
      expect(screen.getByTestId("inspector-content-highlights")).toBeInTheDocument();
    });
  });

  describe("inspector toggle button", () => {
    test("renders toggle button", () => {
      render(<ReaderLayout documentId="doc_123" />);

      const toggleButton = screen.getByTestId("inspector-toggle");
      expect(toggleButton).toBeInTheDocument();
      expect(toggleButton).toHaveTextContent("Hide Inspector");
    });

    test("hides inspector when toggle clicked", () => {
      render(<ReaderLayout documentId="doc_123" />);

      // Inspector should be visible initially
      expect(screen.getByTestId("inspector-content-highlights")).toBeInTheDocument();

      // Click toggle
      fireEvent.click(screen.getByTestId("inspector-toggle"));

      // Inspector should be hidden
      expect(screen.queryByTestId("inspector-content-highlights")).not.toBeInTheDocument();
      expect(screen.getByTestId("inspector-toggle")).toHaveTextContent("Show Inspector");
    });

    test("shows inspector when toggle clicked again", () => {
      render(<ReaderLayout documentId="doc_123" />);

      // Hide inspector
      fireEvent.click(screen.getByTestId("inspector-toggle"));
      expect(screen.queryByTestId("inspector-content-highlights")).not.toBeInTheDocument();

      // Show inspector
      fireEvent.click(screen.getByTestId("inspector-toggle"));
      expect(screen.getByTestId("inspector-content-highlights")).toBeInTheDocument();
    });

    test("close button hides inspector", () => {
      render(<ReaderLayout documentId="doc_123" />);

      // Click close button
      fireEvent.click(screen.getByTestId("inspector-close"));

      // Inspector should be hidden
      expect(screen.queryByTestId("inspector-content-highlights")).not.toBeInTheDocument();
    });
  });

  describe("tab switching", () => {
    test("highlights tab is active by default", () => {
      render(<ReaderLayout documentId="doc_123" />);

      const highlightsTab = screen.getByTestId("tab-highlights");
      expect(highlightsTab).toHaveAttribute("aria-selected", "true");
      expect(screen.getByTestId("inspector-content-highlights")).toBeInTheDocument();
    });

    test("clicking tab switches active tab", () => {
      render(<ReaderLayout documentId="doc_123" />);

      // Click annotations tab
      fireEvent.click(screen.getByTestId("tab-annotations"));

      // Annotations tab should be active
      expect(screen.getByTestId("tab-annotations")).toHaveAttribute("aria-selected", "true");
      expect(screen.getByTestId("tab-highlights")).toHaveAttribute("aria-selected", "false");
      expect(screen.getByTestId("inspector-content-annotations")).toBeInTheDocument();
    });

    test("each tab shows its own content", () => {
      render(<ReaderLayout documentId="doc_123" />);

      // Highlights (default)
      expect(screen.getByText("Your document highlights will appear here.")).toBeInTheDocument();

      // Annotations
      fireEvent.click(screen.getByTestId("tab-annotations"));
      expect(screen.getByText("Your annotations will appear here.")).toBeInTheDocument();

      // Chat
      fireEvent.click(screen.getByTestId("tab-chat"));
      expect(screen.getByText("Chat with your document here.")).toBeInTheDocument();

      // Info
      fireEvent.click(screen.getByTestId("tab-info"));
      expect(screen.getByText("Document metadata and details.")).toBeInTheDocument();
    });

    test("active tab has visual distinction", () => {
      render(<ReaderLayout documentId="doc_123" />);

      const highlightsTab = screen.getByTestId("tab-highlights");
      const annotationsTab = screen.getByTestId("tab-annotations");

      // Highlights should have active styles (blue border)
      expect(highlightsTab.className).toContain("border-blue-600");

      // Annotations should not have active styles
      expect(annotationsTab.className).not.toContain("border-blue-600");

      // Switch tabs
      fireEvent.click(annotationsTab);

      // Now annotations should have active styles
      expect(annotationsTab.className).toContain("border-blue-600");
      expect(highlightsTab.className).not.toContain("border-blue-600");
    });
  });

  describe("zustand store wiring", () => {
    test("store defaults are applied", () => {
      const state = useUIStore.getState();
      expect(state.isInspectorOpen).toBe(true);
      expect(state.activeInspectorTab).toBe("highlights");
    });

    test("toggling via store alone affects layout", () => {
      const { rerender } = render(<ReaderLayout documentId="doc_123" />);

      // Inspector visible
      expect(screen.getByTestId("inspector-content-highlights")).toBeInTheDocument();

      // Toggle via store directly (wrapped in act)
      act(() => {
        useUIStore.getState().toggleInspector();
      });

      // Need to rerender to pick up store changes
      rerender(<ReaderLayout documentId="doc_123" />);

      // Inspector hidden
      expect(screen.queryByTestId("inspector-content-highlights")).not.toBeInTheDocument();
    });

    test("setting tab via store alone affects layout", () => {
      const { rerender } = render(<ReaderLayout documentId="doc_123" />);

      // Default tab
      expect(screen.getByTestId("inspector-content-highlights")).toBeInTheDocument();

      // Change tab via store directly (wrapped in act)
      act(() => {
        useUIStore.getState().setActiveInspectorTab("chat");
      });

      // Rerender
      rerender(<ReaderLayout documentId="doc_123" />);

      // Chat tab active
      expect(screen.getByTestId("inspector-content-chat")).toBeInTheDocument();
    });
  });

  describe("custom inspector content", () => {
    test("renders custom highlights content when provided", () => {
      render(
        <ReaderLayout
          documentId="doc_123"
          highlightsContent={<div data-testid="custom-highlights">Custom Highlights</div>}
        />
      );

      expect(screen.getByTestId("custom-highlights")).toBeInTheDocument();
      expect(screen.getByText("Custom Highlights")).toBeInTheDocument();
      // Should not show stub content
      expect(screen.queryByText("Your document highlights will appear here.")).not.toBeInTheDocument();
    });

    test("renders custom annotations content when provided", () => {
      render(
        <ReaderLayout
          documentId="doc_123"
          annotationsContent={<div data-testid="custom-annotations">Custom Annotations</div>}
        />
      );

      // Switch to annotations tab
      fireEvent.click(screen.getByTestId("tab-annotations"));

      expect(screen.getByTestId("custom-annotations")).toBeInTheDocument();
      expect(screen.getByText("Custom Annotations")).toBeInTheDocument();
    });

    test("falls back to stub content when custom content not provided", () => {
      render(<ReaderLayout documentId="doc_123" />);

      // Highlights tab (default) - should show stub
      expect(screen.getByText("Your document highlights will appear here.")).toBeInTheDocument();

      // Annotations tab - should show stub
      fireEvent.click(screen.getByTestId("tab-annotations"));
      expect(screen.getByText("Your annotations will appear here.")).toBeInTheDocument();
    });
  });
});

