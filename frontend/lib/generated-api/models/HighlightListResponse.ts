/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HighlightItem } from "./HighlightItem";
/**
 * API response for list highlights endpoints (with pagination).
 *
 * Attributes:
 * items: List of HighlightItem objects
 * next_cursor: Opaque cursor for next page, or null if at end
 * has_more: True if more pages exist, False otherwise
 */
export type HighlightListResponse = {
  /**
   * List of highlights
   */
  items: Array<HighlightItem>;
  /**
   * Cursor for next page
   */
  next_cursor?: string | null;
  /**
   * Whether more items exist
   */
  has_more: boolean;
};
