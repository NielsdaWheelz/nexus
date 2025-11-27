/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for POST /annotations.
 *
 * Accepts exactly one of highlight_id or chunk_id (mutually exclusive).
 *
 * Attributes:
 * highlight_id: Optional typed highlight ID (hl_<uuid>)
 * chunk_id: Optional typed chunk ID (chunk_<uuid>)
 * content: The annotation text (required, non-empty after stripping)
 */
export type CreateAnnotationRequest = {
  /**
   * Typed highlight ID (hl_<uuid>), mutually exclusive with chunk_id
   */
  highlight_id?: string | null;
  /**
   * Typed chunk ID (chunk_<uuid>), mutually exclusive with highlight_id
   */
  chunk_id?: string | null;
  /**
   * Annotation text content (required, non-empty)
   */
  content: string;
};
