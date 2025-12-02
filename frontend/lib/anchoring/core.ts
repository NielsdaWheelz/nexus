/**
 * Anchoring Core Module
 *
 * This module provides pure functions for mapping between canonical text
 * offsets and reader-specific anchors. It handles:
 *
 * 1. Re-locating highlights when canonical text changes (findBestAnchorPlacement)
 * 2. Remapping anchors after document updates (remapAnchorAfterCanonicalChange)
 * 3. Converting reader selections to canonical offsets (resolveSelectionToCanonicalOffsets)
 *
 * DESIGN PRINCIPLES
 * -----------------
 * - Pure functions: no side effects, no global state, no randomness
 * - Deterministic: same inputs always produce same outputs
 * - Defensive: never throws on malformed input, always returns a resolution
 * - No external dependencies: uses only built-in string/array operations
 *
 * SCORING ALGORITHM (for disambiguation)
 * --------------------------------------
 * When multiple occurrences of a quote exist in canonical text, we score
 * each candidate and pick the best one. The scoring rules are:
 *
 * 1. Context Match Score (0.0 - 1.0 each for prefix and suffix):
 *    - Compare anchor's stored prefix/suffix with candidate's surrounding text
 *    - Use normalized Levenshtein similarity (1 - editDistance/maxLen)
 *    - Prefix and suffix scores are weighted equally
 *
 * 2. Position Proximity Score (0.0 - 1.0):
 *    - Prefer candidates near the original start position
 *    - Score = 1 / (1 + distance / canonicalLength)
 *    - Small positional bonus to break ties
 *
 * 3. Total Score:
 *    - contextScore = (prefixScore + suffixScore) / 2
 *    - total = contextScore * 0.9 + positionScore * 0.1
 *
 * 4. Tie-Breaking:
 *    - If two candidates have identical scores, pick the one with lower index
 *    - This ensures determinism
 *
 * CONFIGURATION (see constants below)
 * ------------------------------------
 * - CONTEXT_WINDOW_SIZE: max chars of prefix/suffix to compare (64)
 * - MIN_CONTEXT_SCORE: minimum similarity to attach (0.3)
 * - CONTEXT_SCORE_WEIGHT: weight for context similarity (0.9)
 * - POSITION_SCORE_WEIGHT: weight for position proximity (0.1)
 *
 * STRING INDEX vs BYTE OFFSET
 * ---------------------------
 * This module uses JavaScript string indices (UTF-16 code units).
 * The backend uses byte offsets (UTF-8).
 * For English text, these are equivalent.
 * For multi-byte characters, conversion is needed (not implemented in v1).
 */

import type {
  CanonicalAnchorInput,
  AnchorResolution,
  SelectionContext,
  SelectionResolution,
} from "./types";

// ---------------------------------------------------------------------------
// Internal Helper: Find All Occurrences
// ---------------------------------------------------------------------------

/**
 * Find all starting indices where `needle` appears in `haystack`.
 * Returns empty array if needle is empty.
 */
function findAllOccurrences(haystack: string, needle: string): number[] {
  if (needle.length === 0) {
    return [];
  }

  const indices: number[] = [];
  let pos = 0;

  while (true) {
    const found = haystack.indexOf(needle, pos);
    if (found === -1) break;
    indices.push(found);
    pos = found + 1; // Allow overlapping matches
  }

  return indices;
}

// ---------------------------------------------------------------------------
// Internal Helper: Levenshtein Distance
// ---------------------------------------------------------------------------

/**
 * Compute the Levenshtein edit distance between two strings.
 * Uses the classic dynamic programming algorithm.
 * Time: O(n*m), Space: O(min(n,m))
 */
function levenshteinDistance(a: string, b: string): number {
  // Optimize: if one string is empty, distance is length of the other
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;

  // Ensure a is the shorter string to optimize space
  if (a.length > b.length) {
    [a, b] = [b, a];
  }

  // Only keep two rows of the DP matrix
  let prevRow = new Array(a.length + 1);
  let currRow = new Array(a.length + 1);

  // Initialize first row
  for (let i = 0; i <= a.length; i++) {
    prevRow[i] = i;
  }

  for (let j = 1; j <= b.length; j++) {
    currRow[0] = j;

    for (let i = 1; i <= a.length; i++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      currRow[i] = Math.min(
        currRow[i - 1] + 1, // insertion
        prevRow[i] + 1, // deletion
        prevRow[i - 1] + cost // substitution
      );
    }

    // Swap rows
    [prevRow, currRow] = [currRow, prevRow];
  }

  return prevRow[a.length];
}

/**
 * Compute normalized Levenshtein similarity (0.0 - 1.0).
 * 1.0 means identical, 0.0 means completely different.
 */
function levenshteinSimilarity(a: string, b: string): number {
  if (a.length === 0 && b.length === 0) return 1.0;
  const maxLen = Math.max(a.length, b.length);
  const distance = levenshteinDistance(a, b);
  return 1 - distance / maxLen;
}

// ---------------------------------------------------------------------------
// Internal Helper: Extract Context
// ---------------------------------------------------------------------------

