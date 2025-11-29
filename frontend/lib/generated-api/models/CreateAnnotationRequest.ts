/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for POST /annotations.
 *
 * Annotations attach only to highlights (user-selected text spans), never to chunks.
 * Chunks are purely for retrieval and embeddings; they are not annotation targets.
 *
 * Attributes:
 * highlight_id: Typed highlight ID (hl_<uuid>) (required)
 * content: The annotation text (required, non-empty after stripping)
 */
export type CreateAnnotationRequest = {
    /**
     * Typed highlight ID (hl_<uuid>) (required)
     */
    highlight_id: string;
    /**
     * Annotation text content (required, non-empty)
     */
    content: string;
};

