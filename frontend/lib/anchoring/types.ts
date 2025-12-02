/**
 * Anchoring Types
 *
 * Core type definitions for the anchoring module, which maps between
 * canonical text offsets and reader-specific anchors (prefix/quote/suffix).
 *
 * IMPORTANT: String Index vs Byte Offset Limitation
 * -------------------------------------------------
 * The backend uses byte offsets into UTF-8 encoded canonical text.
 * This frontend module uses JavaScript string indices (UTF-16 code units).
 *
 * For ASCII-only and most Latin/English text, these are equivalent.
 * For text with multi-byte UTF-8 characters (e.g., emoji, CJK), they differ.
 *
 * In v1, we assume English-only content where this distinction is irrelevant.
 * Future versions may need to convert between the two coordinate systems.
 */

/**
 * Status of an anchor placement attempt.
 * - 'attached': Quote was successfully located in canonical text
 * - 'detached': Quote could not be reliably located
 */
export type AnchorStatus = "attached" | "detached";

/**
 * The prefix/quote/suffix triple used for disambiguation.
 * These are the context strings stored alongside offset anchors.
 */
export interface AnchorTriple {
  /** Text immediately before the quote (up to ~64 chars) */
  prefix: string;
  /** The exact highlighted text */
  quote: string;
  /** Text immediately after the quote (up to ~64 chars) */
  suffix: string;
}

/**
 * Input for anchor placement operations.
 * Contains the original anchor triple plus the offsets recorded at creation time.
 */
export interface CanonicalAnchorInput extends AnchorTriple {
  /**
   * Original starting index in canonicalText (inclusive).
   * This was correct when the highlight was first created.
   */
  start: number;
  /**
   * Original ending index in canonicalText (exclusive).
   * This was correct when the highlight was first created.
   */
  end: number;
}

/**
 * Result of an anchor placement operation.
 * Indicates whether the anchor was successfully placed and at what offsets.
 */
export interface AnchorResolution {
  /** Whether the anchor was successfully placed */
  status: AnchorStatus;
  /**
   * New starting index (inclusive).
   * Present only when status === 'attached'.
   */
  start?: number;
  /**
   * New ending index (exclusive).
   * Present only when status === 'attached'.
   */
  end?: number;
  /**
   * Diagnostic information about the resolution process.
   * Useful for logging, debugging, and tests.
   * Examples: "unique_match", "disambiguated_by_prefix", "no_occurrences"
   */
  reason?: string;
}

/**
 * Context for resolving a reader selection to canonical offsets.
 */
export interface SelectionContext {
  /** The full canonical text of the document */
  canonicalText: string;
  /** The text the user selected in the reader */
  selectionText: string;
  /**
   * Optional hint: approximate starting index in canonicalText.
   * Can come from reader scroll position, DOM range mapping, etc.
   * Used to prefer nearby matches when multiple exist.
   */
  approximateStart?: number;
}

/**
 * Result of mapping a reader selection to canonical offsets.
 */
export interface SelectionResolution {
  /** Whether the selection was successfully mapped */
  status: "resolved" | "unresolved";
  /**
   * Starting index in canonicalText (inclusive).
   * Present only when status === 'resolved'.
   */
  start?: number;
  /**
   * Ending index in canonicalText (exclusive).
   * Present only when status === 'resolved'.
   */
  end?: number;
  /**
   * Diagnostic information about the resolution process.
   * Useful for logging, debugging, and tests.
   */
  reason?: string;
}

