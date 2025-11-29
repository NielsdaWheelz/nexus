/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response schema for a single message in list endpoint.
 *
 * All IDs are typed (msg_<uuid>), timestamps are ISO8601 UTC.
 */
export type MessageListItem = {
    /**
     * Typed message ID (msg_<uuid>)
     */
    id: string;
    /**
     * Message role
     */
    role: MessageListItem.role;
    /**
     * Message content
     */
    content: string;
    /**
     * UTC timestamp of creation
     */
    created_at: string;
};
export namespace MessageListItem {
    /**
     * Message role
     */
    export enum role {
        USER = 'user',
        ASSISTANT = 'assistant',
    }
}

