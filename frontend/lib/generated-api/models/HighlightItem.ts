/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response item for a single highlight (used in list responses).
 *
 * All IDs are typed (e.g., hl_<uuid>, doc_<uuid>).
 *
 * Attributes:
 * id: Typed highlight ID (hl_<uuid>)
 * document_id: Typed document ID (doc_<uuid>)
 * byte_start: Byte offset start in canonical_text
 * byte_end: Byte offset end in canonical_text
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
     * Byte offset start
     */
    byte_start: number;
    /**
     * Byte offset end
     */
    byte_end: number;
    /**
     * UTC timestamp of creation
     */
    created_at: string;
    /**
     * UTC timestamp of last update
     */
    updated_at?: (string | null);
};

