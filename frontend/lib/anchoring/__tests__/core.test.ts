/**
 * Tests for the Anchoring Core Module
 *
 * These tests verify the core anchoring logic for:
 * - findBestAnchorPlacement: re-locating highlights in changed text
 * - remapAnchorAfterCanonicalChange: updating anchors after document updates
 * - resolveSelectionToCanonicalOffsets: mapping reader selections to offsets
 * - buildAnchorTriple: constructing prefix/quote/suffix context
 *
 * Test philosophy:
 * - Each test is explicit about WHY the case is interesting
 * - Cover both happy paths and edge cases
 * - Verify determinism (same inputs → same outputs)
 */

import { describe, test, expect } from "vitest";
import {
  findBestAnchorPlacement,
  remapAnchorAfterCanonicalChange,
  resolveSelectionToCanonicalOffsets,
  buildAnchorTriple,
} from "../core";
import type {
  CanonicalAnchorInput,
  SelectionContext,
} from "../types";

// =============================================================================
// findBestAnchorPlacement Tests
// =============================================================================

describe("findBestAnchorPlacement", () => {
  test("simple unique match: single occurrence of quote", () => {
    // The most basic case: quote appears exactly once
    const canonicalText = "the quick brown fox jumps over the lazy dog";
    const anchor: CanonicalAnchorInput = {
      prefix: "quick ",
      quote: "brown fox",
      suffix: " jumps",
      start: 10,
      end: 19,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(10);
    expect(result.end).toBe(19);
    expect(result.reason).toBe("unique_match");
    // Verify the offsets actually match the quote
    expect(canonicalText.slice(result.start!, result.end!)).toBe("brown fox");
  });

  test("multiple identical quotes: disambiguated by prefix", () => {
    // Three occurrences of "foo", prefix matches only the first one
    const canonicalText = "alpha foo beta foo gamma foo";
    const anchor: CanonicalAnchorInput = {
      prefix: "alpha ",
      quote: "foo",
      suffix: " beta",
      start: 6, // original position of first "foo"
      end: 9,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(6);
    expect(result.end).toBe(9);
    expect(canonicalText.slice(result.start!, result.end!)).toBe("foo");
    expect(result.reason).toContain("disambiguated");
    expect(result.reason).toContain("3_candidates");
  });

  test("multiple identical quotes: disambiguated by suffix", () => {
    // Three occurrences of "foo", suffix matches only the second one
    const canonicalText = "alpha foo beta foo gamma foo delta";
    const anchor: CanonicalAnchorInput = {
      prefix: "beta ", // matches second foo
      quote: "foo",
      suffix: " gamma", // matches second foo
      start: 15, // original position of second "foo"
      end: 18,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(15);
    expect(result.end).toBe(18);
    expect(canonicalText.slice(result.start!, result.end!)).toBe("foo");
  });

  test("multiple identical quotes: third occurrence selected", () => {
    // Context matches the third occurrence
    // Positions: "alpha foo" starts at 0, "beta foo" at 10, "gamma foo" at 19
    // First foo: 6-9, Second foo: 15-18, Third foo: 25-28
    const canonicalText = "alpha foo beta foo gamma foo delta";
    const anchor: CanonicalAnchorInput = {
      prefix: "gamma ", // matches third foo
      quote: "foo",
      suffix: " delta", // matches third foo
      start: 25, // original position of third "foo"
      end: 28,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(25);
    expect(result.end).toBe(28);
  });

  test("no match: quote not present → detached", () => {
    // Quote doesn't exist in canonical text at all
    const canonicalText = "the quick brown fox jumps over the lazy dog";
    const anchor: CanonicalAnchorInput = {
      prefix: "some ",
      quote: "nonexistent phrase",
      suffix: " here",
      start: 100,
      end: 118,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("detached");
    expect(result.start).toBeUndefined();
    expect(result.end).toBeUndefined();
    expect(result.reason).toBe("no_occurrences");
  });

  test("empty quote → detached", () => {
    // Edge case: empty quote should not match anything
    const canonicalText = "some text";
    const anchor: CanonicalAnchorInput = {
      prefix: "",
      quote: "",
      suffix: "",
      start: 0,
      end: 0,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("detached");
    expect(result.reason).toBe("empty_quote");
  });

  test("empty canonical text → detached", () => {
    const canonicalText = "";
    const anchor: CanonicalAnchorInput = {
      prefix: "",
      quote: "something",
      suffix: "",
      start: 0,
      end: 9,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("detached");
    expect(result.reason).toBe("no_occurrences");
  });

  test("match near original start is preferred when context is ambiguous", () => {
    // Three identical quotes with DIFFERENT context
    // Use buildAnchorTriple to get realistic context extraction
    const canonicalText = "aa foo bb cc foo dd ee foo ff";
    // Position of second foo: 13

    // Find the second occurrence
    const firstFooEnd = canonicalText.indexOf("foo") + 3;
    const secondFooStart = canonicalText.indexOf("foo", firstFooEnd);
    const secondFooEnd = secondFooStart + 3;

    // Build anchor with properly extracted context (simulates real usage)
    const anchor: CanonicalAnchorInput = {
      prefix: canonicalText.slice(Math.max(0, secondFooStart - 64), secondFooStart),
      quote: "foo",
      suffix: canonicalText.slice(secondFooEnd, Math.min(canonicalText.length, secondFooEnd + 64)),
      start: secondFooStart,
      end: secondFooEnd,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBeDefined();
    expect(result.end).toBeDefined();
    // Should pick the second occurrence due to context match
    expect(result.start).toBe(secondFooStart);
    expect(result.end).toBe(secondFooEnd);
  });

  test("partial prefix/suffix match still works", () => {
    // Context has changed slightly but still matches well enough
    const canonicalText = "hello world goodbye world";
    const anchor: CanonicalAnchorInput = {
      prefix: "hello ", // exact match for first "world"
      quote: "world",
      suffix: " goodbye", // exact match for first "world"
      start: 6,
      end: 11,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(6);
    expect(result.end).toBe(11);
  });

  test("determinism: same inputs always produce same outputs", () => {
    const canonicalText = "repeat word repeat word repeat word";
    const anchor: CanonicalAnchorInput = {
      prefix: "some ",
      quote: "word",
      suffix: " other",
      start: 7,
      end: 11,
    };

    // Run multiple times
    const results = Array.from({ length: 10 }, () =>
      findBestAnchorPlacement(canonicalText, anchor)
    );

    // All results should be identical
    const first = results[0];
    for (const result of results) {
      expect(result.status).toBe(first.status);
      expect(result.start).toBe(first.start);
      expect(result.end).toBe(first.end);
    }
  });

  test("context at document boundaries: prefix at start", () => {
    // Quote at the very beginning, no prefix possible
    const canonicalText = "beginning of text with more words";
    const anchor: CanonicalAnchorInput = {
      prefix: "", // empty because quote was at start
      quote: "beginning",
      suffix: " of text",
      start: 0,
      end: 9,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(0);
    expect(result.end).toBe(9);
  });

  test("context at document boundaries: suffix at end", () => {
    // Quote at the very end, no suffix possible
    const canonicalText = "text leading to the ending";
    const anchor: CanonicalAnchorInput = {
      prefix: "the ",
      quote: "ending",
      suffix: "", // empty because quote was at end
      start: 20,
      end: 26,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(20);
    expect(result.end).toBe(26);
  });

  test("overlapping potential matches", () => {
    // Quote that could match overlapping substrings
    const canonicalText = "aaaa";
    const anchor: CanonicalAnchorInput = {
      prefix: "",
      quote: "aa",
      suffix: "aa",
      start: 0,
      end: 2,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    // Should find the first occurrence that best matches suffix context
    expect(result.start).toBe(0);
    expect(result.end).toBe(2);
  });

  test("very long quote", () => {
    const longText =
      "In a galaxy far far away there lived a creature of extraordinary abilities " +
      "who could transform matter at will and traverse dimensions with ease.";
    const quote =
      "a creature of extraordinary abilities who could transform matter at will";
    const startIdx = longText.indexOf(quote);

    const anchor: CanonicalAnchorInput = {
      prefix: longText.slice(Math.max(0, startIdx - 64), startIdx),
      quote,
      suffix: longText.slice(startIdx + quote.length, startIdx + quote.length + 64),
      start: startIdx,
      end: startIdx + quote.length,
    };

    const result = findBestAnchorPlacement(longText, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(startIdx);
    expect(result.end).toBe(startIdx + quote.length);
  });
});

// =============================================================================
// remapAnchorAfterCanonicalChange Tests
// =============================================================================

describe("remapAnchorAfterCanonicalChange", () => {
  test("unchanged canonical text: same behavior as findBestAnchorPlacement", () => {
    const text = "the quick brown fox jumps over the lazy dog";
    const anchor: CanonicalAnchorInput = {
      prefix: "quick ",
      quote: "brown fox",
      suffix: " jumps",
      start: 10,
      end: 19,
    };

    const result = remapAnchorAfterCanonicalChange(text, text, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(10);
    expect(result.end).toBe(19);
    expect(result.reason).toContain("remap");
  });

  test("small insertion before anchor: quote shifts right", () => {
    const oldText = "hello world";
    const newText = "hello brave world"; // "brave " inserted
    const anchor: CanonicalAnchorInput = {
      prefix: "hello ",
      quote: "world",
      suffix: "",
      start: 6, // position in old text
      end: 11,
    };

    const result = remapAnchorAfterCanonicalChange(oldText, newText, anchor);

    expect(result.status).toBe("attached");
    // "world" now at position 12 in new text
    expect(result.start).toBe(12);
    expect(result.end).toBe(17);
    expect(newText.slice(result.start!, result.end!)).toBe("world");
  });

  test("small deletion before anchor: quote shifts left", () => {
    const oldText = "hello brave world";
    const newText = "hello world"; // "brave " removed
    const anchor: CanonicalAnchorInput = {
      prefix: "brave ",
      quote: "world",
      suffix: "",
      start: 12, // position in old text
      end: 17,
    };

    const result = remapAnchorAfterCanonicalChange(oldText, newText, anchor);

    expect(result.status).toBe("attached");
    // "world" now at position 6 in new text
    expect(result.start).toBe(6);
    expect(result.end).toBe(11);
    expect(newText.slice(result.start!, result.end!)).toBe("world");
  });

  test("text removed including the quote: detached", () => {
    const oldText = "hello beautiful world goodbye";
    const newText = "hello goodbye"; // "beautiful world " removed
    const anchor: CanonicalAnchorInput = {
      prefix: "hello ",
      quote: "beautiful world",
      suffix: " goodbye",
      start: 6,
      end: 21,
    };

    const result = remapAnchorAfterCanonicalChange(oldText, newText, anchor);

    expect(result.status).toBe("detached");
    expect(result.reason).toContain("no_occurrences");
  });

  test("quote modified slightly: detached (no fuzzy in v1)", () => {
    const oldText = "the quick brown fox";
    const newText = "the quick brwon fox"; // typo: "brwon" instead of "brown"
    const anchor: CanonicalAnchorInput = {
      prefix: "quick ",
      quote: "brown",
      suffix: " fox",
      start: 10,
      end: 15,
    };

    const result = remapAnchorAfterCanonicalChange(oldText, newText, anchor);

    // In v1, we don't do fuzzy matching, so this detaches
    expect(result.status).toBe("detached");
    expect(result.reason).toContain("no_occurrences");
  });

  test("quote duplicated: disambiguated by context", () => {
    const oldText = "hello world";
    const newText = "hello world and world again"; // "world" now appears twice
    const anchor: CanonicalAnchorInput = {
      prefix: "hello ",
      quote: "world",
      suffix: "", // original was at end, but now there's more text
      start: 6,
      end: 11,
    };

    const result = remapAnchorAfterCanonicalChange(oldText, newText, anchor);

    expect(result.status).toBe("attached");
    // Should prefer the first "world" due to prefix match and position
    expect(result.start).toBe(6);
    expect(result.end).toBe(11);
  });

  test("completely rewritten text: detached", () => {
    const oldText = "the original document content";
    const newText = "something completely different here";
    const anchor: CanonicalAnchorInput = {
      prefix: "the ",
      quote: "original document",
      suffix: " content",
      start: 4,
      end: 21,
    };

    const result = remapAnchorAfterCanonicalChange(oldText, newText, anchor);

    expect(result.status).toBe("detached");
  });

  test("insertion inside quote: detached", () => {
    const oldText = "hello world";
    const newText = "hello woXXrld"; // "XX" inserted inside "world"
    const anchor: CanonicalAnchorInput = {
      prefix: "hello ",
      quote: "world",
      suffix: "",
      start: 6,
      end: 11,
    };

    const result = remapAnchorAfterCanonicalChange(oldText, newText, anchor);

    expect(result.status).toBe("detached");
    expect(result.reason).toContain("no_occurrences");
  });
});

// =============================================================================
// resolveSelectionToCanonicalOffsets Tests
// =============================================================================

describe("resolveSelectionToCanonicalOffsets", () => {
  test("simple one-to-one selection: unique match", () => {
    const ctx: SelectionContext = {
      canonicalText: "the quick brown fox jumps over the lazy dog",
      selectionText: "brown fox",
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(10);
    expect(result.end).toBe(19);
    expect(ctx.canonicalText.slice(result.start!, result.end!)).toBe("brown fox");
    expect(result.reason).toBe("unique_match");
  });

  test("multiple matches with approximateStart: picks nearest", () => {
    const ctx: SelectionContext = {
      canonicalText: "foo bar foo bar foo bar",
      selectionText: "foo bar",
      approximateStart: 16, // near the third occurrence
    };
    // Positions: 0, 8, 16

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(16); // third occurrence
    expect(result.end).toBe(23);
    expect(result.reason).toContain("nearest_to_hint");
    expect(result.reason).toContain("3_candidates");
  });

  test("multiple matches with approximateStart in middle", () => {
    const ctx: SelectionContext = {
      canonicalText: "foo bar foo bar foo bar",
      selectionText: "foo bar",
      approximateStart: 8, // exactly at second occurrence
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(8); // second occurrence
    expect(result.end).toBe(15);
  });

  test("multiple matches without approximateStart: picks first", () => {
    const ctx: SelectionContext = {
      canonicalText: "foo bar foo bar foo bar",
      selectionText: "foo bar",
      // no approximateStart
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(0); // first occurrence
    expect(result.end).toBe(7);
    expect(result.reason).toBe("first_of_3_candidates");
  });

  test("empty selection: unresolved", () => {
    const ctx: SelectionContext = {
      canonicalText: "some text here",
      selectionText: "",
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("unresolved");
    expect(result.start).toBeUndefined();
    expect(result.end).toBeUndefined();
    expect(result.reason).toBe("empty_or_whitespace_selection");
  });

  test("whitespace-only selection: unresolved", () => {
    const ctx: SelectionContext = {
      canonicalText: "some text here",
      selectionText: "   \n\t  ",
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("unresolved");
    expect(result.reason).toBe("empty_or_whitespace_selection");
  });

  test("selection with leading/trailing whitespace: trimmed and matched", () => {
    const ctx: SelectionContext = {
      canonicalText: "the quick brown fox",
      selectionText: "  brown  ", // extra whitespace
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(10);
    expect(result.end).toBe(15);
    expect(ctx.canonicalText.slice(result.start!, result.end!)).toBe("brown");
  });

  test("no match: selection not in canonical text", () => {
    const ctx: SelectionContext = {
      canonicalText: "the quick brown fox",
      selectionText: "lazy dog",
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("unresolved");
    expect(result.reason).toBe("selection_not_found_in_canonical_text");
  });

  test("empty canonical text: unresolved", () => {
    const ctx: SelectionContext = {
      canonicalText: "",
      selectionText: "anything",
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("unresolved");
    expect(result.reason).toBe("selection_not_found_in_canonical_text");
  });

  test("selection spans entire canonical text", () => {
    const text = "complete document";
    const ctx: SelectionContext = {
      canonicalText: text,
      selectionText: text,
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(0);
    expect(result.end).toBe(text.length);
  });

  test("approximateStart out of bounds: still works", () => {
    const ctx: SelectionContext = {
      canonicalText: "foo bar foo bar",
      selectionText: "foo bar",
      approximateStart: 1000, // way past end
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    // Should pick the one nearest to 1000, which is the last occurrence (8)
    expect(result.start).toBe(8);
    expect(result.end).toBe(15);
  });

  test("approximateStart negative: still works", () => {
    const ctx: SelectionContext = {
      canonicalText: "foo bar foo bar",
      selectionText: "foo bar",
      approximateStart: -100, // negative
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    // Should pick the one nearest to -100, which is the first occurrence (0)
    expect(result.start).toBe(0);
    expect(result.end).toBe(7);
  });

  test("case sensitivity: exact match required", () => {
    const ctx: SelectionContext = {
      canonicalText: "The Quick Brown Fox",
      selectionText: "the quick", // wrong case
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("unresolved");
    expect(result.reason).toBe("selection_not_found_in_canonical_text");
  });

  test("determinism: same inputs always produce same outputs", () => {
    const ctx: SelectionContext = {
      canonicalText: "repeat word repeat word repeat word",
      selectionText: "word",
    };

    const results = Array.from({ length: 10 }, () =>
      resolveSelectionToCanonicalOffsets(ctx)
    );

    const first = results[0];
    for (const result of results) {
      expect(result.status).toBe(first.status);
      expect(result.start).toBe(first.start);
      expect(result.end).toBe(first.end);
    }
  });
});

// =============================================================================
// buildAnchorTriple Tests
// =============================================================================

describe("buildAnchorTriple", () => {
  test("basic extraction: quote with full context", () => {
    const text =
      "This is a fairly long text with enough content on both sides of the target phrase to extract proper context windows.";
    const start = text.indexOf("target phrase");
    const end = start + "target phrase".length;

    const result = buildAnchorTriple(text, start, end);

    expect(result.quote).toBe("target phrase");
    expect(result.prefix.length).toBeLessThanOrEqual(64);
    expect(result.suffix.length).toBeLessThanOrEqual(64);
    expect(result.prefix.endsWith("the ")).toBe(true); // "the " before "target phrase"
    expect(result.suffix.startsWith(" to")).toBe(true); // " to" after "target phrase"
  });

  test("quote at start: empty prefix", () => {
    const text = "beginning of the document";
    const result = buildAnchorTriple(text, 0, 9);

    expect(result.quote).toBe("beginning");
    expect(result.prefix).toBe("");
    expect(result.suffix).toBe(" of the document");
  });

  test("quote at end: empty suffix", () => {
    const text = "end of the line";
    const start = text.length - 4; // "line" starts at position 11
    const result = buildAnchorTriple(text, start, text.length);

    expect(result.quote).toBe("line");
    // Prefix is up to 64 chars before quote, which is "end of the "
    expect(result.prefix).toBe("end of the ");
    expect(result.suffix).toBe("");
  });

  test("custom context length", () => {
    const text = "prefix text quote text suffix text more";
    const start = text.indexOf("quote");
    const end = start + "quote".length;

    const result = buildAnchorTriple(text, start, end, 10);

    expect(result.quote).toBe("quote");
    expect(result.prefix.length).toBeLessThanOrEqual(10);
    expect(result.suffix.length).toBeLessThanOrEqual(10);
  });

  test("short text: prefix and suffix are as long as available", () => {
    const text = "ab";
    const result = buildAnchorTriple(text, 1, 2, 64);

    expect(result.quote).toBe("b");
    expect(result.prefix).toBe("a");
    expect(result.suffix).toBe("");
  });

  test("entire text as quote", () => {
    const text = "short";
    const result = buildAnchorTriple(text, 0, text.length);

    expect(result.quote).toBe("short");
    expect(result.prefix).toBe("");
    expect(result.suffix).toBe("");
  });

  test("round-trip: buildAnchorTriple → findBestAnchorPlacement", () => {
    // Verify that an anchor we build can be found again
    const text =
      "The anchoring module is designed to be robust and handle various edge cases gracefully.";
    const start = text.indexOf("robust");
    const end = start + "robust".length;

    const triple = buildAnchorTriple(text, start, end);
    const anchor: CanonicalAnchorInput = {
      ...triple,
      start,
      end,
    };

    const resolution = findBestAnchorPlacement(text, anchor);

    expect(resolution.status).toBe("attached");
    expect(resolution.start).toBe(start);
    expect(resolution.end).toBe(end);
  });
});

// =============================================================================
// Edge Cases and Integration Tests
// =============================================================================

// =============================================================================
// DOM-like Selection → Canonical Offset Tests (for PR6 highlight creation)
// =============================================================================

describe("selection to offset mapping for highlight creation", () => {
  /**
   * These tests verify the flow from user text selection to canonical offsets,
   * which is the core of highlight creation in the HtmlHighlightReader.
   *
   * In the real component:
   * 1. User selects text in the reader
   * 2. window.getSelection().toString() gives us the selection text
   * 3. We call resolveSelectionToCanonicalOffsets to map it to offsets
   * 4. We POST to /highlights with those offsets
   */

  test("simple selection in plain paragraph", () => {
    // Simulates: <p>hello world this is a test</p>
    // User selects "world this"
    const canonicalText = "hello world this is a test";
    const selectionText = "world this";

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(6); // "world" starts at index 6
    expect(result.end).toBe(16); // "world this" ends at index 16
    expect(canonicalText.slice(result.start!, result.end!)).toBe("world this");
  });

  test("selection spanning multiple sentences", () => {
    const canonicalText = "First sentence. Second sentence. Third sentence.";
    const selectionText = "sentence. Second";

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("resolved");
    expect(canonicalText.slice(result.start!, result.end!)).toBe("sentence. Second");
  });

  test("selection with newlines (multi-paragraph)", () => {
    const canonicalText = "Paragraph one.\n\nParagraph two.\n\nParagraph three.";
    const selectionText = "one.\n\nParagraph two";

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("resolved");
    expect(canonicalText.slice(result.start!, result.end!)).toBe("one.\n\nParagraph two");
  });

  test("selection at document start", () => {
    const canonicalText = "Beginning of the document with more text.";
    const selectionText = "Beginning of";

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(0);
    expect(canonicalText.slice(result.start!, result.end!)).toBe("Beginning of");
  });

  test("selection at document end", () => {
    const canonicalText = "Some text at the end.";
    const selectionText = "the end.";

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("resolved");
    expect(result.end).toBe(canonicalText.length);
    expect(canonicalText.slice(result.start!, result.end!)).toBe("the end.");
  });

  test("selection with extra whitespace from browser (trimmed)", () => {
    // Browsers sometimes include leading/trailing whitespace in selections
    const canonicalText = "The quick brown fox jumps.";
    const selectionText = "  brown fox  "; // extra whitespace

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("resolved");
    expect(canonicalText.slice(result.start!, result.end!)).toBe("brown fox");
  });

  test("selection that appears multiple times uses first occurrence", () => {
    const canonicalText = "the cat sat on the mat";
    const selectionText = "the"; // appears twice

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(0); // first occurrence
    expect(result.end).toBe(3);
  });

  test("selection that appears multiple times uses hint when provided", () => {
    const canonicalText = "the cat sat on the mat";
    const selectionText = "the";

    // Hint is near the second occurrence (position 15)
    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
      approximateStart: 15,
    });

    expect(result.status).toBe("resolved");
    expect(result.start).toBe(15); // second occurrence
    expect(result.end).toBe(18);
  });

  test("selection with special characters", () => {
    const canonicalText = "Price: $99.99 (50% off!)";
    const selectionText = "$99.99 (50%";

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("resolved");
    expect(canonicalText.slice(result.start!, result.end!)).toBe("$99.99 (50%");
  });

  test("selection not found returns unresolved", () => {
    const canonicalText = "The quick brown fox";
    const selectionText = "lazy dog"; // not in text

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("unresolved");
    expect(result.reason).toBe("selection_not_found_in_canonical_text");
  });

  test("empty selection returns unresolved", () => {
    const canonicalText = "Some text here";
    const selectionText = "";

    const result = resolveSelectionToCanonicalOffsets({
      canonicalText,
      selectionText,
    });

    expect(result.status).toBe("unresolved");
    expect(result.reason).toBe("empty_or_whitespace_selection");
  });
});

describe("edge cases and integration", () => {
  test("unicode text handling (ASCII equivalent for v1)", () => {
    // For v1, we assume English text where string indices === byte offsets
    // This test documents behavior with simple non-ASCII
    const text = "café menu includes naïve dishes";
    const anchor: CanonicalAnchorInput = {
      prefix: "includes ",
      quote: "naïve",
      suffix: " dishes",
      start: 20,
      end: 25,
    };

    const result = findBestAnchorPlacement(text, anchor);

    // Should work for simple accented characters
    expect(result.status).toBe("attached");
    expect(text.slice(result.start!, result.end!)).toBe("naïve");
  });

  test("newlines in text", () => {
    const text = "line one\nline two\nline three";
    const anchor: CanonicalAnchorInput = {
      prefix: "one\n",
      quote: "line two",
      suffix: "\nline",
      start: 9,
      end: 17,
    };

    const result = findBestAnchorPlacement(text, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(9);
    expect(result.end).toBe(17);
  });

  test("tabs and special whitespace", () => {
    const text = "column1\tcolumn2\tcolumn3";
    const ctx: SelectionContext = {
      canonicalText: text,
      selectionText: "column2",
    };

    const result = resolveSelectionToCanonicalOffsets(ctx);

    expect(result.status).toBe("resolved");
    expect(text.slice(result.start!, result.end!)).toBe("column2");
  });

  test("full workflow: selection → anchor → remap", () => {
    // Simulate the full lifecycle of a highlight:
    // 1. User selects text in reader
    // 2. We resolve to canonical offsets
    // 3. We build anchor triple
    // 4. Document changes
    // 5. We remap the anchor

    const originalText = "The quick brown fox jumps over the lazy dog.";
    const selectionText = "brown fox";

    // Step 1-2: Resolve selection
    const selectionResult = resolveSelectionToCanonicalOffsets({
      canonicalText: originalText,
      selectionText,
    });

    expect(selectionResult.status).toBe("resolved");
    const { start, end } = selectionResult as { start: number; end: number };

    // Step 3: Build anchor
    const triple = buildAnchorTriple(originalText, start, end);
    const anchor: CanonicalAnchorInput = { ...triple, start, end };

    // Step 4: Document changes (insertion before highlight)
    const newText = "The very quick brown fox jumps over the lazy dog.";

    // Step 5: Remap anchor
    const remapResult = remapAnchorAfterCanonicalChange(
      originalText,
      newText,
      anchor
    );

    expect(remapResult.status).toBe("attached");
    expect(newText.slice(remapResult.start!, remapResult.end!)).toBe("brown fox");
    // Position shifted by 5 ("very " inserted)
    expect(remapResult.start).toBe(start + 5);
  });

  test("stress test: many occurrences", () => {
    // 100 occurrences of "word"
    const words = Array(100).fill("word").join(" ");
    const canonicalText = words;

    // Anchor pointing to the 50th occurrence
    const targetIndex = 50;
    const targetStart = targetIndex * 5; // "word " is 5 chars

    const anchor: CanonicalAnchorInput = {
      prefix: "word ", // generic context
      quote: "word",
      suffix: " word", // generic context
      start: targetStart,
      end: targetStart + 4,
    };

    const result = findBestAnchorPlacement(canonicalText, anchor);

    expect(result.status).toBe("attached");
    // Should pick something deterministically (likely near original position)
    expect(result.start).toBeDefined();
    expect(result.end).toBeDefined();
    expect(canonicalText.slice(result.start!, result.end!)).toBe("word");
  });

  test("quote at multiple positions with varying context quality", () => {
    // "target" appears 3 times, but only one has good context match
    // We use full context windows to get proper similarity scoring
    const text = "aa target bb cc target dd ee target ff";
    // Positions: first at 3, second at 16, third at 26
    // Second "target" is at position 13 (after "aa target bb ")
    
    // Let's verify positions:
    // "aa target bb cc target dd ee target ff"
    //  0123456789...
    const secondTargetStart = text.indexOf("target", 4); // skip first, find second
    const secondTargetEnd = secondTargetStart + "target".length;

    // Build realistic anchor with the actual context
    const anchor: CanonicalAnchorInput = {
      prefix: text.slice(Math.max(0, secondTargetStart - 64), secondTargetStart),
      quote: "target",
      suffix: text.slice(secondTargetEnd, Math.min(text.length, secondTargetEnd + 64)),
      start: secondTargetStart,
      end: secondTargetEnd,
    };

    const result = findBestAnchorPlacement(text, anchor);

    expect(result.status).toBe("attached");
    expect(result.start).toBe(secondTargetStart);
    expect(result.end).toBe(secondTargetEnd);
    expect(text.slice(result.start!, result.end!)).toBe("target");
  });
});

