/**
 * Highlight sorting utilities for inspector display.
 *
 * Provides a deterministic, spec-consistent sort order for highlights
 * regardless of anchor type (text or pdf).
 *
 * ORDERING SEMANTICS (see spec/anchors.md):
 *
 * For anchor_type="text":
 *   - Primary: text_start ascending
 *   - Secondary: text_end ascending (shorter spans first for same start)
 *   - Tertiary: id ascending (deterministic tiebreaker)
 *
 * For anchor_type="pdf":
 *   - Primary: pdf_page_number ascending
 *   - Secondary: pdf_char_offset ascending
 *   - Tertiary: id ascending (deterministic tiebreaker)
 *
 * When mixing text and pdf anchors in a single list:
 *   - Text anchors (canonical) appear before PDF anchors
 *   - This matches the conceptual model where canonical text is
 *     the normalized representation, and PDF is a format-specific view
 *   - Within each category, ordering follows the rules above
 *
 * For transcript anchors (future): would follow similar logic with
 * time_start as primary sort key.
 */

import type { HighlightItem } from "@/lib/generated-api";

/**
 * Sort key tuple for deterministic highlight ordering.
 *
 * Structure: [anchorTypeOrdinal, primaryPosition, secondaryPosition, id]
 *
 * - anchorTypeOrdinal: 0 for text, 1 for pdf, 2 for transcript
 * - primaryPosition: text_start for text, pdf_page_number for pdf
 * - secondaryPosition: text_end for text, pdf_char_offset for pdf
 * - id: stable tiebreaker
 */
export type HighlightSortKey = [number, number, number, string];

/**
 * Get sort key for a highlight.
 *
 * The key is a tuple that can be compared lexicographically for
 * deterministic ordering.
 *
 * @param highlight - The highlight to generate a sort key for
 * @returns Sort key tuple [anchorTypeOrdinal, primary, secondary, id]
 */
export function getHighlightSortKey(highlight: HighlightItem): HighlightSortKey {
  const { anchor_type, text_start, text_end, pdf_page_number, pdf_char_offset, id } = highlight;

  switch (anchor_type) {
    case "text":
      // Text anchors: sort by text_start, then text_end
      // If text_start is missing/null (data bug), treat as Infinity (sort to end)
      return [
        0, // Text anchors come first
        text_start ?? Number.MAX_SAFE_INTEGER,
        text_end ?? Number.MAX_SAFE_INTEGER,
        id,
      ];

    case "pdf":
      // PDF anchors: sort by page number, then char offset within page
      // If fields are null (data bug), treat as Infinity (sort to end)
      return [
        1, // PDF anchors come after text anchors
        pdf_page_number ?? Number.MAX_SAFE_INTEGER,
        pdf_char_offset ?? Number.MAX_SAFE_INTEGER,
        id,
      ];

    case "transcript":
      // Transcript anchors: sort by text_start (time_start not available in HighlightItem)
      // If text_start is missing/null (data bug), treat as Infinity (sort to end)
      return [
        2, // Transcript anchors come last
        text_start ?? Number.MAX_SAFE_INTEGER,
        text_end ?? Number.MAX_SAFE_INTEGER,
        id,
      ];

    default:
      // Unknown anchor type: sort to end with id as tiebreaker
      return [999, Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER, id];
  }
}

/**
 * Compare two sort keys lexicographically.
 *
 * @param a - First sort key
 * @param b - Second sort key
 * @returns Negative if a < b, positive if a > b, 0 if equal
 */
function compareSortKeys(a: HighlightSortKey, b: HighlightSortKey): number {
  // Compare each element in order
  for (let i = 0; i < 4; i++) {
    const aVal = a[i];
    const bVal = b[i];

    if (aVal < bVal) return -1;
    if (aVal > bVal) return 1;
  }
  return 0;
}

/**
 * Sort highlights by document position.
 *
 * Returns a new array with highlights sorted in document order.
 * The original array is not mutated.
 *
 * @param highlights - Array of highlights to sort
 * @returns New array with highlights in sorted order
 *
 * @example
 * ```ts
 * const sorted = sortHighlights(highlights);
 * // sorted[0] is the first highlight in the document
 * // sorted[n-1] is the last highlight in the document
 * ```
 */
export function sortHighlights(highlights: HighlightItem[]): HighlightItem[] {
  return [...highlights].sort((a, b) => {
    const keyA = getHighlightSortKey(a);
    const keyB = getHighlightSortKey(b);
    return compareSortKeys(keyA, keyB);
  });
}

