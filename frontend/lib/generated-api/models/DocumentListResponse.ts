/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentListItem } from "./DocumentListItem";
/**
 * API response for GET /documents (list documents).
 *
 * Returns paginated list of user's documents with cursor-based pagination.
 *
 * Attributes:
 * items: List of DocumentListItem objects (0 to limit)
 * next_cursor: Opaque cursor for next page, or None if end reached
 * has_more: True if more pages exist, False otherwise
 */
export type DocumentListResponse = {
  /**
   * List of documents
   */
  items: Array<DocumentListItem>;
  /**
   * Cursor for next page
   */
  next_cursor?: string | null;
  /**
   * Whether more pages exist
   */
  has_more: boolean;
};
