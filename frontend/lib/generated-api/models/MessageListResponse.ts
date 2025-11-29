/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageListItem } from './MessageListItem';
/**
 * API response for GET /conversations/{id}/messages.
 *
 * Returns paginated list of messages in conversation with cursor-based pagination.
 */
export type MessageListResponse = {
    /**
     * List of messages
     */
    items: Array<MessageListItem>;
    /**
     * Cursor for next page
     */
    next_cursor?: (string | null);
    /**
     * Whether more pages exist
     */
    has_more: boolean;
};

