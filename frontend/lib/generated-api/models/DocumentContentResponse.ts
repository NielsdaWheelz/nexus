/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response for GET /documents/{id}/content.
 *
 * Returns the canonical text content of a document for rendering.
 * This endpoint returns the full canonical text without pagination.
 *
 * Note: For large documents (>5MB), expect response times of 1-3s.
 * Streaming or range requests are deferred to v2.
 *
 * Attributes:
 * canonical_text: The full canonical text content (UTF-8)
 * canonical_hash: SHA256 hash of canonical_text
 * anchored_content_hash: Hash at time of most recent highlight creation (may be null)
 * source_kind: Type of source (pdf, epub, html)
 * text_length: Length of canonical_text in characters (codepoints)
 */
export type DocumentContentResponse = {
    /**
     * Full canonical text content
     */
    canonical_text: string;
    /**
     * SHA256 of canonical_text
     */
    canonical_hash: string;
    /**
     * Hash at time of highlight creation
     */
    anchored_content_hash?: (string | null);
    /**
     * Type of source document
     */
    source_kind: 'pdf' | 'epub' | 'html';
    /**
     * Length of canonical_text in characters
     */
    text_length: number;
};

