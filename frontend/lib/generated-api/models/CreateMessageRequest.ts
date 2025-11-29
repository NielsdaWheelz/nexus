/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request schema for POST /conversations/{id}/messages.
 *
 * Appends a user message to a conversation.
 */
export type CreateMessageRequest = {
    /**
     * Message content (required, non-empty)
     */
    content: string;
};

