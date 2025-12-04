/**
 * Anchoring Module
 *
 * This module provides pure functions for mapping between canonical text
 * offsets and reader-specific anchors (prefix/quote/suffix).
 *
 * Usage:
 * - When a user creates a highlight: use resolveSelectionToCanonicalOffsets
 *   to map the selection to canonical offsets, then buildAnchorTriple to
 *   create the context strings for persistence.
 *
 * - When loading highlights: use findBestAnchorPlacement to re-locate each
 *   highlight in the current canonical text.
 *
 * - When canonical text changes: use remapAnchorAfterCanonicalChange to
 *   update highlight positions.
 *
 * - For PDF rendering: use applyPdfHighlightsToPage to decorate the text layer.
 *
 * All functions are pure, deterministic, and never throw.
 */

// Re-export types
export type {
  AnchorStatus,
  AnchorTriple,
  CanonicalAnchorInput,
  AnchorResolution,
  SelectionContext,
  SelectionResolution,
} from "./types";

// Re-export core functions
export {
  findBestAnchorPlacement,
  remapAnchorAfterCanonicalChange,
  resolveSelectionToCanonicalOffsets,
  buildAnchorTriple,
} from "./core";

// Re-export PDF anchoring types and functions
export type { PdfHighlightAnchor, ApplyHighlightsResult } from "./pdfAnchoring";
export {
  applyPdfHighlightsToPage,
  clearPdfHighlightsFromPage,
  updateActiveHighlight,
  findHighlightElement,
  highlightIntersectsPage,
} from "./pdfAnchoring";

