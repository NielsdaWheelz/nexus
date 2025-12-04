import { describe, test, expect } from "vitest";
import { sortHighlights, getHighlightSortKey } from "../sort";
import type { HighlightItem } from "@/lib/generated-api";

/**
 * Helper to create mock highlights for testing.
 */
function createHighlight(
  id: string,
  options: {
    anchor_type?: "text" | "pdf" | "transcript";
    text_start?: number;
    text_end?: number;
    pdf_page_number?: number | null;
    pdf_char_offset?: number | null;
  } = {}
): HighlightItem {
  const anchorType = options.anchor_type ?? "text";
  return {
    id,
    document_id: "doc_test",
    anchor_type: anchorType,
    text_start: options.text_start ?? 0,
    text_end: options.text_end ?? 10,
    quote: "test quote",
    color: "yellow",
    pdf_page_number: options.pdf_page_number ?? null,
    pdf_char_offset: options.pdf_char_offset ?? null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  };
}

describe("getHighlightSortKey", () => {
  describe("text anchors", () => {
    test("returns correct key for text anchor", () => {
      const highlight = createHighlight("hl_1", {
        anchor_type: "text",
        text_start: 100,
        text_end: 150,
      });

      const key = getHighlightSortKey(highlight);

      expect(key[0]).toBe(0); // text anchor ordinal
      expect(key[1]).toBe(100); // text_start
      expect(key[2]).toBe(150); // text_end
      expect(key[3]).toBe("hl_1"); // id
    });

    test("handles null text_start as MAX_SAFE_INTEGER", () => {
      const highlight = createHighlight("hl_1", {
        anchor_type: "text",
        text_start: undefined as unknown as number,
        text_end: 100,
      });
      // Force null for testing edge case
      (highlight as { text_start: number | null }).text_start = null as unknown as number;

      const key = getHighlightSortKey(highlight);

      expect(key[1]).toBe(Number.MAX_SAFE_INTEGER);
    });
  });

  describe("pdf anchors", () => {
    test("returns correct key for pdf anchor", () => {
      const highlight = createHighlight("hl_2", {
        anchor_type: "pdf",
        pdf_page_number: 5,
        pdf_char_offset: 200,
      });

      const key = getHighlightSortKey(highlight);

      expect(key[0]).toBe(1); // pdf anchor ordinal
      expect(key[1]).toBe(5); // pdf_page_number
      expect(key[2]).toBe(200); // pdf_char_offset
      expect(key[3]).toBe("hl_2"); // id
    });

    test("handles null pdf_page_number as MAX_SAFE_INTEGER", () => {
      const highlight = createHighlight("hl_1", {
        anchor_type: "pdf",
        pdf_page_number: null,
        pdf_char_offset: 100,
      });

      const key = getHighlightSortKey(highlight);

      expect(key[1]).toBe(Number.MAX_SAFE_INTEGER);
    });

    test("handles null pdf_char_offset as MAX_SAFE_INTEGER", () => {
      const highlight = createHighlight("hl_1", {
        anchor_type: "pdf",
        pdf_page_number: 1,
        pdf_char_offset: null,
      });

      const key = getHighlightSortKey(highlight);

      expect(key[2]).toBe(Number.MAX_SAFE_INTEGER);
    });
  });

  describe("transcript anchors", () => {
    test("returns correct key for transcript anchor", () => {
      const highlight = createHighlight("hl_3", {
        anchor_type: "transcript",
        text_start: 500,
        text_end: 600,
      });

      const key = getHighlightSortKey(highlight);

      expect(key[0]).toBe(2); // transcript anchor ordinal
      expect(key[1]).toBe(500); // text_start
      expect(key[2]).toBe(600); // text_end
      expect(key[3]).toBe("hl_3"); // id
    });
  });
});

