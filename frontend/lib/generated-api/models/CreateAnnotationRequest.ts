/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for POST /annotations.
 *
 * Accepts exactly one of highlight_id.
 *
 * Attributes:
 * highlight_id: Optional typed highlight ID (hl_<uuid>)
 * content: The annotation text (required, non-empty after stripping)
 */
export type CreateAnnotationRequest = {
  /**
   * Typed highlight ID (hl_<uuid>)
   */
  highlight_id?: string | null;
  /**
   * Annotation text content (required, non-empty)
   */
  content: string;
};
