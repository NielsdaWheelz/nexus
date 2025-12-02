/**
 * UI state store for reader layout.
 *
 * This zustand store manages client-side UI state only.
 * No server state — that's handled by react-query.
 */

import { create } from "zustand";

/** Available inspector tabs. */
export type InspectorTab = "highlights" | "annotations" | "chat" | "info";

/** UI state shape. */
export interface UIState {
  /** Whether the right inspector pane is visible. */
  isInspectorOpen: boolean;
  /** Currently active inspector tab. */
  activeInspectorTab: InspectorTab;
  /** Currently selected/focused highlight ID (hl_<uuid>) */
  activeHighlightId: string | null;
  /** Currently hovered highlight ID (hl_<uuid>) */
  hoveredHighlightId: string | null;
}

/** UI state actions. */
export interface UIActions {
  /** Set inspector open/closed state. */
  setInspectorOpen: (open: boolean) => void;
  /** Toggle inspector visibility. */
  toggleInspector: () => void;
  /** Set the active inspector tab. */
  setActiveInspectorTab: (tab: InspectorTab) => void;
  /** Set the active/selected highlight ID. */
  setActiveHighlightId: (id: string | null) => void;
  /** Set the hovered highlight ID. */
  setHoveredHighlightId: (id: string | null) => void;
}

/** Complete UI store type. */
export type UIStore = UIState & UIActions;

/**
 * Zustand store for UI state.
 *
 * Defaults:
 * - Inspector open by default
 * - Highlights tab active by default
 * - No highlight selected or hovered
 */
export const useUIStore = create<UIStore>((set) => ({
  // State
  isInspectorOpen: true,
  activeInspectorTab: "highlights",
  activeHighlightId: null,
  hoveredHighlightId: null,

  // Actions
  setInspectorOpen: (open) => set({ isInspectorOpen: open }),
  toggleInspector: () => set((state) => ({ isInspectorOpen: !state.isInspectorOpen })),
  setActiveInspectorTab: (tab) => set({ activeInspectorTab: tab }),
  setActiveHighlightId: (id) => set({ activeHighlightId: id }),
  setHoveredHighlightId: (id) => set({ hoveredHighlightId: id }),
}));

