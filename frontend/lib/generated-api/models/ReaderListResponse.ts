/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ReaderResponse } from './ReaderResponse';
/**
 * API response for listing readers with pagination.
 *
 * Returns a paginated list of readers for a document.
 *
 * Attributes:
 * items: List of ReaderResponse objects
 * next_cursor: Cursor for next page (None if no more results)
 * has_more: Boolean indicating if more results available
 */
export type ReaderListResponse = {
    /**
     * List of readers
     */
    items: Array<ReaderResponse>;
    /**
     * Cursor for next page
     */
    next_cursor?: (string | null);
    /**
     * Whether more results are available
     */
    has_more: boolean;
};