describe("sortHighlights", () => {
  describe("pure text anchors", () => {
    test("sorts by text_start ascending", () => {
      const highlights = [
        createHighlight("hl_3", { text_start: 300, text_end: 350 }),
        createHighlight("hl_1", { text_start: 100, text_end: 150 }),
        createHighlight("hl_2", { text_start: 200, text_end: 250 }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_1", "hl_2", "hl_3"]);
    });

    test("uses text_end as secondary sort key when text_start is equal", () => {
      const highlights = [
        createHighlight("hl_2", { text_start: 100, text_end: 200 }),
        createHighlight("hl_1", { text_start: 100, text_end: 150 }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_1", "hl_2"]);
    });

    test("uses id as tertiary tiebreaker", () => {
      const highlights = [
        createHighlight("hl_b", { text_start: 100, text_end: 150 }),
        createHighlight("hl_a", { text_start: 100, text_end: 150 }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_a", "hl_b"]);
    });

    test("does not mutate original array", () => {
      const highlights = [
        createHighlight("hl_2", { text_start: 200, text_end: 250 }),
        createHighlight("hl_1", { text_start: 100, text_end: 150 }),
      ];

      const sorted = sortHighlights(highlights);

      expect(highlights[0].id).toBe("hl_2"); // original unchanged
      expect(sorted[0].id).toBe("hl_1"); // sorted is different
      expect(sorted).not.toBe(highlights); // new array
    });
  });

  describe("pure pdf anchors", () => {
    test("sorts by pdf_page_number ascending", () => {
      const highlights = [
        createHighlight("hl_3", {
          anchor_type: "pdf",
          pdf_page_number: 10,
          pdf_char_offset: 0,
        }),
        createHighlight("hl_1", {
          anchor_type: "pdf",
          pdf_page_number: 1,
          pdf_char_offset: 0,
        }),
        createHighlight("hl_2", {
          anchor_type: "pdf",
          pdf_page_number: 5,
          pdf_char_offset: 0,
        }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_1", "hl_2", "hl_3"]);
    });

    test("uses pdf_char_offset as secondary sort key when page is equal", () => {
      const highlights = [
        createHighlight("hl_2", {
          anchor_type: "pdf",
          pdf_page_number: 1,
          pdf_char_offset: 500,
        }),
        createHighlight("hl_1", {
          anchor_type: "pdf",
          pdf_page_number: 1,
          pdf_char_offset: 100,
        }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_1", "hl_2"]);
    });
  });

  describe("mixed anchor types", () => {
    test("text anchors appear before pdf anchors", () => {
      const highlights = [
        createHighlight("hl_pdf", {
          anchor_type: "pdf",
          pdf_page_number: 1,
          pdf_char_offset: 0,
        }),
        createHighlight("hl_text", {
          anchor_type: "text",
          text_start: 100,
          text_end: 150,
        }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_text", "hl_pdf"]);
    });

    test("text anchors appear before transcript anchors", () => {
      const highlights = [
        createHighlight("hl_transcript", {
          anchor_type: "transcript",
          text_start: 100,
          text_end: 150,
        }),
        createHighlight("hl_text", {
          anchor_type: "text",
          text_start: 100,
          text_end: 150,
        }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_text", "hl_transcript"]);
    });

    test("pdf anchors appear before transcript anchors", () => {
      const highlights = [
        createHighlight("hl_transcript", {
          anchor_type: "transcript",
          text_start: 100,
          text_end: 150,
        }),
        createHighlight("hl_pdf", {
          anchor_type: "pdf",
          pdf_page_number: 1,
          pdf_char_offset: 0,
        }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_pdf", "hl_transcript"]);
    });

    test("preserves position ordering within each anchor type in mixed list", () => {
      const highlights = [
        createHighlight("hl_pdf_2", {
          anchor_type: "pdf",
          pdf_page_number: 5,
          pdf_char_offset: 0,
        }),
        createHighlight("hl_text_2", {
          anchor_type: "text",
          text_start: 500,
          text_end: 550,
        }),
        createHighlight("hl_pdf_1", {
          anchor_type: "pdf",
          pdf_page_number: 1,
          pdf_char_offset: 0,
        }),
        createHighlight("hl_text_1", {
          anchor_type: "text",
          text_start: 100,
          text_end: 150,
        }),
      ];

      const sorted = sortHighlights(highlights);

      // Text anchors first (sorted by text_start), then PDF (sorted by page)
      expect(sorted.map((h) => h.id)).toEqual([
        "hl_text_1",
        "hl_text_2",
        "hl_pdf_1",
        "hl_pdf_2",
      ]);
    });
  });

  describe("edge cases", () => {
    test("handles empty array", () => {
      const sorted = sortHighlights([]);
      expect(sorted).toEqual([]);
    });

    test("handles single element", () => {
      const highlights = [createHighlight("hl_1", { text_start: 100, text_end: 150 })];
      const sorted = sortHighlights(highlights);
      expect(sorted).toEqual(highlights);
    });

    test("already sorted array remains stable", () => {
      const highlights = [
        createHighlight("hl_1", { text_start: 100, text_end: 150 }),
        createHighlight("hl_2", { text_start: 200, text_end: 250 }),
        createHighlight("hl_3", { text_start: 300, text_end: 350 }),
      ];

      const sorted = sortHighlights(highlights);

      expect(sorted.map((h) => h.id)).toEqual(["hl_1", "hl_2", "hl_3"]);
    });
  });
});

