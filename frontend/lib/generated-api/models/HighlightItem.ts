/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response item for a single highlight (used in list responses).
 *
 * All IDs are typed (e.g., hl_<uuid>, doc_<uuid>).
 *
 * Offset Semantics:
 * text_start and text_end are zero-indexed positions into canonical_text
 * treated as a sequence of Unicode code points. For practical purposes,
 * treat them as Python/JS string indices. This keeps frontend/backend
 * semantically aligned without byte↔codepoint mapping.
 *
 * For PDF anchors (anchor_type="pdf"), the primary anchoring coordinates are
 * pdf_page_number and pdf_char_offset, NOT text_start/text_end. The frontend
 * should use the PDF-specific fields for rendering PDF highlights.
 *
 * Attributes:
 * id: Typed highlight ID (hl_<uuid>)
 * document_id: Typed document ID (doc_<uuid>)
 * anchor_type: Type of anchor (text, pdf, transcript)
 * text_start: Character offset start in canonical_text (codepoint index)
 * text_end: Character offset end in canonical_text (codepoint index)
 * quote: The exact text at [text_start:text_end]
 * color: Highlight color (yellow, blue, green, pink, purple)
 * pdf_page_number: PDF page number (1-based, only for anchor_type="pdf")
 * pdf_char_offset: Character offset within the page (only for anchor_type="pdf")
 * created_at: UTC timestamp of creation
 * updated_at: UTC timestamp of last update
 */
export type HighlightItem = {
    /**
     * Typed highlight ID (hl_<uuid>)
     */
    id: string;
    /**
     * Typed document ID (doc_<uuid>)
     */
    document_id: string;
    /**
     * Type of anchor
     */
    anchor_type: HighlightItem.anchor_type;
    /**
     * Character offset start (codepoint index)
     */
    text_start: number;
    /**
     * Character offset end (codepoint index)
     */
    text_end: number;
    /**
     * The highlighted text at [text_start:text_end]
     */
    quote: string;
    /**
     * Highlight color (yellow, blue, green, pink, purple)
     */
    color: string;
    /**
     * PDF page number (1-based, PDF anchors only)
     */
    pdf_page_number?: (number | null);
    /**
     * Character offset within page (PDF anchors only)
     */
    pdf_char_offset?: (number | null);
    /**
     * UTC timestamp of creation
     */
    created_at: string;
    /**
     * UTC timestamp of last update
     */
    updated_at?: (string | null);
};
export namespace HighlightItem {
    /**
     * Type of anchor
     */
    export enum anchor_type {
        TEXT = 'text',
        PDF = 'pdf',
        TRANSCRIPT = 'transcript',
    }
}