/**
 * Extract prefix and suffix context around a position in text.
 * Mimics the backend's 64-character context windows.
 */
function extractContext(
  text: string,
  start: number,
  end: number,
  contextLength: number = CONTEXT_WINDOW_SIZE
): { prefix: string; suffix: string } {
  const prefix = text.slice(Math.max(0, start - contextLength), start);
  const suffix = text.slice(end, Math.min(text.length, end + contextLength));
  return { prefix, suffix };
}

// ---------------------------------------------------------------------------
// Internal Helper: Score a Candidate Match
// ---------------------------------------------------------------------------

interface ScoredCandidate {
  start: number;
  end: number;
  contextScore: number;
  positionScore: number;
  totalScore: number;
}

/**
 * Score a candidate match based on context similarity and position proximity.
 */
function scoreCandidate(
  candidateStart: number,
  candidateEnd: number,
  canonicalText: string,
  anchor: CanonicalAnchorInput
): ScoredCandidate {
  // Extract context around candidate
  const { prefix: candidatePrefix, suffix: candidateSuffix } = extractContext(
    canonicalText,
    candidateStart,
    candidateEnd
  );

  // Context similarity scores
  const prefixScore = levenshteinSimilarity(anchor.prefix, candidatePrefix);
  const suffixScore = levenshteinSimilarity(anchor.suffix, candidateSuffix);
  const contextScore = (prefixScore + suffixScore) / 2;

  // Position proximity score
  // Small bonus for candidates near the original position
  const distance = Math.abs(candidateStart - anchor.start);
  const positionScore =
    canonicalText.length > 0 ? 1 / (1 + distance / canonicalText.length) : 1;

  // Combined score: context is primary, position is tie-breaker
  const totalScore =
    contextScore * CONTEXT_SCORE_WEIGHT + positionScore * POSITION_SCORE_WEIGHT;

  return {
    start: candidateStart,
    end: candidateEnd,
    contextScore,
    positionScore,
    totalScore,
  };
}

// ---------------------------------------------------------------------------
// Configuration Constants
// ---------------------------------------------------------------------------

/** Maximum chars of prefix/suffix context to extract and compare */
const CONTEXT_WINDOW_SIZE = 64;

/** Minimum context score required to attach (prevents false positives) */
const MIN_CONTEXT_SCORE = 0.3;

/** Weight given to context similarity in scoring (prefix/suffix match) */
const CONTEXT_SCORE_WEIGHT = 0.9;

/** Weight given to position proximity in scoring (nearness to original start) */
const POSITION_SCORE_WEIGHT = 0.1;

// ---------------------------------------------------------------------------
// Main Export: findBestAnchorPlacement
// ---------------------------------------------------------------------------

/**
 * Find the best placement for an anchor in the current canonical text.
 *
 * Given an anchor with (prefix, quote, suffix, start, end) that was created
 * for some original version of canonical text, this function attempts to
 * re-locate that anchor in the current canonical text.
 *
 * Algorithm:
 * 1. Find all exact occurrences of the quote
 * 2. If exactly one: attach to it
 * 3. If multiple: score each by context similarity + position proximity
 * 4. If none: return detached (fuzzy matching not implemented in v1)
 *
 * @param canonicalText - The current canonical text
 * @param anchor - The anchor to place (prefix, quote, suffix, original start/end)
 * @returns Resolution with status and new offsets (if attached)
 */
export function findBestAnchorPlacement(
  canonicalText: string,
  anchor: CanonicalAnchorInput
): AnchorResolution {
  // Edge case: empty quote
  if (anchor.quote.length === 0) {
    return {
      status: "detached",
      reason: "empty_quote",
    };
  }

  // Find all occurrences of the quote
  const occurrences = findAllOccurrences(canonicalText, anchor.quote);

  // No occurrences: detached
  if (occurrences.length === 0) {
    return {
      status: "detached",
      reason: "no_occurrences",
    };
  }

  // Single occurrence: attach directly
  if (occurrences.length === 1) {
    const start = occurrences[0];
    const end = start + anchor.quote.length;
    return {
      status: "attached",
      start,
      end,
      reason: "unique_match",
    };
  }

  // Multiple occurrences: score each candidate
  const scoredCandidates = occurrences.map((start) => {
    const end = start + anchor.quote.length;
    return scoreCandidate(start, end, canonicalText, anchor);
  });

  // Sort by total score descending, then by start index ascending (tie-breaker)
  scoredCandidates.sort((a, b) => {
    if (b.totalScore !== a.totalScore) {
      return b.totalScore - a.totalScore;
    }
    return a.start - b.start;
  });

  const best = scoredCandidates[0];

  // Check if the best candidate meets minimum threshold
  if (best.contextScore < MIN_CONTEXT_SCORE) {
    return {
      status: "detached",
      reason: `best_candidate_below_threshold:${best.contextScore.toFixed(3)}`,
    };
  }

  return {
    status: "attached",
    start: best.start,
    end: best.end,
    reason: `disambiguated:${scoredCandidates.length}_candidates:score=${best.totalScore.toFixed(3)}`,
  };
}

