/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for POST /highlights.
 *
 * Accepts a character-range anchor (text_start, text_end) which will be
 * validated and mapped to the richer internal anchor format by the route handler.
 *
 * Offset Semantics (v1):
 * text_start and text_end are zero-indexed positions into canonical_text
 * treated as a sequence of Unicode code points. For practical purposes,
 * treat them as Python/JS string indices.
 *
 * Attributes:
 * document_id: Typed document ID (doc_<uuid>)
 * text_start: Character offset start in canonical_text (>= 0)
 * text_end: Character offset end in canonical_text (> text_start)
 */
export type CreateHighlightRequest = {
    /**
     * Typed document ID (doc_<uuid>)
     */
    document_id: string;
    /**
     * Character offset start (>= 0)
     */
    text_start: number;
    /**
     * Character offset end (> text_start)
     */
    text_end: number;
};

