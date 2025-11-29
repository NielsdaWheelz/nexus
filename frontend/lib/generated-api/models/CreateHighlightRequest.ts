/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for POST /highlights.
 *
 * Accepts a simple byte-range anchor (text_start, text_end) which will be
 * validated and mapped to the richer internal anchor format by the route handler.
 *
 * Attributes:
 * document_id: Typed document ID (doc_<uuid>)
 * byte_start: Byte offset start in canonical_text (>= 0)
 * byte_end: Byte offset end in canonical_text (> byte_start)
 */
export type CreateHighlightRequest = {
    /**
     * Typed document ID (doc_<uuid>)
     */
    document_id: string;
    /**
     * Byte offset start (>= 0)
     */
    byte_start: number;
    /**
     * Byte offset end (> byte_start)
     */
    byte_end: number;
};

