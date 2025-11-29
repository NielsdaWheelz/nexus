/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConversationListItem } from './ConversationListItem';
/**
 * API response for GET /conversations (list conversations).
 *
 * Returns paginated list of user's conversations with cursor-based pagination.
 */
export type ConversationListResponse = {
    /**
     * List of conversations
     */
    items: Array<ConversationListItem>;
    /**
     * Cursor for next page
     */
    next_cursor?: (string | null);
    /**
     * Whether more pages exist
     */
    has_more: boolean;
};

