/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request schema for POST /conversations.
 *
 * Creates a new conversation optionally tied to a document.
 */
export type CreateConversationRequest = {
    /**
     * Optional conversation title (max 512 characters)
     */
    title?: (string | null);
    /**
     * Optional typed document ID (doc_<uuid>) to tie conversation to a document
     */
    root_document_id?: (string | null);
};

