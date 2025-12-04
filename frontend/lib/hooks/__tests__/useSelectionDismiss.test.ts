/**
 * Tests for useSelectionDismiss hook and helper functions.
 *
 * These tests verify the escape key and click-outside dismissal behavior
 * in isolation from the DOM event handling complexity.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import {
  useSelectionDismiss,
  isClickOutside,
  isEscapeKey,
} from "../useSelectionDismiss";

describe("isEscapeKey", () => {
  it("returns true for Escape key", () => {
    expect(isEscapeKey("Escape")).toBe(true);
  });

  it("returns false for other keys", () => {
    expect(isEscapeKey("Enter")).toBe(false);
    expect(isEscapeKey("Tab")).toBe(false);
    expect(isEscapeKey("a")).toBe(false);
    expect(isEscapeKey("Esc")).toBe(false); // Different from "Escape"
  });
});

describe("isClickOutside", () => {
  it("returns true when clickTarget is null", () => {
    const container = document.createElement("div");
    expect(isClickOutside(null, container)).toBe(true);
  });

  it("returns true when container is null", () => {
    const target = document.createElement("span");
    expect(isClickOutside(target, null)).toBe(true);
  });

  it("returns true when both are null", () => {
    expect(isClickOutside(null, null)).toBe(true);
  });

  it("returns false when clickTarget is inside container", () => {
    const container = document.createElement("div");
    const child = document.createElement("span");
    container.appendChild(child);
    
    expect(isClickOutside(child, container)).toBe(false);
  });

  it("returns false when clickTarget is the container itself", () => {
    const container = document.createElement("div");
    expect(isClickOutside(container, container)).toBe(false);
  });

  it("returns true when clickTarget is outside container", () => {
    const container = document.createElement("div");
    const outside = document.createElement("span");
    
    // Both are separate elements, not parent/child
    expect(isClickOutside(outside, container)).toBe(true);
  });

  it("returns false when clickTarget is deeply nested inside container", () => {
    const container = document.createElement("div");
    const level1 = document.createElement("div");
    const level2 = document.createElement("span");
    const level3 = document.createElement("button");
    
    container.appendChild(level1);
    level1.appendChild(level2);
    level2.appendChild(level3);
    
    expect(isClickOutside(level3, container)).toBe(false);
  });
});

describe("useSelectionDismiss", () => {
  let mockOnDismiss: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockOnDismiss = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns isActive matching the input", () => {
    const { result, rerender } = renderHook(
      ({ isActive }) =>
        useSelectionDismiss({
          isActive,
          onDismiss: mockOnDismiss,
        }),
      { initialProps: { isActive: false } }
    );

    expect(result.current.isActive).toBe(false);

    rerender({ isActive: true });
    expect(result.current.isActive).toBe(true);
  });

  it("does not call onDismiss when isActive is false", () => {
    renderHook(() =>
      useSelectionDismiss({
        isActive: false,
        onDismiss: mockOnDismiss,
      })
    );

    // Simulate keyboard event
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });

    expect(mockOnDismiss).not.toHaveBeenCalled();
  });

  it("calls onDismiss on Escape key when isActive is true", () => {
    renderHook(() =>
      useSelectionDismiss({
        isActive: true,
        onDismiss: mockOnDismiss,
      })
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });

    expect(mockOnDismiss).toHaveBeenCalledTimes(1);
  });

  it("does not call onDismiss for other keys", () => {
    renderHook(() =>
      useSelectionDismiss({
        isActive: true,
        onDismiss: mockOnDismiss,
      })
    );

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    });

    expect(mockOnDismiss).not.toHaveBeenCalled();
  });

  it("calls onDismiss on mousedown outside when excludeRef is not provided", () => {
    renderHook(() =>
      useSelectionDismiss({
        isActive: true,
        onDismiss: mockOnDismiss,
      })
    );

    act(() => {
      document.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    });

    expect(mockOnDismiss).toHaveBeenCalledTimes(1);
  });

  it("does not call onDismiss when clicking inside excludeRef element", () => {
    const container = document.createElement("div");
    const button = document.createElement("button");
    container.appendChild(button);
    document.body.appendChild(container);

    const excludeRef = { current: container };

    renderHook(() =>
      useSelectionDismiss({
        isActive: true,
        onDismiss: mockOnDismiss,
        excludeRef,
      })
    );

    // Click inside the excluded container
    act(() => {
      const event = new MouseEvent("mousedown", { bubbles: true });
      Object.defineProperty(event, "target", { value: button, writable: false });
      document.dispatchEvent(event);
    });

    expect(mockOnDismiss).not.toHaveBeenCalled();

    // Cleanup
    document.body.removeChild(container);
  });

  it("calls onDismiss when clicking outside excludeRef element", () => {
    const container = document.createElement("div");
    const outside = document.createElement("span");
    document.body.appendChild(container);
    document.body.appendChild(outside);

    const excludeRef = { current: container };

    renderHook(() =>
      useSelectionDismiss({
        isActive: true,
        onDismiss: mockOnDismiss,
        excludeRef,
      })
    );

    // Click outside the excluded container
    act(() => {
      const event = new MouseEvent("mousedown", { bubbles: true });
      Object.defineProperty(event, "target", { value: outside, writable: false });
      document.dispatchEvent(event);
    });

    expect(mockOnDismiss).toHaveBeenCalledTimes(1);

    // Cleanup
    document.body.removeChild(container);
    document.body.removeChild(outside);
  });

  it("cleans up event listeners when isActive changes to false", () => {
    const { rerender } = renderHook(
      ({ isActive }) =>
        useSelectionDismiss({
          isActive,
          onDismiss: mockOnDismiss,
        }),
      { initialProps: { isActive: true } }
    );

    // First verify it works when active
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(mockOnDismiss).toHaveBeenCalledTimes(1);

    // Now deactivate
    rerender({ isActive: false });
    mockOnDismiss.mockClear();

    // Should not trigger after deactivation
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(mockOnDismiss).not.toHaveBeenCalled();
  });

  it("cleans up event listeners on unmount", () => {
    const addSpy = vi.spyOn(document, "addEventListener");
    const removeSpy = vi.spyOn(document, "removeEventListener");

    const { unmount } = renderHook(() =>
      useSelectionDismiss({
        isActive: true,
        onDismiss: mockOnDismiss,
      })
    );

    // Should have added keydown and mousedown listeners
    expect(addSpy).toHaveBeenCalledWith("keydown", expect.any(Function));
    expect(addSpy).toHaveBeenCalledWith("mousedown", expect.any(Function));

    unmount();

    // Should have removed the listeners
    expect(removeSpy).toHaveBeenCalledWith("keydown", expect.any(Function));
    expect(removeSpy).toHaveBeenCalledWith("mousedown", expect.any(Function));

    addSpy.mockRestore();
    removeSpy.mockRestore();
  });
});

