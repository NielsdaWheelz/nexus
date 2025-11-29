/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for PATCH /annotations/{annotation_id}.
 *
 * Attributes:
 * content: The updated annotation text (required, non-empty)
 */
export type UpdateAnnotationRequest = {
    /**
     * Annotation text content (required, non-empty)
     */
    content: string;
};

