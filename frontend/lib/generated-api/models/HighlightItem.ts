/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response item for a single highlight (used in list responses).
 *
 * All IDs are typed (e.g., hl_<uuid>, doc_<uuid>).
 *
 * Offset Semantics (v1):
 * text_start and text_end are zero-indexed positions into canonical_text
 * treated as a sequence of Unicode code points. For practical purposes,
 * treat them as Python/JS string indices.
 *
 * Attributes:
 * id: Typed highlight ID (hl_<uuid>)
 * document_id: Typed document ID (doc_<uuid>)
 * text_start: Character offset start in canonical_text (codepoint index)
 * text_end: Character offset end in canonical_text (codepoint index)
 * quote: The exact text at [text_start:text_end]
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
     * UTC timestamp of creation
     */
    created_at: string;
    /**
     * UTC timestamp of last update
     */
    updated_at?: (string | null);
};

