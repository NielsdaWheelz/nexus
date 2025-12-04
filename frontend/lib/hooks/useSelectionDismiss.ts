/**
 * useSelectionDismiss - Hook to handle dismissing selection state.
 *
 * Provides testable escape key and click-outside behavior for selection UI.
 * Factors out DOM event handling from components for easier unit testing.
 *
 * Usage:
 * ```tsx
 * const { isActive } = useSelectionDismiss({
 *   isActive: !!pendingSelection,
 *   onDismiss: handleCancelSelection,
 *   excludeRef: actionBarRef,
 * });
 * ```
 */

import { useEffect, useCallback, type RefObject } from "react";

/**
 * Options for the useSelectionDismiss hook.
 */
export interface UseSelectionDismissOptions {
  /** Whether the dismissible UI is currently active/visible */
  isActive: boolean;
  /** Callback to dismiss the selection */
  onDismiss: () => void;
  /** Ref to element that should be excluded from click-outside detection */
  excludeRef?: RefObject<HTMLElement | null>;
}

/**
 * Result of the useSelectionDismiss hook.
 */
export interface UseSelectionDismissResult {
  /** Whether the dismissible UI is currently active */
  isActive: boolean;
}

/**
 * Hook to handle escape key and click-outside dismissal of selection UI.
 *
 * Behavior:
 * - When isActive is true, pressing Escape calls onDismiss
 * - When isActive is true, clicking outside excludeRef calls onDismiss
 * - Automatically cleans up event listeners when isActive becomes false
 *
 * @param options - Configuration for the hook
 * @returns Object with isActive state
 *
 * @example
 * ```tsx
 * const [pendingSelection, setPendingSelection] = useState(null);
 * const actionBarRef = useRef<HTMLDivElement>(null);
 *
 * const handleDismiss = useCallback(() => {
 *   setPendingSelection(null);
 *   window.getSelection()?.removeAllRanges();
 * }, []);
 *
 * useSelectionDismiss({
 *   isActive: !!pendingSelection,
 *   onDismiss: handleDismiss,
 *   excludeRef: actionBarRef,
 * });
 * ```
 */
export function useSelectionDismiss({
  isActive,
  onDismiss,
  excludeRef,
}: UseSelectionDismissOptions): UseSelectionDismissResult {
  // Handle escape key to dismiss
  useEffect(() => {
    if (!isActive) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onDismiss();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isActive, onDismiss]);

  // Handle click outside to dismiss
  useEffect(() => {
    if (!isActive) return;

    const handleClickOutside = (e: MouseEvent) => {
      const excludeElement = excludeRef?.current;
      if (excludeElement && !excludeElement.contains(e.target as Node)) {
        onDismiss();
      } else if (!excludeElement) {
        // If no exclude ref, any click dismisses
        onDismiss();
      }
    };

    // Use mousedown so we catch clicks before they create a new selection
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isActive, onDismiss, excludeRef]);

  return { isActive };
}

/**
 * Pure function to determine if a click is outside an element.
 * Useful for testing without DOM dependencies.
 *
 * @param clickTarget - The clicked element
 * @param container - The container to check against
 * @returns true if click is outside container
 */
export function isClickOutside(
  clickTarget: Node | null,
  container: HTMLElement | null
): boolean {
  if (!clickTarget || !container) {
    return true;
  }
  return !container.contains(clickTarget);
}

/**
 * Pure function to determine if a key event is an escape key.
 * Useful for testing without DOM dependencies.
 *
 * @param key - The key from the event
 * @returns true if key is Escape
 */
export function isEscapeKey(key: string): boolean {
  return key === "Escape";
}

