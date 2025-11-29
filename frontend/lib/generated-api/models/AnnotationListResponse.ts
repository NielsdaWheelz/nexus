/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnnotationItem } from './AnnotationItem';
/**
 * API response for list annotations endpoints (with pagination).
 *
 * Attributes:
 * items: List of AnnotationItem objects
 * next_cursor: Opaque cursor for next page, or null if at end
 * has_more: True if more pages exist, False otherwise
 */
export type AnnotationListResponse = {
    /**
     * List of annotations
     */
    items: Array<AnnotationItem>;
    /**
     * Cursor for next page
     */
    next_cursor?: (string | null);
    /**
     * Whether more items exist
     */
    has_more: boolean;
};

