/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API request for updating a reader.
 *
 * Updates the reading position and last_read_at timestamp.
 *
 * Attributes:
 * current_position: Byte offset into canonical text (must be >= 0)
 */
export type UpdateReaderRequest = {
  /**
   * Byte offset into canonical text
   */
  current_position: number;
};
