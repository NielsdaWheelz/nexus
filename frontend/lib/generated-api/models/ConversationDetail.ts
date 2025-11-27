/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response schema for GET /conversations/{id}.
 *
 * Same fields as ConversationListItem.
 */
export type ConversationDetail = {
  /**
   * Typed conversation ID (conv_<uuid>)
   */
  id: string;
  /**
   * Conversation title
   */
  title?: string | null;
  /**
   * Typed document ID (doc_<uuid>) if conversation is tied to a specific document
   */
  root_document_id?: string | null;
  /**
   * Timestamp of last message
   */
  last_message_at?: string | null;
  /**
   * UTC timestamp of creation
   */
  created_at: string;
  /**
   * UTC timestamp of last update
   */
  updated_at: string;
};
