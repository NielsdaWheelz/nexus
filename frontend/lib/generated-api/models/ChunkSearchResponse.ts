/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ChunkSearchHit } from './ChunkSearchHit';
/**
 * Response schema for chunk similarity search.
 *
 * Attributes:
 * items: List of search results
 * next_cursor: Pagination cursor (always None for now)
 * has_more: Whether more results exist (always False for now)
 */
export type ChunkSearchResponse = {
    /**
     * Search results
     */
    items: Array<ChunkSearchHit>;
    /**
     * Pagination cursor (unused, always null)
     */
    next_cursor?: (string | null);
    /**
     * Whether more results exist (unused)
     */
    has_more?: boolean;
};

