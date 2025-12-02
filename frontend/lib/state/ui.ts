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
}

/** UI state actions. */
export interface UIActions {
  /** Set inspector open/closed state. */
  setInspectorOpen: (open: boolean) => void;
  /** Toggle inspector visibility. */
  toggleInspector: () => void;
  /** Set the active inspector tab. */
  setActiveInspectorTab: (tab: InspectorTab) => void;
}

/** Complete UI store type. */
export type UIStore = UIState & UIActions;

/**
 * Zustand store for UI state.
 *
 * Defaults:
 * - Inspector open by default
 * - Highlights tab active by default
 */
export const useUIStore = create<UIStore>((set) => ({
  // State
  isInspectorOpen: true,
  activeInspectorTab: "highlights",

  // Actions
  setInspectorOpen: (open) => set({ isInspectorOpen: open }),
  toggleInspector: () => set((state) => ({ isInspectorOpen: !state.isInspectorOpen })),
  setActiveInspectorTab: (tab) => set({ activeInspectorTab: tab }),
}));