// ---------------------------------------------------------------------------
// Main Export: remapAnchorAfterCanonicalChange
// ---------------------------------------------------------------------------

/**
 * Remap an anchor from old canonical text to new canonical text.
 *
 * This function is called when a document's canonical text changes and we
 * need to update highlight positions. In v1, we don't use the old canonical
 * text directly—instead, we rely on the stored prefix/quote/suffix and the
 * original start position as a proximity hint.
 *
 * Note: In a more sophisticated implementation, we could diff the old and new
 * text to compute position shifts. For v1, we simply re-find the best match.
 *
 * @param oldCanonicalText - The previous canonical text (used for position hints only)
 * @param newCanonicalText - The current canonical text
 * @param anchor - The anchor to remap
 * @returns Resolution with status and new offsets (if attached)
 */
export function remapAnchorAfterCanonicalChange(
  oldCanonicalText: string,
  newCanonicalText: string,
  anchor: CanonicalAnchorInput
): AnchorResolution {
  // In v1, we don't diff old vs new text.
  // We rely on prefix/quote/suffix to find the best match.
  // The original start position provides a weak positional hint via scoring.
  //
  // Future enhancement: compute relative position in old text and use that
  // to bias toward similar relative position in new text.

  const resolution = findBestAnchorPlacement(newCanonicalText, anchor);

  // Add note that we're doing a remap (for debugging/logging)
  if (resolution.reason) {
    resolution.reason = `remap:${resolution.reason}`;
  }

  return resolution;
}

// ---------------------------------------------------------------------------
// Main Export: resolveSelectionToCanonicalOffsets
// ---------------------------------------------------------------------------

/**
 * Resolve a reader selection to canonical text offsets.
 *
 * Given a text selection from the reader (e.g., from DOM Range.toString() or
 * pdf.js selection), find the corresponding [start, end) offsets in the
 * canonical text.
 *
 * Algorithm:
 * 1. Trim whitespace from selection (tolerant of browser quirks)
 * 2. If empty: return unresolved
 * 3. Find all occurrences in canonical text
 * 4. If none: return unresolved
 * 5. If multiple and approximateStart provided: pick nearest
 * 6. If multiple without hint: pick first occurrence
 *
 * @param ctx - Selection context with canonical text and selection string
 * @returns Resolution with status and offsets (if resolved)
 */
export function resolveSelectionToCanonicalOffsets(
  ctx: SelectionContext
): SelectionResolution {
  // Normalize: trim whitespace from selection
  const trimmedSelection = ctx.selectionText.trim();

  // Empty or whitespace-only selection
  if (trimmedSelection.length === 0) {
    return {
      status: "unresolved",
      reason: "empty_or_whitespace_selection",
    };
  }

  // Find all occurrences
  const occurrences = findAllOccurrences(ctx.canonicalText, trimmedSelection);

  // No occurrences found
  if (occurrences.length === 0) {
    return {
      status: "unresolved",
      reason: "selection_not_found_in_canonical_text",
    };
  }

  // Single occurrence: easy case
  if (occurrences.length === 1) {
    const start = occurrences[0];
    const end = start + trimmedSelection.length;
    return {
      status: "resolved",
      start,
      end,
      reason: "unique_match",
    };
  }

  // Multiple occurrences: use approximateStart if available
  if (ctx.approximateStart !== undefined) {
    // Find the occurrence nearest to approximateStart
    let nearestIdx = 0;
    let nearestDistance = Math.abs(occurrences[0] - ctx.approximateStart);

    for (let i = 1; i < occurrences.length; i++) {
      const distance = Math.abs(occurrences[i] - ctx.approximateStart);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIdx = i;
      }
    }

    const start = occurrences[nearestIdx];
    const end = start + trimmedSelection.length;
    return {
      status: "resolved",
      start,
      end,
      reason: `nearest_to_hint:${occurrences.length}_candidates`,
    };
  }

  // Multiple occurrences, no hint: pick first (deterministic)
  const start = occurrences[0];
  const end = start + trimmedSelection.length;
  return {
    status: "resolved",
    start,
    end,
    reason: `first_of_${occurrences.length}_candidates`,
  };
}

// ---------------------------------------------------------------------------
// Utility Export: buildAnchorTriple
// ---------------------------------------------------------------------------

/**
 * Build an anchor triple (prefix, quote, suffix) from canonical text and offsets.
 * Useful when creating a new highlight.
 *
 * @param canonicalText - The full canonical text
 * @param start - Start offset (inclusive)
 * @param end - End offset (exclusive)
 * @param contextLength - Length of prefix/suffix context (default: CONTEXT_WINDOW_SIZE)
 * @returns The anchor triple
 */
export function buildAnchorTriple(
  canonicalText: string,
  start: number,
  end: number,
  contextLength: number = CONTEXT_WINDOW_SIZE
): { prefix: string; quote: string; suffix: string } {
  const quote = canonicalText.slice(start, end);
  const { prefix, suffix } = extractContext(
    canonicalText,
    start,
    end,
    contextLength
  );
  return { prefix, quote, suffix };
}

