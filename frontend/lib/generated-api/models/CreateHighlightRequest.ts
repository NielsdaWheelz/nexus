/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for POST /highlights.
 *
 * Generic highlight creation endpoint supporting multiple media types and anchor types.
 * For v1, only media_type="document" with anchor_type="text" is supported.
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
 * media_type: Type of media to highlight ("document" only for v1)
 * media_id: Typed media ID (e.g., doc_<uuid> for documents)
 * anchor_type: Type of anchor ("text" only for html/epub in v1)
 * text_start: Character offset start in canonical_text (>= 0)
 * text_end: Character offset end in canonical_text (> text_start)
 */
export type CreateHighlightRequest = {
    /**
     * Type of media to highlight (only 'document' supported in v1)
     */
    media_type: string;
    /**
     * Typed media ID (e.g., doc_<uuid> for documents)
     */
    media_id: string;
    /**
     * Type of anchor (only 'text' supported for html/epub in v1)
     */
    anchor_type: string;
    /**
     * Character offset start (>= 0)
     */
    text_start: number;
    /**
     * Character offset end (> text_start)
     */
    text_end: number;
};

